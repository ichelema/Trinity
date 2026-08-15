#!/usr/bin/env python
"""Test del gate semantico pre-retain (ICH-67, ICH-73): modulo lib + integrazione worker.

Flusso coperto: gate sempre attivo quando retain_enabled e' true;
retain + context -> POST diretta silenziosa; skip -> niente; uncertain +
context -> pending + domanda classica "(sì/no)" (consenso al prompt
successivo, meccanica ICH-66); context VUOTO (retain o uncertain) -> pending +
Claude propone una riga di dominio e chiede "(sì / no / context: …)": al
prompt successivo il context viene risolto con la catena esplicito
(`context: ...`) -> gate -> proposta di Claude nel transcript -> riga
repo/branch (HITL ICH-73); errore tecnico del gate -> fail-closed (nessuna
POST, systemMessage non bloccante una sola volta per sessione, rollback del
contatore di throttling cosi' il prossimo Stop rivaluta)."""

from __future__ import annotations

import importlib.util
import io
import json
import os
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest import mock

from lib import hindsight_config
from lib.hindsight_retain_gate import (
    GATE_ACTIONS,
    GATE_PROMPT,
    GATE_REASONS,
    GATE_SCHEMA,
    REASONS_BY_ACTION,
    GateResult,
    dedup_query,
    evaluate_retain,
    fallback_context,
    fetch_duplicate_candidates,
    handle_retain_consent,
    retain_consent_context,
    retain_consent_decision,
    retain_context_from_transcript,
    save_retain_pending,
)

HERE = Path(__file__).resolve().parent


def fake_api(response: dict, latency: float = 7.0):
    def _call(model, system, user, schema_name, schema, timeout):
        assert schema == GATE_SCHEMA
        return response, latency

    return _call


def user_record(text: str) -> dict:
    return {"type": "user", "message": {"role": "user", "content": text}}


def assistant_record(text: str) -> dict:
    return {
        "type": "assistant",
        "message": {"role": "assistant", "content": [{"type": "text", "text": text}]},
    }


def write_jsonl(path: str, records: list[dict]) -> str:
    """Transcript JSONL minimale (stesso formato dei record reali di Claude Code)."""
    with open(path, "w", encoding="utf-8") as handle:
        for record in records:
            handle.write(json.dumps(record, ensure_ascii=False) + "\n")
    return path


