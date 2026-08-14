#!/usr/bin/env python
"""Test del gate semantico pre-retain (ICH-67): modulo lib + integrazione worker.

Flusso coperto: gate sempre attivo quando retain_enabled e' true;
retain -> POST diretta silenziosa; skip -> niente; uncertain -> pending +
domanda (consenso al prompt successivo, meccanica ICH-66); errore tecnico
del gate -> fail-open (POST come prima del gate)."""

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
    GATE_REASONS,
    GATE_SCHEMA,
    REASONS_BY_ACTION,
    GateResult,
    dedup_query,
    evaluate_retain,
    fetch_duplicate_candidates,
    handle_retain_consent,
    retain_consent_decision,
    save_retain_pending,
)

HERE = Path(__file__).resolve().parent


def fake_api(response: dict, latency: float = 7.0):
    def _call(model, system, user, schema_name, schema, timeout):
        assert schema == GATE_SCHEMA
        return response, latency

    return _call


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
            {"action": "skip", "reason": "duplicate", "preview": "", "duplicate_of": [], "context": ""},
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

            for payload in (
                {
                    "action": "retain",
                    "reason": "duplicate",
                    "preview": "Memoria duplicata.",
                    "duplicate_of": [0],
                    "context": "",
                },
                {
                    "action": "skip",
                    "reason": "duplicate",
                    "preview": "",
                    "duplicate_of": [],
                    "context": "",
                },
                {
                    "action": "skip",
                    "reason": "trivial_or_ephemeral",
                    "preview": "",
                    "duplicate_of": [0],
                    "context": "",
                },
            ):
                inconsistent = evaluate_retain(
                    "finestra", summary, ["http://bank"], cfg, fake_api(payload)
                )
                self.assertEqual(inconsistent.reason, "gate_error", payload)

    def test_reason_must_match_action(self):
        cfg = {"retain_gate_model": "m", "retain_gate_timeout": 5}
        summary = {"turns": []}
        contradictory = (
            ("retain", "trivial_or_ephemeral", "Salvo X."),
            ("skip", "durable_decision", ""),
            ("uncertain", "repo_recoverable", "Forse salvo X."),
        )
        for action, reason, preview in contradictory:
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
            self.assertEqual(result.reason, "gate_error", (action, reason))
            self.assertIsNotNone(result.error, (action, reason))
            self.assertIn("incompatibile", result.error or "", (action, reason))

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

    def save(self, preview="Salvo la decisione X."):
        return save_retain_pending(
            "sess-consent",
            "/proj",
            "http://127.0.0.1:9/banks/t",
            {"items": [{"content": "finestra"}], "async": True},
            preview,
        )

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
        self.assertEqual(outcome, {"action": "discarded", "reason": "negative"})
        self.assertIsNone(handle_retain_consent("no", "sess-consent", "/proj"))

        self.assertTrue(self.save())
        outcome = handle_retain_consent(
            "parliamo di tutt'altro adesso", "sess-consent", "/proj"
        )
        self.assertEqual(outcome, {"action": "discarded", "reason": "new_prompt"})

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
                "context_extraction": False,
                "debug_log_enabled": False,
                "retain_debug_in_context": False,
            }
        )
        base.update(overrides)
        return base

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

    def test_gate_context_fallback_when_empty(self):
        rc, _out, _gate, urlopen = self.run_main(
            self.cfg(),
            GateResult(action="retain", reason="durable_decision", preview="Salvo X."),
        )
        self.assertEqual(rc, 0)
        item = json.loads(urlopen.call_args[0][0].data.decode("utf-8"))["items"][0]
        # context vuoto dal gate -> catena storica (context_extraction off => piano)
        self.assertEqual(item["context"], "claude-code")

    def test_retain_debug_emits_summary(self):
        rc, out, _gate, urlopen = self.run_main(
            self.cfg(retain_debug_in_context=True),
            GateResult(action="retain", reason="durable_decision", preview="Salvo X."),
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

    def test_gate_error_is_fail_open(self):
        rc, _out, _gate, urlopen = self.run_main(
            self.cfg(),
            GateResult(action="skip", reason="gate_error", error="TimeoutError: x"),
        )
        self.assertEqual(rc, 0)
        self.assertEqual(urlopen.call_count, 1)  # salva come prima del gate

    def test_uncertain_blocks_and_saves_pending(self):
        preview = "Vale la pena salvare la decisione sul gate?"
        rc, out, _gate, urlopen = self.run_main(
            self.cfg(), GateResult(action="uncertain", reason="borderline", preview=preview)
        )
        self.assertEqual(rc, 0)
        urlopen.assert_not_called()
        lines = self.gate_lines(out)
        self.assertEqual(len(lines), 1)
        self.assertEqual(lines[0]["decision"], "block")
        self.assertIn("Vuoi che salvi questa memoria?", lines[0]["reason"])
        self.assertIn(preview, lines[0]["reason"])
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
        self.assertEqual(consent_post.call_count, 1)
        posted = json.loads(consent_post.call_args[0][0].data.decode("utf-8"))
        self.assertEqual(len(posted["items"]), 1)
        self.assertIn("document_id", posted["items"][0])

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

        gate = GateResult(action="retain", reason="durable_decision", preview="x")
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