class GateModuleTests(unittest.TestCase):
    def test_routes_retain_skip_uncertain(self):
        cfg = {"retain_gate_model": "m", "retain_gate_timeout": 5}
        summary = {"turns": [("user", "domanda"), ("assistant", "risposta finale")]}

        result = evaluate_retain(
            "finestra",
            summary,
            [],
            cfg,
            fake_api({
                "action": "retain",
                "reason": "durable_decision",
                "preview": "Salvo la decisione X perché Y.",
                "duplicate_of": [],
                "context": "gestione bank e config Hindsight nel progetto Trinity",
            }),
        )
        self.assertEqual(result.action, "retain")
        self.assertEqual(result.reason, "durable_decision")
        self.assertEqual(result.preview, "Salvo la decisione X perché Y.")
        self.assertEqual(
            result.context, "gestione bank e config Hindsight nel progetto Trinity"
        )
        self.assertIsNone(result.error)
        self.assertEqual(result.latency_ms, 7.0)

        result = evaluate_retain(
            "finestra",
            summary,
            [],
            cfg,
            fake_api({
                "action": "skip",
                "reason": "trivial_or_ephemeral",
                "preview": "",
                "duplicate_of": [],
                "context": "",
            }),
        )
        self.assertEqual(result.action, "skip")
        self.assertIsNone(result.error)

        result = evaluate_retain(
            "finestra",
            summary,
            [],
            cfg,
            fake_api({
                "action": "uncertain",
                "reason": "borderline",
                "preview": "Forse vale la pena salvare Z.",
                "duplicate_of": [],
                "context": "ipotesi sulla latenza del recall",
            }),
        )
        self.assertEqual(result.action, "uncertain")

    def test_invalid_payloads_fail_closed(self):
        cfg = {"retain_gate_model": "m", "retain_gate_timeout": 5}
        summary = {"turns": []}
        bad_payloads = [
            {},  # schema incompleto
            {"action": "keep", "reason": "duplicate", "preview": "", "duplicate_of": [], "context": ""},
            {"action": "skip", "reason": "unknown_reason", "preview": "", "duplicate_of": [], "context": ""},
            {"action": "retain", "reason": "durable_decision", "preview": "  ", "duplicate_of": [], "context": ""},
            {"action": "skip", "reason": "duplicate", "preview": "", "duplicate_of": ["0"], "context": ""},
            {"action": "skip", "reason": "duplicate", "preview": "", "duplicate_of": [True], "context": ""},
            {"action": "skip", "reason": "duplicate", "preview": "", "duplicate_of": [0], "context": ""},  # fuori range: 0 candidati
            {"action": "skip", "reason": "duplicate", "preview": "", "duplicate_of": [], "context": 5},  # context non stringa
        ]
        for payload in bad_payloads:
            result = evaluate_retain("finestra", summary, [], cfg, fake_api(payload))
            self.assertEqual(result.action, "skip", payload)
            self.assertEqual(result.reason, "gate_error", payload)
            self.assertIsNotNone(result.error, payload)

    def test_duplicate_indices_validated_against_candidates(self):
        cfg = {"retain_gate_model": "m", "retain_gate_timeout": 5}
        summary = {"turns": [("assistant", "testo di chiusura")]}
        candidates = [{"text": "memoria uno"}, {"text": "memoria due"}]
        with mock.patch(
            "lib.hindsight_retain_gate.fetch_duplicate_candidates",
            return_value=candidates,
        ):
            ok = evaluate_retain(
                "finestra",
                summary,
                ["http://bank"],
                cfg,
                fake_api({
                    "action": "skip",
                    "reason": "duplicate",
                    "preview": "",
                    "duplicate_of": [0, 1],
                    "context": "",
                }),
            )
            self.assertEqual(ok.action, "skip")
            self.assertEqual(ok.reason, "duplicate")
            self.assertEqual(ok.duplicate_of, [0, 1])

            out_of_range = evaluate_retain(
                "finestra",
                summary,
                ["http://bank"],
                cfg,
                fake_api({
                    "action": "skip",
                    "reason": "duplicate",
                    "preview": "",
                    "duplicate_of": [5],
                    "context": "",
                }),
            )
            self.assertEqual(out_of_range.reason, "gate_error")

            duplicated_index = evaluate_retain(
                "finestra",
                summary,
                ["http://bank"],
                cfg,
                fake_api({
                    "action": "skip",
                    "reason": "duplicate",
                    "preview": "",
                    "duplicate_of": [0, 0],
                    "context": "",
                }),
            )
            self.assertEqual(duplicated_index.reason, "gate_error")

            # Combo SEMANTICHE (fix ICH-72): niente gate_error, la action del
            # modello resta e i metadati vengono normalizzati.
            retain_with_indices = evaluate_retain(
                "finestra",
                summary,
                ["http://bank"],
                cfg,
                fake_api({
                    "action": "retain",
                    "reason": "durable_decision",
                    "preview": "Salvo X.",
                    "duplicate_of": [0],
                    "context": "",
                }),
            )
            self.assertEqual(retain_with_indices.action, "retain")
            self.assertEqual(retain_with_indices.duplicate_of, [])
            self.assertEqual(retain_with_indices.candidates, candidates)
            self.assertIsNone(retain_with_indices.error)

            retain_claiming_duplicate = evaluate_retain(
                "finestra",
                summary,
                ["http://bank"],
                cfg,
                fake_api({
                    "action": "retain",
                    "reason": "duplicate",
                    "preview": "Memoria duplicata.",
                    "duplicate_of": [0],
                    "context": "",
                }),
            )
            self.assertEqual(retain_claiming_duplicate.action, "retain")
            self.assertEqual(retain_claiming_duplicate.duplicate_of, [])
            self.assertIsNone(retain_claiming_duplicate.error)

            unclaimed_duplicate = evaluate_retain(
                "finestra",
                summary,
                ["http://bank"],
                cfg,
                fake_api({
                    "action": "skip",
                    "reason": "duplicate",
                    "preview": "",
                    "duplicate_of": [],
                    "context": "",
                }),
            )
            self.assertEqual(unclaimed_duplicate.action, "skip")
            # claim di duplicato senza indici: degradato a skip "neutro"
            self.assertEqual(unclaimed_duplicate.reason, "no_durable_knowledge")
            self.assertIsNone(unclaimed_duplicate.error)

            stray_indices = evaluate_retain(
                "finestra",
                summary,
                ["http://bank"],
                cfg,
                fake_api({
                    "action": "skip",
                    "reason": "trivial_or_ephemeral",
                    "preview": "",
                    "duplicate_of": [0],
                    "context": "",
                }),
            )
            self.assertEqual(stray_indices.action, "skip")
            self.assertEqual(stray_indices.reason, "trivial_or_ephemeral")
            self.assertEqual(stray_indices.duplicate_of, [])
            self.assertIsNone(stray_indices.error)

    def test_mismatched_reason_preserves_action(self):
        """Fix ICH-72: action e reason valide ma male accoppiate NON degradano
        piu' a gate_error (che il worker trattava allora come fail-open, cioe'
        POST diretta anche per finestre giudicate uncertain/skip; da ICH-73 e'
        fail-closed, cioe' finestra persa): la action del modello resta e la
        reason viene accettata com'e'."""
        cfg = {"retain_gate_model": "m", "retain_gate_timeout": 5}
        summary = {"turns": []}
        mismatched = (
            # i primi due sono i casi reali del debug log (2026-08-14)
            ("uncertain", "root_cause_or_workaround", "Forse salvo X."),
            ("uncertain", "environment_constraint", "Forse salvo Y."),
            ("retain", "trivial_or_ephemeral", "Salvo X."),
            ("skip", "durable_decision", ""),
        )
        for action, reason, preview in mismatched:
            result = evaluate_retain(
                "finestra",
                summary,
                [],
                cfg,
                fake_api({
                    "action": action,
                    "reason": reason,
                    "preview": preview,
                    "duplicate_of": [],
                    "context": "dominio di prova",
                }),
            )
            self.assertEqual(result.action, action, (action, reason))
            self.assertEqual(result.reason, reason, (action, reason))
            self.assertEqual(result.preview, preview, (action, reason))
            self.assertIsNone(result.error, (action, reason))

    def test_reason_map_covers_schema_without_overlap(self):
        self.assertEqual(set(REASONS_BY_ACTION), GATE_ACTIONS)
        flattened = [
            reason for reasons in REASONS_BY_ACTION.values() for reason in reasons
        ]
        self.assertEqual(set(flattened), GATE_REASONS)
        self.assertEqual(len(flattened), len(set(flattened)))

    def test_api_errors_fail_closed(self):
        cfg = {"retain_gate_model": "m", "retain_gate_timeout": 5}
        summary = {"turns": []}
        for exc in (
            RuntimeError("OPENAI_API_KEY non impostata"),
            TimeoutError("deadline HTTP superata"),
            json.JSONDecodeError("bad", "x", 0),
            OSError("HTTP 500"),
        ):
            def raising(*_args, _exc=exc, **_kw):
                raise _exc

            result = evaluate_retain("finestra", summary, [], cfg, raising)
            self.assertEqual(result.action, "skip")
            self.assertEqual(result.reason, "gate_error")
            self.assertIn(type(exc).__name__, result.error)

    def test_dedup_query_combines_first_user_and_last_assistant(self):
        self.assertEqual(
            dedup_query({
                "turns": [
                    ("user", "argomento iniziale"),
                    ("assistant", "risposta intermedia"),
                    ("user", "domanda successiva"),
                    ("assistant", "chiusura finale"),
                ]
            }),
            "argomento iniziale\n\nchiusura finale",
        )

    def test_dedup_query_fallbacks_and_avoids_duplicate_text(self):
        self.assertEqual(dedup_query({"turns": [("user", "solo user")]}), "solo user")
        self.assertEqual(
            dedup_query({"turns": [("assistant", "solo assistant")]}),
            "solo assistant",
        )
        self.assertEqual(
            dedup_query({"turns": [("user", "uguale"), ("assistant", "uguale")]}),
            "uguale",
        )
        self.assertEqual(dedup_query({"turns": []}), "")
        self.assertEqual(
            dedup_query({"last_user_prompt": "legacy prompt"}), "legacy prompt"
        )

    def test_dedup_query_limit_preserves_both_parts(self):
        query = dedup_query({
            "turns": [
                ("user", "inizio-user " + "u" * 2000),
                ("assistant", "a" * 2000 + " fine-assistant"),
            ]
        })
        self.assertEqual(len(query), 1500)
        self.assertTrue(query.startswith("inizio-user "))
        self.assertTrue(query.endswith(" fine-assistant"))
        self.assertIn("\n\n", query)

    def test_fetch_duplicate_candidates_dedup_cap_and_query_limit(self):
        calls = []

        def fake_fetch(url, payload, timeout):
            calls.append((url, payload, timeout))
            return [
                {"text": "Fatto A"},
                {"text": "fatto  a"},  # duplicato normalizzato
                {"text": f"unico per {url}"},
            ]

        with mock.patch(
            "lib.hindsight_retain_gate.fetch_bank_results", side_effect=fake_fetch
        ):
            out = fetch_duplicate_candidates(
                ["http://b1", "http://b2"], "q" * 5000, timeout=4
            )
        self.assertEqual(len(out), 3)
        self.assertEqual(len(calls), 2)
        self.assertEqual(len(calls[0][1]["query"]), 1500)
        self.assertEqual(calls[0][1]["limit"], 3)

        with mock.patch(
            "lib.hindsight_retain_gate.fetch_bank_results"
        ) as fetch:
            self.assertEqual(fetch_duplicate_candidates(["http://b1"], "", 4), [])
            fetch.assert_not_called()

    def test_schema_and_enums_consistent(self):
        self.assertEqual(set(GATE_SCHEMA["properties"]["action"]["enum"]), GATE_ACTIONS)
        self.assertEqual(set(GATE_SCHEMA["properties"]["reason"]["enum"]), GATE_REASONS)
        self.assertNotIn("gate_error", GATE_REASONS)  # sentinella solo fail-closed
        # La mappa reason->action e' esplicita anche nel prompt: ogni action e
        # ogni reason del validatore devono comparirvi (niente drift silenzioso).
        for name in sorted(GATE_ACTIONS | GATE_REASONS):
            self.assertIn(name, GATE_PROMPT, name)


class FakeResponse:
    status = 200

    def read(self):
        return b'{"success": true}'

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False


class ConsentTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        env_patch = mock.patch.dict(
            os.environ, {"HS_RETAIN_PENDING_DIR": self.tmp.name}
        )
        env_patch.start()
        self.addCleanup(env_patch.stop)

    def test_consent_vocabulary(self):
        positives = ["si", "sì", "Sì grazie", "va bene", "certo", "procedi", "salvala", "salvala pure e poi continua"]
        negatives = ["no", "No grazie", "non salvarla", "scartala", "non salvare nulla"]
        neutral = ["", "com'è il meteo?", "sistemami il bug del parser"]
        for prompt in positives:
            self.assertEqual(retain_consent_decision(prompt), "positive", prompt)
        for prompt in negatives:
            self.assertEqual(retain_consent_decision(prompt), "negative", prompt)
        for prompt in neutral:
            self.assertIsNone(retain_consent_decision(prompt), prompt)

    def save(self, preview="Salvo la decisione X.", context=None, metadata=None):
        """Pending con la POST pronta. context/metadata None = chiave assente
        nell'item (come i pending storici, pre-ICH-73)."""
        item = {"content": "finestra"}
        if context is not None:
            item["context"] = context
        if metadata is not None:
            item["metadata"] = metadata
        return save_retain_pending(
            "sess-consent",
            "/proj",
            "http://127.0.0.1:9/banks/t",
            {"items": [item], "async": True},
            preview,
        )

    def consent(self, prompt, transcript_path=""):
        """handle_retain_consent con la POST mockata: (esito, item POSTato o None)."""
        with mock.patch(
            "lib.hindsight_retain_gate.urllib.request.urlopen",
            return_value=FakeResponse(),
        ) as urlopen:
            outcome = handle_retain_consent(
                prompt, "sess-consent", "/proj", transcript_path=transcript_path
            )
        posted = None
        if urlopen.called:
            posted = json.loads(urlopen.call_args[0][0].data.decode("utf-8"))["items"][0]
        return outcome, posted

    def transcript(self, *records):
        return write_jsonl(os.path.join(self.tmp.name, "transcript.jsonl"), list(records))

    def test_positive_consumes_and_posts(self):
        self.assertTrue(self.save())
        with mock.patch(
            "lib.hindsight_retain_gate.urllib.request.urlopen",
            return_value=FakeResponse(),
        ) as urlopen:
            outcome = handle_retain_consent("si", "sess-consent", "/proj")
        self.assertEqual(outcome["action"], "saved")
        self.assertEqual(outcome["status"], 200)
        self.assertEqual(outcome["preview"], "Salvo la decisione X.")
        request = urlopen.call_args[0][0]
        self.assertTrue(request.full_url.endswith("/banks/t/memories"))
        # consumo singolo: un secondo "si" non trova piu' nulla
        self.assertIsNone(handle_retain_consent("si", "sess-consent", "/proj"))

    def test_negative_and_new_prompt_discard(self):
        self.assertTrue(self.save())
        outcome = handle_retain_consent("no", "sess-consent", "/proj")
        self.assertEqual(
            outcome,
            {"action": "discarded", "reason": "negative", "preview": "Salvo la decisione X."},
        )
        self.assertIsNone(handle_retain_consent("no", "sess-consent", "/proj"))

        self.assertTrue(self.save())
        outcome = handle_retain_consent(
            "parliamo di tutt'altro adesso", "sess-consent", "/proj"
        )
        self.assertEqual(
            outcome,
            {"action": "discarded", "reason": "new_prompt", "preview": "Salvo la decisione X."},
        )

    def test_context_reply_grammar(self):
        # L'intero prompt e' "context: <testo>", con prefisso di assenso opzionale.
        accepted = {
            "context: architettura X": "architettura X",
            "sì, context: X": "X",
            "Sì context: X": "X",
            "va bene, context: X": "X",
            "d'accordo: context: X": "X",
            "context: X\n": "X",  # newline finale tollerata
        }
        for prompt, expected in accepted.items():
            self.assertEqual(retain_consent_context(prompt), expected, prompt)
        # Il prefisso ammesso e' SOLO il lessico standalone di retain_consent_decision
        # ("ok" non lo e', ne' da solo ne' come prefisso); un prompt multi-riga che
        # apre con "context:" e prosegue con altro e' testo libero -> new_prompt.
        rejected = (
            "si",
            "no",
            "ok, context: X",
            "parliamo del context: X del progetto",
            "context:",
            "context:   ",
            "context: X\n\npoi sistemiamo il README",
        )
        for prompt in rejected:
            self.assertIsNone(retain_consent_context(prompt), prompt)

    def test_positive_keeps_gate_context(self):
        self.assertTrue(self.save(context="dominio del gate"))
        outcome, posted = self.consent("si")
        self.assertEqual(outcome["action"], "saved")
        self.assertEqual(outcome["context_source"], "gate")
        self.assertEqual(outcome["context"], "dominio del gate")
        self.assertEqual(posted["context"], "dominio del gate")

    def test_explicit_context_overrides_pending(self):
        for prompt in ("context: nuovo dominio", "sì, context: nuovo dominio"):
            with self.subTest(prompt=prompt):
                self.assertTrue(self.save(context="dal gate"))
                outcome, posted = self.consent(prompt)
                self.assertEqual(outcome["action"], "saved")
                self.assertEqual(outcome["context_source"], "explicit")
                self.assertEqual(outcome["context"], "nuovo dominio")
                self.assertEqual(posted["context"], "nuovo dominio")

    def test_positive_takes_proposal_from_transcript(self):
        cases = (
            (
                "Salvo questa memoria con context «dominio proposto da claude»? "
                "(sì / no / context: …)",
                "dominio proposto da claude",
            ),
            (
                "Vuoi che salvi questa memoria? — Salvo X. "
                "Context proposto: «altro dominio» (sì / no / context: …)",
                "altro dominio",
            ),
            (
                # due match nell'ultimo messaggio assistant: vince l'ULTIMO
                "Salvo questa memoria con context «primo tentativo»? Anzi, meglio: "
                "Context proposto: «ultimo match» (sì / no / context: …)",
                "ultimo match",
            ),
            (
                # placeholder dell'istruzione ricopiato alla lettera come ULTIMO
                # match: non e' una proposta, vale il match precedente
                "Salvo questa memoria con context «dominio vero»? "
                "(sì / no / context: «<PROPOSTA>»)",
                "dominio vero",
            ),
        )
        for text, expected in cases:
            with self.subTest(expected=expected):
                transcript = self.transcript(
                    user_record("domanda iniziale"),
                    # messaggio assistant PRECEDENTE con una proposta: ignorato
                    assistant_record(
                        "Salvo questa memoria con context «proposta vecchia»? "
                        "(sì / no / context: …)"
                    ),
                    user_record("altra domanda"),
                    assistant_record(text),
                )
                self.assertEqual(retain_context_from_transcript(transcript), expected)
                self.assertTrue(self.save(context=""))
                outcome, posted = self.consent("si", transcript_path=transcript)
                self.assertEqual(outcome["action"], "saved")
                self.assertEqual(outcome["context_source"], "proposal")
                self.assertEqual(outcome["context"], expected)
                self.assertEqual(posted["context"], expected)

    def test_positive_falls_back_to_repo_branch(self):
        self.assertEqual(
            fallback_context({"repo": "Trinity", "branch": "main"}),
            "sessione Claude Code nel repo Trinity, branch main",
        )
        self.assertEqual(
            fallback_context({"repo": "Trinity"}), "sessione Claude Code nel repo Trinity"
        )
        self.assertEqual(
            fallback_context({"branch": "main"}), "sessione Claude Code sul branch main"
        )
        self.assertEqual(fallback_context({}), "sessione Claude Code")

        # nessun transcript: ultima risorsa repo/branch dai metadata dell'item
        self.assertTrue(
            self.save(context="", metadata={"repo": "Trinity", "branch": "main"})
        )
        outcome, posted = self.consent("si")
        self.assertEqual(outcome["action"], "saved")
        self.assertEqual(outcome["context_source"], "fallback")
        self.assertEqual(outcome["context"], "sessione Claude Code nel repo Trinity, branch main")
        self.assertEqual(posted["context"], "sessione Claude Code nel repo Trinity, branch main")

        # transcript senza proposta (o inesistente) + metadata vuoti
        transcript = self.transcript(
            user_record("domanda"), assistant_record("Fatto, ho chiuso il task.")
        )
        self.assertIsNone(retain_context_from_transcript(transcript))
        self.assertIsNone(
            retain_context_from_transcript(os.path.join(self.tmp.name, "missing.jsonl"))
        )
        self.assertTrue(self.save(context="", metadata={}))
        outcome, posted = self.consent("si", transcript_path=transcript)
        self.assertEqual(outcome["context_source"], "fallback")
        self.assertEqual(outcome["context"], "sessione Claude Code")
        self.assertEqual(posted["context"], "sessione Claude Code")

    def test_proposal_skips_placeholder_and_tool_only_records(self):
        # solo il placeholder ricopiato alla lettera: nessuna proposta
        self.assertIsNone(
            retain_context_from_transcript(
                self.transcript(
                    assistant_record("Salvo questa memoria con context «<PROPOSTA>»?")
                )
            )
        )
        # l'ultimo record assistant e' un tool_use senza testo (Claude Code scrive
        # un record per content-block): si risale al testo precedente
        tool_only = {
            "type": "assistant",
            "message": {
                "role": "assistant",
                "content": [{"type": "tool_use", "name": "Read", "input": {}}],
            },
        }
        self.assertEqual(
            retain_context_from_transcript(
                self.transcript(
                    assistant_record("Salvo questa memoria con context «prima del tool»?"),
                    tool_only,
                )
            ),
            "prima del tool",
        )

    def test_discard_returns_preview(self):
        self.assertTrue(self.save())
        self.assertEqual(
            handle_retain_consent("no", "sess-consent", "/proj"),
            {"action": "discarded", "reason": "negative", "preview": "Salvo la decisione X."},
        )
        self.assertTrue(self.save(preview="Salvo la decisione Y."))
        self.assertEqual(
            handle_retain_consent("sistemami il bug del parser", "sess-consent", "/proj"),
            {"action": "discarded", "reason": "new_prompt", "preview": "Salvo la decisione Y."},
        )

    def test_post_failure_reports_error(self):
        self.assertTrue(self.save())
        with mock.patch(
            "lib.hindsight_retain_gate.urllib.request.urlopen",
            side_effect=OSError("connection refused"),
        ):
            outcome = handle_retain_consent("si", "sess-consent", "/proj")
        self.assertEqual(outcome["action"], "error")
        self.assertIn("OSError", outcome["error"])

    def test_pending_requires_session_id(self):
        self.assertFalse(
            save_retain_pending("", "/proj", "http://x", {"items": []}, "p")
        )
        self.assertIsNone(handle_retain_consent("si", "", "/proj"))


class GateConfigTests(unittest.TestCase):
    def test_defaults_and_override_validation(self):
        self.assertNotIn("retain_gate_mode", hindsight_config.DEFAULTS)
        # ICH-73: il fallback nano del context e' rimosso, chiavi comprese.
        for key in (
            "context_extraction",
            "context_extraction_strategy",
            "context_extraction_model",
        ):
            self.assertNotIn(key, hindsight_config.DEFAULTS, key)
        self.assertEqual(hindsight_config.DEFAULTS["retain_gate_model"], "gpt-5.6-luna")
        self.assertEqual(hindsight_config.DEFAULTS["retain_gate_timeout"], 15)
        self.assertIs(hindsight_config.DEFAULTS["retain_debug_in_context"], False)

        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "config.json")
            cfg = dict(hindsight_config.DEFAULTS)
            with open(path, "w", encoding="utf-8") as handle:
                json.dump(
                    {
                        "retain_gate_timeout": -3,
                        "retain_gate_model": "  ",
                        "retain_debug_in_context": "yes",
                    },
                    handle,
                )
            hindsight_config._merge_json(cfg, path)
            self.assertEqual(cfg["retain_gate_timeout"], 15)
            self.assertEqual(cfg["retain_gate_model"], "gpt-5.6-luna")
            self.assertIs(cfg["retain_debug_in_context"], False)

            with open(path, "w", encoding="utf-8") as handle:
                json.dump(
                    {"retain_gate_timeout": 8, "retain_debug_in_context": True}, handle
                )
            hindsight_config._merge_json(cfg, path)
            self.assertEqual(cfg["retain_gate_timeout"], 8)
            self.assertIs(cfg["retain_debug_in_context"], True)


def load_worker():
    spec = importlib.util.spec_from_file_location(
        "retain_worker_under_test", HERE / "hindsight-retain-worker.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class WorkerGateTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.worker = load_worker()

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        transcript = os.path.join(self.tmp.name, "transcript.jsonl")
        entries = [
            {
                "type": "user",
                "message": {
                    "role": "user",
                    "content": "domanda abbastanza lunga per superare i filtri del retain",
                },
            },
            {
                "type": "assistant",
                "message": {
                    "role": "assistant",
                    "content": [
                        {
                            "type": "text",
                            "text": "Deciso: usiamo il gate semantico prima della POST perché riduce il rumore.",
                        }
                    ],
                },
            },
        ]
        with open(transcript, "w", encoding="utf-8") as handle:
            for entry in entries:
                handle.write(json.dumps(entry) + "\n")
        self.transcript = transcript
        self.hook_input = json.dumps(
            {
                "session_id": "sess-gate-test",
                "transcript_path": transcript,
                "cwd": self.tmp.name,
                "hook_event_name": "Stop",
            }
        )

        env = {
            "HS_RETAIN_STATE_DIR": self.tmp.name,
            "HS_RETAIN_PENDING_DIR": os.path.join(self.tmp.name, "pending"),
            "HOOK_INPUT": self.hook_input,
        }
        env_patch = mock.patch.dict(os.environ, env)
        env_patch.start()
        self.addCleanup(env_patch.stop)
        for var in ("HS_RETAIN_FORCE", "API_URL"):
            os.environ.pop(var, None)

        patches = [
            mock.patch.object(self.worker, "HOOK_INPUT", self.hook_input),
            mock.patch.object(
                self.worker,
                "git_info",
                return_value={"repo": "", "branch": "", "commit": ""},
            ),
            mock.patch.object(
                self.worker, "retain_bank_url", return_value="http://127.0.0.1:9/banks/t"
            ),
            mock.patch.object(
                self.worker,
                "recall_bank_urls",
                return_value=["http://127.0.0.1:9/banks/t"],
            ),
        ]
        for patch in patches:
            patch.start()
            self.addCleanup(patch.stop)

    def cfg(self, **overrides):
        base = dict(self.worker.CFG)
        base.update(
            {
                "retain_enabled": True,
                "retain_mode": "chunked",
                "retain_every_n_turns": 1,
                "retain_overlap_turns": 1,
                "retain_tool_calls": False,
                "retain_text_truncate": 2000,
                "retain_max_files": 15,
                "retain_max_cmds": 10,
                "debug_log_enabled": False,
                "retain_debug_in_context": False,
            }
        )
        base.update(overrides)
        return base

    def read_state(self) -> dict:
        """File di stato del worker (stop_count, gate_error_notified per sessione)."""
        with open(
            os.path.join(self.tmp.name, "hs-retain-state.json"), encoding="utf-8"
        ) as handle:
            return json.load(handle)

    def consent(self, prompt, transcript_path=""):
        """handle_retain_consent sul pending del worker: (esito, item POSTato o None)."""
        with mock.patch(
            "lib.hindsight_retain_gate.urllib.request.urlopen",
            return_value=FakeResponse(),
        ) as urlopen:
            outcome = handle_retain_consent(
                prompt, "sess-gate-test", self.tmp.name, transcript_path=transcript_path
            )
        posted = None
        if urlopen.called:
            posted = json.loads(urlopen.call_args[0][0].data.decode("utf-8"))["items"][0]
        return outcome, posted

    def run_main(self, cfg, gate_result):
        stdout = io.StringIO()
        gate_mock = mock.Mock(return_value=gate_result)
        with mock.patch.object(self.worker, "CFG", cfg), mock.patch.object(
            self.worker, "evaluate_retain", gate_mock
        ), mock.patch("urllib.request.urlopen", return_value=FakeResponse()) as urlopen:
            with redirect_stdout(stdout):
                rc = self.worker.main()
        return rc, stdout.getvalue(), gate_mock, urlopen

    @staticmethod
    def gate_lines(out: str) -> list[dict]:
        return [
            json.loads(line[len("HSGATE ") :])
            for line in out.splitlines()
            if line.startswith("HSGATE ")
        ]

    def test_gate_not_called_before_third_stop(self):
        cfg = self.cfg(retain_every_n_turns=3)
        gate_result = GateResult(action="skip", reason="trivial_or_ephemeral")
        calls = []
        for _ in range(3):
            rc, _out, gate_mock, _urlopen = self.run_main(cfg, gate_result)
            self.assertEqual(rc, 0)
            calls.append(gate_mock.call_count)
        self.assertEqual(calls, [0, 0, 1])

    def test_retain_posts_directly_and_silently(self):
        rc, out, gate_mock, urlopen = self.run_main(
            self.cfg(),
            GateResult(
                action="retain",
                reason="durable_decision",
                preview="Salvo X.",
                context="convenzioni di branching nel progetto di prova",
            ),
        )
        self.assertEqual(rc, 0)
        self.assertEqual(gate_mock.call_count, 1)
        self.assertEqual(urlopen.call_count, 1)
        self.assertEqual(self.gate_lines(out), [])  # nessuna notifica: silenzioso
        item = json.loads(urlopen.call_args[0][0].data.decode("utf-8"))["items"][0]
        # context descrittivo dal gate; niente header volatile nel content
        self.assertEqual(item["context"], "convenzioni di branching nel progetto di prova")
        self.assertTrue(item["content"].startswith("## Conversation (recent turns)"))
        self.assertNotIn("Session:", item["content"])
        self.assertNotIn("CWD:", item["content"])

    def test_retain_without_context_blocks_asking_context(self):
        # retain SENZA context: niente POST diretta e niente fallback LLM (ICH-73):
        # pending + block, Claude propone un context e chiede conferma.
        rc, out, _gate, urlopen = self.run_main(
            self.cfg(),
            GateResult(
                action="retain", reason="durable_decision", preview="Salvo X.", context=""
            ),
        )
        self.assertEqual(rc, 0)
        urlopen.assert_not_called()
        lines = self.gate_lines(out)
        self.assertEqual(len(lines), 1)
        self.assertEqual(lines[0]["decision"], "block")
        reason = lines[0]["reason"]
        self.assertIn(
            "Salvo questa memoria con context «<PROPOSTA>»? (sì / no / context: …)", reason
        )
        self.assertIn("Salvo X.", reason)
        self.assertNotIn("hookSpecificOutput", lines[0])

        # Risposta esplicita "context: ..." al prompt successivo -> POST con quel context.
        outcome, posted = self.consent("context: dominio scelto")
        self.assertEqual(outcome["action"], "saved")
        self.assertEqual(outcome["context_source"], "explicit")
        self.assertEqual(outcome["context"], "dominio scelto")
        self.assertEqual(posted["context"], "dominio scelto")
        self.assertIn("document_id", posted)

    def test_uncertain_without_context_asks_fused_question(self):
        preview = "Forse vale la pena salvare la scelta sul gate."
        rc, out, _gate, urlopen = self.run_main(
            self.cfg(),
            GateResult(action="uncertain", reason="borderline", preview=preview, context=""),
        )
        self.assertEqual(rc, 0)
        urlopen.assert_not_called()
        lines = self.gate_lines(out)
        self.assertEqual(len(lines), 1)
        self.assertEqual(lines[0]["decision"], "block")
        # La preview finisce col punto: nella domanda fusa non deve raddoppiare.
        self.assertIn(
            f"Vuoi che salvi questa memoria? — {preview.rstrip('.')}. "
            "Context proposto: «<PROPOSTA>» (sì / no / context: …)",
            lines[0]["reason"],
        )
        self.assertNotIn("..", lines[0]["reason"].replace("…", ""))

        # "si" al prompt successivo: il context arriva dalla proposta che Claude
        # ha scritto nel transcript (ultimo messaggio assistant).
        transcript = write_jsonl(
            os.path.join(self.tmp.name, "consent-transcript.jsonl"),
            [
                user_record("domanda abbastanza lunga per superare i filtri del retain"),
                assistant_record(
                    f"Vuoi che salvi questa memoria? — {preview}. "
                    "Context proposto: «dominio dal transcript» (sì / no / context: …)"
                ),
            ],
        )
        outcome, posted = self.consent("si", transcript_path=transcript)
        self.assertEqual(outcome["action"], "saved")
        self.assertEqual(outcome["context_source"], "proposal")
        self.assertEqual(outcome["context"], "dominio dal transcript")
        self.assertEqual(posted["context"], "dominio dal transcript")

    def test_retain_debug_emits_summary(self):
        rc, out, _gate, urlopen = self.run_main(
            self.cfg(retain_debug_in_context=True),
            GateResult(
                action="retain",
                reason="durable_decision",
                preview="Salvo X.",
                context="dominio di prova",
            ),
        )
        self.assertEqual(rc, 0)
        self.assertEqual(urlopen.call_count, 1)
        lines = self.gate_lines(out)
        self.assertEqual(len(lines), 1)
        self.assertNotIn("decision", lines[0])
        self.assertIn("## Hindsight retain debug", lines[0]["systemMessage"])
        self.assertIn("retain (durable_decision)", lines[0]["systemMessage"])

    def test_skip_saves_nothing(self):
        rc, out, _gate, urlopen = self.run_main(
            self.cfg(), GateResult(action="skip", reason="repo_recoverable")
        )
        self.assertEqual(rc, 0)
        urlopen.assert_not_called()
        self.assertEqual(self.gate_lines(out), [])

    def test_gate_error_is_fail_closed_with_rollback_and_notice(self):
        cfg = self.cfg(retain_every_n_turns=3)
        gate_error = GateResult(action="skip", reason="gate_error", error="TimeoutError: x")
        # 1° e 2° Stop: throttling, il gate non viene nemmeno chiamato.
        for _ in range(2):
            rc, out, gate_mock, urlopen = self.run_main(cfg, gate_error)
            self.assertEqual(rc, 0)
            gate_mock.assert_not_called()
            urlopen.assert_not_called()
            self.assertEqual(self.gate_lines(out), [])
        # 3° Stop: gate chiamato -> errore tecnico -> FAIL-CLOSED: nessuna POST,
        # systemMessage non bloccante, rollback del contatore.
        rc, out, gate_mock, urlopen = self.run_main(cfg, gate_error)
        self.assertEqual(rc, 0)
        self.assertEqual(gate_mock.call_count, 1)
        urlopen.assert_not_called()
        lines = self.gate_lines(out)
        self.assertEqual(len(lines), 1)
        self.assertNotIn("decision", lines[0])  # notifica, non block
        self.assertIn("errore tecnico del gate", lines[0]["systemMessage"])
        self.assertIn("TimeoutError: x", lines[0]["systemMessage"])
        entry = self.read_state()["sess-gate-test"]
        self.assertEqual(entry["stop_count"], 2)  # 3 -> 2: il prossimo Stop rivaluta
        self.assertIs(entry["gate_error_notified"], True)
        # 4° Stop: il contatore torna a 3 -> gate CHIAMATO di nuovo (rollback
        # efficace); stesso errore -> nessuna seconda notifica nella sessione.
        rc, out, gate_mock, urlopen = self.run_main(cfg, gate_error)
        self.assertEqual(rc, 0)
        self.assertEqual(gate_mock.call_count, 1)
        urlopen.assert_not_called()
        self.assertEqual(self.gate_lines(out), [])
        self.assertEqual(self.read_state()["sess-gate-test"]["stop_count"], 2)

    def test_gate_error_debug_still_emits_block(self):
        rc, out, _gate, urlopen = self.run_main(
            self.cfg(retain_debug_in_context=True),
            GateResult(action="skip", reason="gate_error", error="TimeoutError: x"),
        )
        self.assertEqual(rc, 0)
        urlopen.assert_not_called()
        lines = self.gate_lines(out)
        self.assertEqual(len(lines), 1)
        self.assertNotIn("decision", lines[0])
        message = lines[0]["systemMessage"]
        self.assertIn("errore tecnico del gate", message)  # notifica fail-closed
        self.assertIn("## Hindsight retain debug", message)  # + blocco debug
        self.assertIn("fail-closed", message)
        self.assertIn(
            "## Hindsight retain debug",
            lines[0]["hookSpecificOutput"]["additionalContext"],
        )

    def test_uncertain_blocks_and_saves_pending(self):
        preview = "Vale la pena salvare la decisione sul gate?"
        rc, out, _gate, urlopen = self.run_main(
            self.cfg(),
            GateResult(
                action="uncertain", reason="borderline", preview=preview, context="dominio"
            ),
        )
        self.assertEqual(rc, 0)
        urlopen.assert_not_called()
        lines = self.gate_lines(out)
        self.assertEqual(len(lines), 1)
        self.assertEqual(lines[0]["decision"], "block")
        # uncertain CON context: la domanda classica resta identica (niente
        # proposta di context, ICH-73 tocca solo il caso context vuoto).
        self.assertIn(
            f"Vuoi che salvi questa memoria? — {preview} (sì/no)", lines[0]["reason"]
        )
        self.assertNotIn("<PROPOSTA>", lines[0]["reason"])
        # Niente hookSpecificOutput: additionalContext non e' documentato per
        # Stop e duplicava l'istruzione nel transcript (error + feedback).
        self.assertNotIn("hookSpecificOutput", lines[0])

        # Il pending contiene la POST pronta: il "si" al prompt successivo la esegue.
        with mock.patch(
            "lib.hindsight_retain_gate.urllib.request.urlopen",
            return_value=FakeResponse(),
        ) as consent_post:
            outcome = handle_retain_consent("si", "sess-gate-test", self.tmp.name)
        self.assertEqual(outcome["action"], "saved")
        self.assertEqual(outcome["context_source"], "gate")
        self.assertEqual(consent_post.call_count, 1)
        posted = json.loads(consent_post.call_args[0][0].data.decode("utf-8"))
        self.assertEqual(len(posted["items"]), 1)
        self.assertIn("document_id", posted["items"][0])
        self.assertEqual(posted["items"][0]["context"], "dominio")

    def test_uncertain_with_semantic_reason_still_pending(self):
        # Regressione ICH-72: uncertain + reason semantica arrivava al worker
        # come gate_error (allora fail-open) => POST diretta. Ora resta un
        # uncertain normale: pending + domanda, nessun salvataggio silenzioso.
        preview = "Salvo la causa radice appena confermata?"
        rc, out, _gate, urlopen = self.run_main(
            self.cfg(),
            GateResult(
                action="uncertain",
                reason="root_cause_or_workaround",
                preview=preview,
                context="dominio",
            ),
        )
        self.assertEqual(rc, 0)
        urlopen.assert_not_called()
        lines = self.gate_lines(out)
        self.assertEqual(len(lines), 1)
        self.assertEqual(lines[0]["decision"], "block")
        self.assertIn(preview, lines[0]["reason"])

    def test_window_boundaries_ignore_synthetic_user_messages(self):
        def user(text):
            return {"type": "user", "message": {"role": "user", "content": text}}

        def assistant(text):
            return {
                "type": "user",
                "message": {
                    "role": "assistant",
                    "content": [{"type": "text", "text": text}],
                },
            }

        tool_result = {
            "type": "user",
            "message": {
                "role": "user",
                "content": [{"type": "tool_result", "content": "output del tool"}],
            },
        }
        reminder = {
            "type": "user",
            "message": {"role": "user", "content": "<system-reminder>nota</system-reminder>"},
        }
        entries = [
            user("prima domanda vera dell'utente"),
            assistant("prima risposta"),
            tool_result,
            tool_result,
            reminder,
            assistant("seconda risposta dopo i tool"),
            user("seconda domanda vera dell'utente"),
            assistant("terza risposta"),
        ]
        summary = self.worker.summarize_window(entries, 2)
        user_texts = [t for r, t in summary["turns"] if r == "user"]
        # 2 turni UMANI: la finestra parte dalla prima domanda vera, non viene
        # consumata da tool_result/reminder (pseudo-turni con ruolo user).
        self.assertEqual(
            user_texts,
            ["prima domanda vera dell'utente", "seconda domanda vera dell'utente"],
        )
        # e con finestra 1 resta solo l'ultimo turno umano
        summary_one = self.worker.summarize_window(entries, 1)
        self.assertEqual(
            [t for r, t in summary_one["turns"] if r == "user"],
            ["seconda domanda vera dell'utente"],
        )

    def test_chunked_doc_id_stable_on_replay(self):
        cfg = self.cfg()
        payloads = []

        def capture(req, timeout=10):
            payloads.append(json.loads(req.data.decode("utf-8")))
            return FakeResponse()

        gate = GateResult(
            action="retain", reason="durable_decision", preview="x", context="dominio"
        )
        with mock.patch.object(self.worker, "CFG", cfg), mock.patch.object(
            self.worker, "evaluate_retain", return_value=gate
        ), mock.patch("urllib.request.urlopen", side_effect=capture):
            with redirect_stdout(io.StringIO()):
                self.assertEqual(self.worker.main(), 0)
                self.assertEqual(self.worker.main(), 0)

        self.assertEqual(len(payloads), 2)
        first, second = (p["items"][0] for p in payloads)
        self.assertEqual(first["document_id"], second["document_id"])
        self.assertTrue(first["document_id"].startswith("sess-gate-test-"))
        # Senza header volatile il content e' identico sui replay: stesso id.
        self.assertEqual(first["content"], second["content"])

        with open(self.transcript, "a", encoding="utf-8") as handle:
            handle.write(
                json.dumps(
                    {
                        "type": "user",
                        "message": {
                            "role": "user",
                            "content": "un altro prompt che cambia la finestra del retain",
                        },
                    }
                )
                + "\n"
            )
        with mock.patch.object(self.worker, "CFG", cfg), mock.patch.object(
            self.worker, "evaluate_retain", return_value=gate
        ), mock.patch("urllib.request.urlopen", side_effect=capture):
            with redirect_stdout(io.StringIO()):
                self.assertEqual(self.worker.main(), 0)
        self.assertNotEqual(payloads[2]["items"][0]["document_id"], first["document_id"])


if __name__ == "__main__":
    unittest.main()
