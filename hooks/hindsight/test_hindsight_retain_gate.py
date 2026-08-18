#!/usr/bin/env python
"""Test del gate semantico pre-retain (ICH-67, ICH-73, ICH-86): modulo lib +
integrazione worker.

Flusso coperto: gate sempre attivo quando retain_enabled e' true;
retain + context -> POST diretta silenziosa; skip -> niente; uncertain +
context -> pending + domanda classica "(sì/no)" (consenso al prompt
successivo, meccanica ICH-66); context VUOTO (retain o uncertain) -> pending +
Claude propone una riga di dominio e chiede "(sì / no / context: …)": al
prompt successivo il context viene risolto con la catena esplicito
(`context: ...`) -> gate -> proposta di Claude nel transcript -> riga
repo/branch (HITL ICH-73); errore tecnico del gate -> fail-closed (nessuna
POST, systemMessage non bloccante una sola volta per sessione, rollback del
contatore di throttling cosi' la valutazione successiva riprova).
Da ICH-86 il worker valuta a UserPromptSubmit l'entry accodata dallo Stop
(coda hs-retain-queue, evaluate_queued) o in drain a fine sessione: la
domanda del gate viaggia in additionalContext e chiude la risposta successiva.
La valutazione differita gira in un processo detached (`--queued`) che scrive
un outbox; qui il launcher e' sostituito da un thread in-process (fake_spawn)
per restare ermetici — il vero processo e' coperto da test_hindsight_recall_hook."""

from __future__ import annotations

import ast
import importlib.util
import io
import json
import os
import re
import tempfile
import threading
import time
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from unittest import mock

from lib import hindsight_config
from lib.hindsight_recall_lib import _VALID_RECALL_TYPES
from lib.hindsight_retain_gate import (
    DEDUP_CANDIDATE_TYPES,
    DEDUP_DOC_FACTS_CAP,
    GATE_ACTIONS,
    GATE_PROMPT,
    GATE_REASONS,
    GATE_SCHEMA,
    REASONS_BY_ACTION,
    GateResult,
    complete_documents,
    dedup_query,
    evaluate_retain,
    fallback_context,
    fetch_document_facts,
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


def gate_payload(**overrides) -> dict:
    """Risposta valida del gate; gli override cambiano i soli campi voluti."""
    payload = {
        "durable_claims": [],
        "covered_by": [],
        "action": "skip",
        "reason": "trivial_or_ephemeral",
        "preview": "",
        "context": "",
    }
    payload.update(overrides)
    return payload


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
            fake_api(gate_payload(
                action="retain",
                reason="durable_decision",
                preview="Salvo la decisione X perché Y.",
                context="gestione bank e config Hindsight nel progetto Trinity",
            )),
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
            fake_api(gate_payload()),
        )
        self.assertEqual(result.action, "skip")
        self.assertIsNone(result.error)

        result = evaluate_retain(
            "finestra",
            summary,
            [],
            cfg,
            fake_api(gate_payload(
                action="uncertain",
                reason="borderline",
                preview="Forse vale la pena salvare Z.",
                context="ipotesi sulla latenza del recall",
            )),
        )
        self.assertEqual(result.action, "uncertain")

    def test_invalid_payloads_fail_closed(self):
        cfg = {"retain_gate_model": "m", "retain_gate_timeout": 5}
        summary = {"turns": []}
        missing_durable_claims = gate_payload()
        del missing_durable_claims["durable_claims"]
        bad_payloads = [
            {},  # schema incompleto
            gate_payload(action="keep", reason="duplicate"),
            gate_payload(reason="unknown_reason"),
            gate_payload(action="retain", reason="durable_decision", preview="  "),
            gate_payload(reason="duplicate", covered_by=["0"]),
            gate_payload(reason="duplicate", covered_by=[True]),
            gate_payload(reason="duplicate", covered_by=[0]),  # fuori range: 0 candidati
            gate_payload(reason="duplicate", context=5),  # context non stringa
            missing_durable_claims,  # durable_claims assente
            gate_payload(durable_claims="x"),  # durable_claims non lista
            gate_payload(durable_claims=[1]),  # elemento non stringa
        ]
        for payload in bad_payloads:
            result = evaluate_retain("finestra", summary, [], cfg, fake_api(payload))
            self.assertEqual(result.action, "skip", payload)
            self.assertEqual(result.reason, "gate_error", payload)
            self.assertIsNotNone(result.error, payload)

    def test_coverage_indices_validated_against_candidates(self):
        """Rinominato da test_duplicate_indices_validated_against_candidates
        (ICH-84): covered_by sostituisce duplicate_of nel payload del gate.
        Cuore del fix, vedi stray_indices sotto: su skip, covered_by non
        vuoto vince SEMPRE sulla reason dichiarata dal modello, non solo su
        "duplicate". Prima (ICH-72) gli indici in una reason diversa da
        "duplicate" venivano scartati e la reason originale restava intatta;
        ora covered_by forza reason="duplicate" a prescindere."""
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
                fake_api(gate_payload(reason="duplicate", covered_by=[0, 1])),
            )
            self.assertEqual(ok.action, "skip")
            self.assertEqual(ok.reason, "duplicate")
            self.assertEqual(ok.duplicate_of, [0, 1])

            out_of_range = evaluate_retain(
                "finestra",
                summary,
                ["http://bank"],
                cfg,
                fake_api(gate_payload(reason="duplicate", covered_by=[5])),
            )
            self.assertEqual(out_of_range.reason, "gate_error")

            duplicated_index = evaluate_retain(
                "finestra",
                summary,
                ["http://bank"],
                cfg,
                fake_api(gate_payload(reason="duplicate", covered_by=[0, 0])),
            )
            self.assertEqual(duplicated_index.reason, "gate_error")

            # Combo SEMANTICHE (fix ICH-72): niente gate_error, la action del
            # modello resta e i metadati vengono normalizzati.
            retain_with_indices = evaluate_retain(
                "finestra",
                summary,
                ["http://bank"],
                cfg,
                fake_api(gate_payload(
                    action="retain",
                    reason="durable_decision",
                    preview="Salvo X.",
                    covered_by=[0],
                )),
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
                fake_api(gate_payload(
                    action="retain",
                    reason="duplicate",
                    preview="Memoria duplicata.",
                    covered_by=[0],
                )),
            )
            self.assertEqual(retain_claiming_duplicate.action, "retain")
            self.assertEqual(retain_claiming_duplicate.duplicate_of, [])
            self.assertIsNone(retain_claiming_duplicate.error)

            unclaimed_duplicate = evaluate_retain(
                "finestra",
                summary,
                ["http://bank"],
                cfg,
                fake_api(gate_payload(reason="duplicate")),
            )
            self.assertEqual(unclaimed_duplicate.action, "skip")
            # claim di duplicato senza indici: degradato a skip "neutro"
            self.assertEqual(unclaimed_duplicate.reason, "no_durable_knowledge")
            self.assertIsNone(unclaimed_duplicate.error)

            # CAMBIA rispetto a prima (cuore del fix ICH-84): reason di
            # partenza "trivial_or_ephemeral", non "duplicate" — covered_by
            # la sovrascrive comunque.
            stray_indices = evaluate_retain(
                "finestra",
                summary,
                ["http://bank"],
                cfg,
                fake_api(gate_payload(covered_by=[0])),
            )
            self.assertEqual(stray_indices.action, "skip")
            self.assertEqual(stray_indices.reason, "duplicate")
            self.assertEqual(stray_indices.duplicate_of, [0])
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
                fake_api(gate_payload(
                    action=action, reason=reason, preview=preview, context="dominio di prova",
                )),
            )
            self.assertEqual(result.action, action, (action, reason))
            self.assertEqual(result.reason, reason, (action, reason))
            self.assertEqual(result.preview, preview, (action, reason))
            self.assertIsNone(result.error, (action, reason))

        # ICH-84: su uncertain covered_by resta solo osservabilita' (nel
        # GateResult) e non tocca ne' la action ne' duplicate_of, riservato
        # a skip.
        with mock.patch(
            "lib.hindsight_retain_gate.fetch_duplicate_candidates",
            return_value=[{"text": "memoria uno"}],
        ):
            uncertain_with_coverage = evaluate_retain(
                "finestra",
                summary,
                ["http://bank"],
                cfg,
                fake_api(gate_payload(
                    action="uncertain",
                    reason="borderline",
                    preview="Forse salvo Z.",
                    context="dominio di prova",
                    covered_by=[0],
                )),
            )
        self.assertEqual(uncertain_with_coverage.action, "uncertain")
        self.assertEqual(uncertain_with_coverage.duplicate_of, [])

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
        self.assertEqual(calls[0][1]["limit"], 8)
        # ICH-89: solo raw fact come candidati (niente observation di
        # consolidamento) ed entita' spente alla fonte, come nel recall.
        self.assertEqual(calls[0][1]["types"], ["world", "experience"])
        self.assertEqual(calls[0][1]["include"], {"entities": None})

        with mock.patch(
            "lib.hindsight_retain_gate.fetch_bank_results"
        ) as fetch:
            self.assertEqual(fetch_duplicate_candidates(["http://b1"], "", 4), [])
            fetch.assert_not_called()

    def test_dedup_candidate_types_are_raw_facts_only(self):
        """ICH-89: i tipi del filtro sono quelli accettati dall'endpoint recall
        e non includono le observation (layer derivato, senza document_id)."""
        self.assertTrue(set(DEDUP_CANDIDATE_TYPES) <= set(_VALID_RECALL_TYPES))
        self.assertNotIn("observation", DEDUP_CANDIDATE_TYPES)
        self.assertEqual(sorted(DEDUP_CANDIDATE_TYPES), ["experience", "world"])

    def test_complete_documents_fills_cited_documents(self):
        """ICH-88: ogni documento citato dal top-k viene completato coi fatti
        mancanti (id gia' visti e testi normalizzati gia' visti scartati);
        fatti dello stesso documento contigui, documenti in ordine di prima
        apparizione, candidati senza document_id al loro posto."""
        A1 = {"id": "A1", "text": "fatto a1", "document_id": "doc-a"}
        A2 = {"id": "A2", "text": "fatto a2", "document_id": "doc-a"}
        A3 = {"id": "A3", "text": "fatto a3", "document_id": "doc-a"}
        A4 = {"id": "A4", "text": "fatto a4", "document_id": "doc-a"}
        B1 = {"id": "B1", "text": "fatto b1", "document_id": "doc-b"}
        B2 = {"id": "B2", "text": "Fatto B2", "document_id": "doc-b"}
        B2bis = {"id": "B2bis", "text": "fatto   b2", "document_id": "doc-b"}
        N0 = {"id": "N0", "text": "osservazione senza documento"}
        ranked = [("http://b1", A1), ("http://b1", B1), ("http://b1", A2), ("http://b1", N0)]
        calls = []

        def fake_fetch(url, doc_id, timeout):
            calls.append((url, doc_id, timeout))
            return {"doc-a": [A1, A2, A3, A4], "doc-b": [B1, B2, B2bis]}[doc_id]

        out = complete_documents(
            ranked, timeout=4, fetch=fake_fetch, clock=lambda: 0.0
        )
        self.assertEqual(
            [r["id"] for r in out], ["A1", "A2", "A3", "A4", "B1", "B2", "N0"]
        )
        self.assertEqual(
            calls, [("http://b1", "doc-a", 4), ("http://b1", "doc-b", 4)]
        )

    def test_complete_documents_keeps_partial_when_fetch_fails_or_over_cap(self):
        """Fetch None (GET fallita o documento oltre il cap) => il documento
        resta esattamente com'era nel top-k."""
        A1 = {"id": "A1", "text": "fatto a1", "document_id": "doc-a"}
        A2 = {"id": "A2", "text": "fatto a2", "document_id": "doc-a"}
        N0 = {"id": "N0", "text": "osservazione"}
        ranked = [("http://b1", A1), ("http://b1", N0), ("http://b1", A2)]
        out = complete_documents(ranked, timeout=4, fetch=lambda u, d, t: None)
        self.assertEqual(len(out), 3)
        self.assertIs(out[0], A1)
        self.assertIs(out[1], A2)
        self.assertIs(out[2], N0)

    def test_complete_documents_respects_total_budget(self):
        """Tetto totale: gli extra di un documento che sforerebbe non vengono
        aggiunti, ma i documenti successivi che ci stanno vengono completati."""
        A1 = {"id": "A1", "text": "fatto a1", "document_id": "doc-a"}
        B1 = {"id": "B1", "text": "fatto b1", "document_id": "doc-b"}
        B2 = {"id": "B2", "text": "fatto b2", "document_id": "doc-b"}
        full_a = [A1] + [
            {"id": f"A{i}", "text": f"fatto a{i}", "document_id": "doc-a"}
            for i in range(2, 6)
        ]
        ranked = [("http://b1", A1), ("http://b1", B1)]

        def fake_fetch(url, doc_id, timeout):
            return {"doc-a": full_a, "doc-b": [B1, B2]}[doc_id]

        out = complete_documents(ranked, timeout=4, max_total=4, fetch=fake_fetch)
        self.assertEqual([r["id"] for r in out], ["A1", "B1", "B2"])

    def test_complete_documents_uses_origin_bank_per_document(self):
        """Ogni documento viene completato dal bank del suo primo candidato."""
        A1 = {"id": "A1", "text": "fatto a1", "document_id": "doc-a"}
        B1 = {"id": "B1", "text": "fatto b1", "document_id": "doc-b"}
        calls = []

        def fake_fetch(url, doc_id, timeout):
            calls.append((url, doc_id))
            return []

        complete_documents(
            [("http://b1", A1), ("http://b2", B1)], timeout=4, fetch=fake_fetch
        )
        self.assertEqual(calls, [("http://b1", "doc-a"), ("http://b2", "doc-b")])

    def test_fetch_document_facts_get_and_failures(self):
        """GET /memories/list?document_id=...&state=valid&limit=cap+1
        (urlencoded; solo fatti validi); None su eccezione, risposta senza
        items o documento oltre il cap."""

        class FakeListResponse:
            def __init__(self, body):
                self.body = body

            def read(self):
                return json.dumps(self.body).encode("utf-8")

            def __enter__(self):
                return self

            def __exit__(self, *args):
                return False

        with mock.patch(
            "lib.hindsight_retain_gate.urllib.request.urlopen",
            return_value=FakeListResponse(
                {"items": [{"id": "x", "text": "t"}], "total": 1}
            ),
        ) as urlopen:
            out = fetch_document_facts("http://b1", "doc a", timeout=4)
        self.assertEqual(out, [{"id": "x", "text": "t"}])
        request = urlopen.call_args[0][0]
        self.assertEqual(
            request.full_url,
            "http://b1/memories/list?document_id=doc%20a&state=valid&limit="
            + str(DEDUP_DOC_FACTS_CAP + 1),
        )
        self.assertEqual(request.get_method(), "GET")
        self.assertEqual(urlopen.call_args[1]["timeout"], 4)

        too_many = [
            {"id": f"x{i}", "text": f"t{i}"} for i in range(DEDUP_DOC_FACTS_CAP + 1)
        ]
        with mock.patch(
            "lib.hindsight_retain_gate.urllib.request.urlopen",
            return_value=FakeListResponse({"items": too_many}),
        ):
            self.assertIsNone(fetch_document_facts("http://b1", "doc-a", timeout=4))

        with mock.patch(
            "lib.hindsight_retain_gate.urllib.request.urlopen",
            side_effect=OSError("boom"),
        ):
            self.assertIsNone(fetch_document_facts("http://b1", "doc-a", timeout=4))

        with mock.patch(
            "lib.hindsight_retain_gate.urllib.request.urlopen",
            return_value=FakeListResponse({}),
        ):
            self.assertIsNone(fetch_document_facts("http://b1", "doc-a", timeout=4))

        # Pagina incompleta (total oltre gli item ricevuti): il documento non
        # sarebbe intero in vista, resta com'e' nel top-k.
        with mock.patch(
            "lib.hindsight_retain_gate.urllib.request.urlopen",
            return_value=FakeListResponse(
                {"items": [{"id": "x", "text": "t"}], "total": 2}
            ),
        ):
            self.assertIsNone(fetch_document_facts("http://b1", "doc-a", timeout=4))

    def test_complete_documents_budget_rejected_doc_does_not_poison_dedup(self):
        """Un documento rifiutato per budget non e' in vista: i suoi testi non
        devono far scartare i fatti identici di un documento successivo."""
        A1 = {"id": "A1", "text": "fatto a1", "document_id": "doc-a"}
        B1 = {"id": "B1", "text": "fatto b1", "document_id": "doc-b"}
        B2 = {"id": "B2", "text": "testo condiviso", "document_id": "doc-b"}
        a_extra = [
            {"id": f"A{i}", "text": f"fatto a{i}", "document_id": "doc-a"}
            for i in range(2, 7)
        ] + [{"id": "A9", "text": "testo condiviso", "document_id": "doc-a"}]

        def fake_fetch(url, doc_id, timeout):
            return {"doc-a": [A1] + a_extra, "doc-b": [B1, B2]}[doc_id]

        out = complete_documents(
            [("http://b1", A1), ("http://b1", B1)],
            timeout=4,
            max_total=5,
            fetch=fake_fetch,
        )
        self.assertEqual([r["id"] for r in out], ["A1", "B1", "B2"])

    def test_complete_documents_no_doc_candidates_keep_relative_position(self):
        """I candidati senza document_id restano alla loro posizione relativa
        (non vengono raggruppati fra loro)."""
        A1 = {"id": "A1", "text": "fatto a1", "document_id": "doc-a"}
        A2 = {"id": "A2", "text": "fatto a2", "document_id": "doc-a"}
        B1 = {"id": "B1", "text": "fatto b1", "document_id": "doc-b"}
        N0 = {"id": "N0", "text": "osservazione zero", "document_id": None}
        N1 = {"id": "N1", "text": "osservazione uno"}
        ranked = [("http://b1", A1), ("http://b1", N0), ("http://b1", B1), ("http://b1", N1)]
        calls = []

        def fake_fetch(url, doc_id, timeout):
            calls.append(doc_id)
            return {"doc-a": [A1, A2], "doc-b": [B1]}[doc_id]

        out = complete_documents(ranked, timeout=4, fetch=fake_fetch)
        self.assertEqual([r["id"] for r in out], ["A1", "A2", "N0", "B1", "N1"])
        self.assertEqual(calls, ["doc-a", "doc-b"])

        # id None ripetuti fra gli extra: dedup solo per testo, non per id.
        x1 = {"id": None, "text": "extra uno", "document_id": "doc-a"}
        x2 = {"id": None, "text": "extra due", "document_id": "doc-a"}
        out = complete_documents(
            [("http://b1", A1)], timeout=4, fetch=lambda u, d, t: [A1, x1, x2]
        )
        self.assertEqual([r["text"] for r in out], ["fatto a1", "extra uno", "extra due"])

    def test_complete_documents_shared_deadline_caps_fetch_timeout(self):
        """Ogni GET riceve min(residuo della deadline, DEDUP_DOC_FETCH_TIMEOUT);
        a deadline scaduta i documenti restanti non vengono completati."""
        A1 = {"id": "A1", "text": "fatto a1", "document_id": "doc-a"}
        B1 = {"id": "B1", "text": "fatto b1", "document_id": "doc-b"}
        C1 = {"id": "C1", "text": "fatto c1", "document_id": "doc-c"}
        ranked = [("http://b1", A1), ("http://b1", B1), ("http://b1", C1)]
        ticks = iter([0.0, 0.0, 12.0, 20.0])
        calls = []

        def fake_fetch(url, doc_id, timeout):
            calls.append((doc_id, timeout))
            return []

        out = complete_documents(
            ranked, timeout=15, fetch=fake_fetch, clock=lambda: next(ticks)
        )
        self.assertEqual([r["id"] for r in out], ["A1", "B1", "C1"])
        self.assertEqual(calls, [("doc-a", 5.0), ("doc-b", 3.0)])

    def test_fetch_duplicate_candidates_completes_documents_after_top_k(self):
        """Dopo il top-k tra bank, ogni documento in vista viene completato
        dal bank di provenienza (ICH-88)."""
        A1 = {"id": "A1", "text": "fatto a1", "document_id": "doc-a"}
        A2 = {"id": "A2", "text": "fatto a2", "document_id": "doc-a"}
        B1 = {"id": "B1", "text": "fatto b1", "document_id": "doc-b"}
        C1 = {"id": "C1", "text": "fatto c1", "document_id": "doc-c"}
        C2 = {"id": "C2", "text": "fatto c2", "document_id": "doc-c"}
        calls = []

        def fake_bank(url, payload, timeout):
            return {"http://b1": [A1, B1], "http://b2": [C1]}[url]

        def fake_docs(url, doc_id, timeout):
            calls.append((url, doc_id))
            return {"doc-a": [A1, A2], "doc-b": [B1], "doc-c": [C1, C2]}[doc_id]

        with mock.patch(
            "lib.hindsight_retain_gate.fetch_bank_results", side_effect=fake_bank
        ), mock.patch(
            "lib.hindsight_retain_gate.fetch_document_facts", side_effect=fake_docs
        ):
            out = fetch_duplicate_candidates(["http://b1", "http://b2"], "q", timeout=4)
        self.assertEqual([r["id"] for r in out], ["A1", "A2", "B1", "C1", "C2"])
        self.assertEqual(
            calls, [("http://b1", "doc-a"), ("http://b1", "doc-b"), ("http://b2", "doc-c")]
        )

    def test_schema_and_enums_consistent(self):
        self.assertEqual(set(GATE_SCHEMA["properties"]["action"]["enum"]), GATE_ACTIONS)
        self.assertEqual(set(GATE_SCHEMA["properties"]["reason"]["enum"]), GATE_REASONS)
        self.assertNotIn("gate_error", GATE_REASONS)  # sentinella solo fail-closed
        # La mappa reason->action e' esplicita anche nel prompt: ogni action e
        # ogni reason del validatore devono comparirvi (niente drift silenzioso).
        for name in sorted(GATE_ACTIONS | GATE_REASONS):
            self.assertIn(name, GATE_PROMPT, name)
        # ICH-84: idem per i nomi dei campi dello schema (durable_claims,
        # covered_by compresi) — niente drift silenzioso tra schema e prompt.
        for prop in GATE_SCHEMA["properties"]:
            self.assertIn(prop, GATE_PROMPT, prop)
        self.assertNotIn("duplicate_of", GATE_SCHEMA["properties"])

    def test_coverage_outranks_other_skip_reasons(self):
        """covered_by non vuoto forza reason="duplicate" su skip, qualunque
        sia la reason dichiarata dal modello (ICH-84: e' li' che il bench
        ICH-72 perdeva i duplicati etichettati con altre reason)."""
        cfg = {"retain_gate_model": "m", "retain_gate_timeout": 5}
        summary = {"turns": []}
        candidates = [{"text": "memoria uno"}, {"text": "memoria due"}]
        with mock.patch(
            "lib.hindsight_retain_gate.fetch_duplicate_candidates",
            return_value=candidates,
        ):
            for reason in (
                "repo_recoverable",
                "no_durable_knowledge",
                "intermediate_attempt",
                "trivial_or_ephemeral",
            ):
                result = evaluate_retain(
                    "finestra",
                    summary,
                    ["http://bank"],
                    cfg,
                    fake_api(gate_payload(reason=reason, covered_by=[1])),
                )
                self.assertEqual(result.reason, "duplicate", reason)
                self.assertEqual(result.duplicate_of, [1], reason)
                self.assertIsNone(result.error, reason)

    def test_coverage_never_flips_the_action(self):
        cfg = {"retain_gate_model": "m", "retain_gate_timeout": 5}
        summary = {"turns": []}
        candidates = [{"text": "memoria uno"}]
        cases = (
            ("retain", "durable_decision", "Salvo X."),
            ("uncertain", "borderline", "Forse salvo X."),
        )
        with mock.patch(
            "lib.hindsight_retain_gate.fetch_duplicate_candidates",
            return_value=candidates,
        ):
            for action, reason, preview in cases:
                result = evaluate_retain(
                    "finestra",
                    summary,
                    ["http://bank"],
                    cfg,
                    fake_api(gate_payload(
                        action=action, reason=reason, preview=preview, covered_by=[0],
                    )),
                )
                self.assertEqual(result.action, action, (action, reason))
                self.assertEqual(result.duplicate_of, [], (action, reason))
                self.assertEqual(result.covered_by, [0], (action, reason))
                self.assertIsNone(result.error, (action, reason))

    def test_durable_claims_preserved_in_result(self):
        cfg = {"retain_gate_model": "m", "retain_gate_timeout": 5}
        summary = {"turns": []}
        claims = ["il bank X va interrogato prima di Y"]
        result = evaluate_retain(
            "finestra", summary, [], cfg, fake_api(gate_payload(durable_claims=claims))
        )
        self.assertEqual(result.durable_claims, claims)

    def test_schema_field_order_puts_coverage_before_action(self):
        self.assertEqual(
            list(GATE_SCHEMA["properties"])[:3], ["durable_claims", "covered_by", "action"]
        )

    def test_prompt_states_coverage_precedence(self):
        self.assertIn("durable_claims", GATE_PROMPT)
        self.assertIn("covered_by", GATE_PROMPT)
        self.assertIn("A covered window is a duplicate", GATE_PROMPT)
        self.assertNotIn("duplicate_of", GATE_PROMPT)

    def test_check_stub_verdict_covers_schema_required_fields(self):
        """Lo stub e2e di hindsight-check.sh fabbrica la risposta del gate:
        se perde un campo required il gate reale va in gate_error fail-closed
        e la diagnostica riporta KO permanente (review ICH-84). Il confronto
        e' strutturale sul dict del VERDICT (non testuale sull'intero script):
        con additionalProperties false anche un campo di troppo e' fatale."""
        script = (
            Path(__file__).resolve().parent / "tools" / "hindsight-check.sh"
        ).read_text(encoding="utf-8")
        match = re.search(r"VERDICT = json\.dumps\((\{.*?\})\)", script, re.S)
        self.assertIsNotNone(match, "blocco VERDICT non trovato nello stub")
        verdict = ast.literal_eval(match.group(1))
        self.assertEqual(set(verdict), set(GATE_SCHEMA["required"]))

    def test_empty_candidates_force_empty_coverage(self):
        """Contratto esplicito del caso "nessuna memoria fornita": con 0
        candidati qualunque indice in covered_by e' fuori range."""
        cfg = {"retain_gate_model": "m", "retain_gate_timeout": 5}
        summary = {"turns": []}
        result = evaluate_retain(
            "finestra", summary, [], cfg,
            fake_api(gate_payload(reason="duplicate", covered_by=[0])),
        )
        self.assertEqual(result.reason, "gate_error")
        self.assertIsNotNone(result.error)


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

    def test_post_failure_reports_error_and_restores_pending(self):
        self.assertTrue(self.save(context=""))
        with mock.patch(
            "lib.hindsight_retain_gate.urllib.request.urlopen",
            side_effect=OSError("connection refused"),
        ):
            outcome = handle_retain_consent("si", "sess-consent", "/proj")
        self.assertEqual(outcome["action"], "error")
        self.assertIn("OSError", outcome["error"])
        self.assertEqual(outcome["preview"], "Salvo la decisione X.")
        # Il pending consumato viene rimesso in attesa: un secondo "si'"
        # riprova la POST (qui con la rete tornata) invece di trovare il vuoto.
        # Il context risolto al primo tentativo (qui il fallback repo/branch,
        # ma vale anche per la proposta letta dal transcript) viaggia col
        # pending ripristinato: al retry e' gia' nell'item, senza dipendere da
        # un transcript nel frattempo cambiato.
        self.assertTrue(outcome["restored"])
        retry, posted = self.consent("si")
        self.assertEqual(retry["action"], "saved")
        self.assertEqual(retry["context_source"], "gate")
        self.assertEqual(posted["context"], "sessione Claude Code")
        self.assertEqual(posted["content"], "finestra")
        # e il ripristino e' a consumo singolo come l'originale
        self.assertIsNone(handle_retain_consent("si", "sess-consent", "/proj"))

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


ASK_LAST = "as the very last thing in your reply, ask the user verbatim"


class WorkerGateTests(unittest.TestCase):
    """Worker in modalita' "deferred" (ICH-86: valutazione a UserPromptSubmit
    dell'entry accodata dallo Stop). L'output e' il dict ritornato da
    evaluate(); non esiste piu' decision:block, la domanda viaggia in
    hookSpecificOutput.additionalContext e va posta in coda alla risposta."""

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
        self.hook = {
            "session_id": "sess-gate-test",
            "transcript_path": transcript,
            "cwd": self.tmp.name,
            "hook_event_name": "UserPromptSubmit",
        }
        self.hook_input = json.dumps(self.hook)

        env = {
            "HS_RETAIN_STATE_DIR": self.tmp.name,
            "HS_RETAIN_PENDING_DIR": os.path.join(self.tmp.name, "pending"),
            "HS_RETAIN_QUEUE_DIR": os.path.join(self.tmp.name, "queue"),
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

    def run_main(self, cfg, gate_result, mode="deferred", hook=None):
        """evaluate(hook, mode) con gate e POST mockati:
        (rc, hook_output o None, gate_mock, urlopen)."""
        gate_mock = mock.Mock(return_value=gate_result)
        with mock.patch.object(self.worker, "CFG", cfg), mock.patch.object(
            self.worker, "evaluate_retain", gate_mock
        ), mock.patch("urllib.request.urlopen", return_value=FakeResponse()) as urlopen:
            with redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
                rc, out = self.worker.evaluate(hook or self.hook, mode)
        return rc, out, gate_mock, urlopen

    @staticmethod
    def context_of(out: dict) -> str:
        assert "decision" not in out, out
        hso = out["hookSpecificOutput"]
        assert hso["hookEventName"] == "UserPromptSubmit", hso
        return hso["additionalContext"]

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
        self.assertIsNone(out)  # nessuna notifica: silenzioso
        item = json.loads(urlopen.call_args[0][0].data.decode("utf-8"))["items"][0]
        # context descrittivo dal gate; niente header volatile nel content
        self.assertEqual(item["context"], "convenzioni di branching nel progetto di prova")
        self.assertTrue(item["content"].startswith("## Conversation (recent turns)"))
        self.assertNotIn("Session:", item["content"])
        self.assertNotIn("CWD:", item["content"])

    def test_retain_without_context_asks_context_in_additional_context(self):
        # retain SENZA context: niente POST diretta e niente fallback LLM (ICH-73):
        # pending + istruzione nascosta, Claude propone un context e chiede
        # conferma IN CODA alla risposta al prompt corrente (ICH-86).
        rc, out, _gate, urlopen = self.run_main(
            self.cfg(),
            GateResult(
                action="retain", reason="durable_decision", preview="Salvo X.", context=""
            ),
        )
        self.assertEqual(rc, 0)
        urlopen.assert_not_called()
        instruction = self.context_of(out)
        self.assertIn(
            "Salvo questa memoria con context «<PROPOSTA>»? (sì / no / context: …)",
            instruction,
        )
        self.assertIn("Salvo X.", instruction)
        self.assertIn(ASK_LAST, instruction)
        self.assertIn("Answer the current prompt normally first", instruction)
        # Visibile per costruzione (systemMessage nel terminale), anche se
        # Claude omettesse la domanda: preview + come rispondere; la proposta
        # del context la fa Claude, quindi qui non c'e' nessun «<PROPOSTA>».
        self.assertIn("il gate propone di salvare — Salvo X", out["systemMessage"])
        self.assertIn("sì / no / `context: …`", out["systemMessage"])
        self.assertNotIn("<PROPOSTA>", out["systemMessage"])

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
        instruction = self.context_of(out)
        # La preview finisce col punto: nella domanda fusa non deve raddoppiare.
        self.assertIn(
            f"Vuoi che salvi questa memoria? — {preview.rstrip('.')}. "
            "Context proposto: «<PROPOSTA>» (sì / no / context: …)",
            instruction,
        )
        self.assertNotIn("..", instruction.replace("…", ""))
        self.assertIn(ASK_LAST, instruction)

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
        self.assertNotIn("decision", out)
        self.assertIn("## Hindsight retain debug", out["systemMessage"])
        self.assertIn("retain (durable_decision)", out["systemMessage"])
        self.assertEqual(out["hookSpecificOutput"]["hookEventName"], "UserPromptSubmit")

    def test_skip_saves_nothing(self):
        rc, out, _gate, urlopen = self.run_main(
            self.cfg(), GateResult(action="skip", reason="repo_recoverable")
        )
        self.assertEqual(rc, 0)
        urlopen.assert_not_called()
        self.assertIsNone(out)

    def test_gate_error_is_fail_closed_with_rollback_and_notice(self):
        cfg = self.cfg(retain_every_n_turns=3)
        gate_error = GateResult(action="skip", reason="gate_error", error="TimeoutError: x")
        # 1a e 2a valutazione: throttling, il gate non viene nemmeno chiamato.
        for _ in range(2):
            rc, out, gate_mock, urlopen = self.run_main(cfg, gate_error)
            self.assertEqual(rc, 0)
            gate_mock.assert_not_called()
            urlopen.assert_not_called()
            self.assertIsNone(out)
        # 3a: gate chiamato -> errore tecnico -> FAIL-CLOSED: nessuna POST,
        # systemMessage non bloccante, rollback del contatore.
        rc, out, gate_mock, urlopen = self.run_main(cfg, gate_error)
        self.assertEqual(rc, 0)
        self.assertEqual(gate_mock.call_count, 1)
        urlopen.assert_not_called()
        self.assertNotIn("decision", out)  # notifica, non block
        self.assertIn("errore tecnico del gate", out["systemMessage"])
        self.assertIn("TimeoutError: x", out["systemMessage"])
        self.assertIn("il prossimo turno riprova", out["systemMessage"])
        entry = self.read_state()["sess-gate-test"]
        self.assertEqual(entry["stop_count"], 2)  # 3 -> 2: la prossima rivaluta
        self.assertIs(entry["gate_error_notified"], True)
        # 4a: il contatore torna a 3 -> gate CHIAMATO di nuovo (rollback
        # efficace); stesso errore -> nessuna seconda notifica nella sessione.
        rc, out, gate_mock, urlopen = self.run_main(cfg, gate_error)
        self.assertEqual(rc, 0)
        self.assertEqual(gate_mock.call_count, 1)
        urlopen.assert_not_called()
        self.assertIsNone(out)
        self.assertEqual(self.read_state()["sess-gate-test"]["stop_count"], 2)

    def test_gate_error_debug_still_emits_notice(self):
        rc, out, _gate, urlopen = self.run_main(
            self.cfg(retain_debug_in_context=True),
            GateResult(action="skip", reason="gate_error", error="TimeoutError: x"),
        )
        self.assertEqual(rc, 0)
        urlopen.assert_not_called()
        self.assertNotIn("decision", out)
        message = out["systemMessage"]
        self.assertIn("errore tecnico del gate", message)  # notifica fail-closed
        self.assertIn("## Hindsight retain debug", message)  # + blocco debug
        self.assertIn("fail-closed", message)
        self.assertIn("## Hindsight retain debug", self.context_of(out))

    def test_uncertain_asks_and_saves_pending(self):
        preview = "Vale la pena salvare la decisione sul gate?"
        rc, out, _gate, urlopen = self.run_main(
            self.cfg(),
            GateResult(
                action="uncertain", reason="borderline", preview=preview, context="dominio"
            ),
        )
        self.assertEqual(rc, 0)
        urlopen.assert_not_called()
        instruction = self.context_of(out)
        # uncertain CON context: la domanda classica resta identica (niente
        # proposta di context, ICH-73 tocca solo il caso context vuoto).
        self.assertIn(f"Vuoi che salvi questa memoria? — {preview} (sì/no)", instruction)
        self.assertNotIn("<PROPOSTA>", instruction)
        self.assertIn(ASK_LAST, instruction)
        self.assertIn("end the turn", instruction)
        # La stessa domanda anche in systemMessage: visibile nel terminale a
        # prescindere da Claude (additionalContext e' consultivo).
        self.assertEqual(
            out["systemMessage"],
            f"Hindsight: Vuoi che salvi questa memoria? — {preview} (sì/no)",
        )

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
        self.assertIn(preview, self.context_of(out))

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
            with redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
                self.assertEqual(self.worker.evaluate(self.hook, "deferred"), (0, None))
                self.assertEqual(self.worker.evaluate(self.hook, "deferred"), (0, None))

        self.assertEqual(len(payloads), 2)
        first, second = (p["items"][0] for p in payloads)
        self.assertEqual(first["document_id"], second["document_id"])
        self.assertTrue(first["document_id"].startswith("sess-gate-test-"))
        # Senza header volatile il content e' identico sui replay: stesso id.
        self.assertEqual(first["content"], second["content"])

        # Un prompt user in coda SENZA risposta (= il prompt appena inviato a
        # UserPromptSubmit) non fa parte del turno completato: stessa finestra,
        # stesso id (ICH-86, drop_unanswered_tail).
        with open(self.transcript, "a", encoding="utf-8") as handle:
            handle.write(
                json.dumps(user_record("un altro prompt che cambia la finestra del retain"))
                + "\n"
            )
        with mock.patch.object(self.worker, "CFG", cfg), mock.patch.object(
            self.worker, "evaluate_retain", return_value=gate
        ), mock.patch("urllib.request.urlopen", side_effect=capture):
            with redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
                self.assertEqual(self.worker.evaluate(self.hook, "deferred"), (0, None))
        self.assertEqual(payloads[2]["items"][0]["document_id"], first["document_id"])

        # Turno completato (prompt + risposta): la finestra cambia, id diverso.
        with open(self.transcript, "a", encoding="utf-8") as handle:
            handle.write(json.dumps(assistant_record("Fatto, finestra nuova.")) + "\n")
        with mock.patch.object(self.worker, "CFG", cfg), mock.patch.object(
            self.worker, "evaluate_retain", return_value=gate
        ), mock.patch("urllib.request.urlopen", side_effect=capture):
            with redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
                self.assertEqual(self.worker.evaluate(self.hook, "deferred"), (0, None))
        self.assertNotEqual(payloads[3]["items"][0]["document_id"], first["document_id"])

    # --- ICH-86: coda, drain, evaluate_queued ------------------------------

    def enqueue(self, hook: dict, name: str) -> str:
        """Scrive un'entry di coda come farebbe lo Stop hook (HOOK_INPUT verbatim).
        name = "<EPOCHREALTIME senza punto>-<pid>" (ordina per istante)."""
        queue_dir = self.worker.retain_queue_dir()
        os.makedirs(queue_dir, exist_ok=True)
        path = os.path.join(queue_dir, name + ".json")
        with open(path, "w", encoding="utf-8") as handle:
            handle.write(json.dumps(hook))
        return path

    def queue_names(self) -> list[str]:
        """Nomi delle ENTRY di coda (gli outbox *.out.json della stessa dir
        non sono entry: si controllano a parte con outbox())."""
        queue_dir = self.worker.retain_queue_dir()
        if not os.path.isdir(queue_dir):
            return []
        return sorted(n for n in os.listdir(queue_dir) if not n.endswith(".out.json"))

    def test_drop_unanswered_tail(self):
        drop = self.worker.drop_unanswered_tail
        u1, a1 = user_record("prima domanda"), assistant_record("prima risposta")
        u2, a2 = user_record("seconda domanda"), assistant_record("seconda risposta")
        reminder = user_record("<system-reminder>nota</system-reminder>")
        # transcript "da Stop": finisce con l'assistant -> invariato
        self.assertEqual(drop([u1, a1, u2, a2]), [u1, a1, u2, a2])
        # transcript "da UserPromptSubmit": il prompt nuovo (e i suoi wrapper
        # system-reminder, ruolo user) in coda vengono tolti
        self.assertEqual(drop([u1, a1, u2, a2, u1]), [u1, a1, u2, a2])
        self.assertEqual(drop([u1, a1, u2, a2, reminder, u1]), [u1, a1, u2, a2])
        # tool_result (ruolo user senza testo) in coda: tolto anche lui
        tool_result = {
            "type": "user",
            "message": {
                "role": "user",
                "content": [{"type": "tool_result", "content": "output"}],
            },
        }
        self.assertEqual(drop([u1, a1, tool_result]), [u1, a1])
        # record non-user dopo l'ultimo assistant (es. summary) restano
        summary = {"type": "summary", "summary": "riassunto"}
        self.assertEqual(drop([u1, a1, summary, u2]), [u1, a1, summary])
        # nessun assistant = nessun turno completato; transcript vuoto
        self.assertEqual(drop([u1]), [])
        self.assertEqual(drop([u1, reminder]), [])
        self.assertEqual(drop([]), [])
        # ruolo derivato da type quando message manca
        self.assertEqual(
            drop([{"type": "user"}, {"type": "assistant"}, {"type": "user"}]),
            [{"type": "user"}, {"type": "assistant"}],
        )

    def test_dequeue_picks_newest_and_deletes_only_that_session(self):
        old = dict(self.hook, marker="old")
        new = dict(self.hook, marker="new")
        other = dict(self.hook, session_id="sess-other", marker="other")
        self.enqueue(old, "1700000000100000-11")
        self.enqueue(other, "1700000000200000-12")
        self.enqueue(new, "1700000000300000-13")
        entry = self.worker.dequeue_for_session("sess-gate-test")
        self.assertEqual(entry["marker"], "new")
        # tutte le entry della sessione sparite, l'altra sessione intatta
        self.assertEqual(self.queue_names(), ["1700000000200000-12.json"])
        self.assertIsNone(self.worker.dequeue_for_session("sess-gate-test"))
        self.assertIsNone(self.worker.dequeue_for_session(""))
        self.assertEqual(self.queue_names(), ["1700000000200000-12.json"])
        # coda inesistente: None senza errori
        with mock.patch.dict(
            os.environ, {"HS_RETAIN_QUEUE_DIR": os.path.join(self.tmp.name, "nope")}
        ):
            self.assertIsNone(self.worker.dequeue_for_session("sess-gate-test"))

    def test_dequeue_handles_unparsable_entries(self):
        queue_dir = self.worker.retain_queue_dir()
        os.makedirs(queue_dir, exist_ok=True)
        stale = os.path.join(queue_dir, "1700000000000000-1.json")
        young = os.path.join(queue_dir, "1700000000500000-2.json")
        for path in (stale, young):
            with open(path, "w", encoding="utf-8") as handle:
                handle.write('{"session_id": "sess-gate-test", "trunc')
        os.utime(stale, (time.time() - 120, time.time() - 120))  # vecchia: via
        self.enqueue(self.hook, "1700000000400000-3")
        entry = self.worker.dequeue_for_session("sess-gate-test")
        self.assertEqual(entry["session_id"], "sess-gate-test")
        # la illeggibile vecchia e' stata cancellata, la giovane (forse in
        # scrittura) e' rimasta
        self.assertEqual(self.queue_names(), ["1700000000500000-2.json"])

    def test_drain_queue_one_per_session_and_empties(self):
        a_old = dict(self.hook, marker="a-old")
        a_new = dict(self.hook, marker="a-new")
        b = dict(self.hook, session_id="sess-b", marker="b")
        no_sid = {"transcript_path": self.transcript, "marker": "no-sid"}
        no_sid2 = {"transcript_path": self.transcript, "marker": "no-sid-2"}
        self.enqueue(a_old, "1700000000100000-1")
        self.enqueue(b, "1700000000200000-2")
        self.enqueue(no_sid, "1700000000250000-2")
        self.enqueue(a_new, "1700000000300000-3")
        self.enqueue(no_sid2, "1700000000350000-2")
        entries = self.worker.drain_queue()
        self.assertEqual(
            sorted(e["marker"] for e in entries), ["a-new", "b", "no-sid", "no-sid-2"]
        )
        self.assertEqual(self.queue_names(), [])
        self.assertEqual(self.worker.drain_queue(), [])

    def test_evaluate_queued_consumes_and_returns_output(self):
        preview = "Vale la pena salvare la decisione sul gate?"
        gate = GateResult(action="uncertain", reason="borderline", preview=preview, context="dominio")
        self.enqueue(self.hook, "1700000000100000-1")
        with mock.patch.object(self.worker, "CFG", self.cfg()), mock.patch.object(
            self.worker, "evaluate_retain", return_value=gate
        ), mock.patch("urllib.request.urlopen", return_value=FakeResponse()) as urlopen:
            with redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
                out = self.worker.evaluate_queued("sess-gate-test")
        urlopen.assert_not_called()
        self.assertIn(f"Vuoi che salvi questa memoria? — {preview} (sì/no)", self.context_of(out))
        self.assertEqual(self.queue_names(), [])
        # niente in coda: None, nessuna valutazione
        with mock.patch.object(self.worker, "evaluate") as evaluate:
            self.assertIsNone(self.worker.evaluate_queued("sess-gate-test"))
            evaluate.assert_not_called()

    def test_evaluate_queued_retain_disabled_deletes_queue_without_work(self):
        self.enqueue(self.hook, "1700000000100000-1")
        with mock.patch.object(
            self.worker, "CFG", self.cfg(retain_enabled=False)
        ), mock.patch.object(self.worker, "evaluate_retain") as gate, mock.patch.object(
            self.worker, "load_transcript"
        ) as load, mock.patch("urllib.request.urlopen") as urlopen:
            with redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
                self.assertIsNone(self.worker.evaluate_queued("sess-gate-test"))
        gate.assert_not_called()
        load.assert_not_called()
        urlopen.assert_not_called()
        self.assertEqual(self.queue_names(), [])

    def test_evaluate_queued_swallows_exceptions(self):
        self.enqueue(self.hook, "1700000000100000-1")
        with mock.patch.object(
            self.worker, "evaluate", side_effect=RuntimeError("boom")
        ):
            self.assertIsNone(self.worker.evaluate_queued("sess-gate-test"))
        self.assertEqual(self.queue_names(), [])  # consumata comunque
        with mock.patch.object(
            self.worker, "dequeue_for_session", side_effect=OSError("disk")
        ):
            self.assertIsNone(self.worker.evaluate_queued("sess-gate-test"))

    def test_drain_uncertain_skips_without_pending_or_post(self):
        rc, out, gate_mock, urlopen = self.run_main(
            self.cfg(),
            GateResult(action="uncertain", reason="borderline", preview="Forse X.", context="dominio"),
            mode="drain",
        )
        self.assertEqual(rc, 0)
        self.assertIsNone(out)
        self.assertEqual(gate_mock.call_count, 1)
        urlopen.assert_not_called()
        self.assertFalse(os.path.isdir(os.path.join(self.tmp.name, "pending")))
        # e nemmeno un "si" al prompt dopo trova nulla
        self.assertIsNone(handle_retain_consent("si", "sess-gate-test", self.tmp.name))

    def test_drain_retain_without_context_posts_with_fallback(self):
        with mock.patch.object(
            self.worker,
            "git_info",
            return_value={"repo": "Trinity", "branch": "main", "commit": "abc"},
        ):
            rc, out, _gate, urlopen = self.run_main(
                self.cfg(),
                GateResult(action="retain", reason="durable_decision", preview="Salvo X.", context=""),
                mode="drain",
            )
        self.assertEqual(rc, 0)
        self.assertIsNone(out)
        self.assertEqual(urlopen.call_count, 1)
        item = json.loads(urlopen.call_args[0][0].data.decode("utf-8"))["items"][0]
        self.assertEqual(item["context"], "sessione Claude Code nel repo Trinity, branch main")
        self.assertIn("document_id", item)
        self.assertFalse(os.path.isdir(os.path.join(self.tmp.name, "pending")))

    def test_drain_forces_past_throttling_and_gate_error_is_silent(self):
        cfg = self.cfg(retain_every_n_turns=3)
        retain = GateResult(action="retain", reason="durable_decision", preview="x", context="dominio")
        # in deferred la 1a valutazione e' throttlata...
        rc, out, gate_mock, urlopen = self.run_main(cfg, retain)
        gate_mock.assert_not_called()
        urlopen.assert_not_called()
        # ...in drain no: gate chiamato e POST fatta, contatore fermo
        rc, out, gate_mock, urlopen = self.run_main(cfg, retain, mode="drain")
        self.assertEqual((rc, out), (0, None))
        self.assertEqual(gate_mock.call_count, 1)
        self.assertEqual(urlopen.call_count, 1)
        self.assertEqual(self.read_state()["sess-gate-test"]["stop_count"], 1)
        # errore del gate in drain: skip silenzioso, niente notifica ne' rollback
        rc, out, gate_mock, urlopen = self.run_main(
            cfg, GateResult(action="skip", reason="gate_error", error="TimeoutError: x"), mode="drain"
        )
        self.assertEqual((rc, out), (0, None))
        urlopen.assert_not_called()
        state = self.read_state()["sess-gate-test"]
        self.assertEqual(state["stop_count"], 1)
        self.assertNotIn("gate_error_notified", state)

    def test_main_drain_evaluates_each_entry_best_effort(self):
        self.enqueue(self.hook, "1700000000100000-1")
        self.enqueue(dict(self.hook, session_id="sess-b"), "1700000000200000-2")
        seen = []

        def fake_evaluate(entry, mode):
            seen.append((entry["session_id"], mode))
            if entry["session_id"] == "sess-gate-test":
                raise RuntimeError("boom")
            return 0, None

        stderr = io.StringIO()
        with mock.patch.object(self.worker, "evaluate", side_effect=fake_evaluate):
            with redirect_stdout(io.StringIO()), redirect_stderr(stderr):
                self.assertEqual(self.worker.main(["--drain"]), 0)
        self.assertIn("drain error: RuntimeError: boom", stderr.getvalue())
        self.assertEqual(seen, [("sess-gate-test", "drain"), ("sess-b", "drain")])
        self.assertEqual(self.queue_names(), [])

    def test_main_default_prints_hsgate_line(self):
        preview = "Vale la pena salvare la decisione sul gate?"
        gate = GateResult(action="uncertain", reason="borderline", preview=preview, context="dominio")
        stdout, stderr = io.StringIO(), io.StringIO()
        with mock.patch.object(self.worker, "CFG", self.cfg()), mock.patch.object(
            self.worker, "evaluate_retain", return_value=gate
        ), mock.patch("urllib.request.urlopen", return_value=FakeResponse()):
            with redirect_stdout(stdout), redirect_stderr(stderr):
                self.assertEqual(self.worker.main([]), 0)
        # stdout e' ESATTAMENTE la riga HSGATE: i log '[retain]' vanno su stderr
        # (il worker e' importato dall'hook recall, il cui stdout e' il JSON).
        lines = stdout.getvalue().splitlines()
        self.assertEqual(len(lines), 1, lines)
        self.assertTrue(lines[0].startswith("HSGATE "), lines[0])
        out = json.loads(lines[0][len("HSGATE "):])
        self.assertIn(preview, self.context_of(out))
        # la chiave interna asks_consent (protocollo dell'outbox) non esce
        self.assertNotIn("asks_consent", out)

    def test_evaluate_logs_go_to_stderr_not_stdout(self):
        stdout, stderr = io.StringIO(), io.StringIO()
        gate = GateResult(action="retain", reason="durable_decision", preview="x", context="dominio")
        with mock.patch.object(self.worker, "CFG", self.cfg()), mock.patch.object(
            self.worker, "evaluate_retain", return_value=gate
        ), mock.patch("urllib.request.urlopen", return_value=FakeResponse()):
            with redirect_stdout(stdout), redirect_stderr(stderr):
                self.assertEqual(self.worker.evaluate(self.hook, "deferred"), (0, None))
        self.assertEqual(stdout.getvalue(), "")
        self.assertIn("[retain] OK 200", stderr.getvalue())
        # e anche gli skip (gate/throttling) parlano solo su stderr
        stdout, stderr = io.StringIO(), io.StringIO()
        with mock.patch.object(self.worker, "CFG", self.cfg()), mock.patch.object(
            self.worker, "evaluate_retain", return_value=GateResult(action="skip", reason="repo_recoverable")
        ):
            with redirect_stdout(stdout), redirect_stderr(stderr):
                self.worker.evaluate(self.hook, "deferred")
        self.assertEqual(stdout.getvalue(), "")
        self.assertIn("[retain] skip: gate (repo_recoverable)", stderr.getvalue())

    # --- ICH-86 (WP-D/WP-E): retain_at_prompt = pickup + consenso + gate detached

    def make_pending(self, preview="Vale la pena salvare la decisione sul gate?"):
        """Pending come lo lascia il gate 'uncertain' del worker (stessa POST
        pronta che il si' del prompt successivo esegue)."""
        rc, out, _gate, urlopen = self.run_main(
            self.cfg(),
            GateResult(action="uncertain", reason="borderline", preview=preview, context="dominio"),
        )
        self.assertEqual(rc, 0)
        urlopen.assert_not_called()
        self.assertIn(preview, self.context_of(out))
        return preview

    def fake_spawn(self, spawned: list):
        """Launcher in-process al posto di _spawn_queued (che lancerebbe un
        VERO python detached, fuori dai mock): esegue lo stesso codice del
        figlio — main(["--queued", sid]) -> evaluate_queued -> outbox — in un
        thread, cosi' i test restano ermetici e veloci ma il protocollo
        dell'outbox e' quello reale. Ritorna il thread (join nel chiamante).
        La lista `spawned` raccoglie (session_id, log_path) per le asserzioni."""
        worker = self.worker

        def _spawn(session_id, log_path):
            spawned.append((session_id, log_path))
            thread = threading.Thread(
                target=worker.main, args=(["--queued", session_id],), daemon=True
            )
            thread.start()
            return thread

        return _spawn

    def at_prompt(self, prompt, inspect, cfg=None, gate_result=None, urlopen_effect=None):
        """retain_at_prompt con gate, POST e launcher mockati: (result,
        gate_mock, urlopen). `inspect(result, gate_mock, urlopen)` gira DENTRO
        il contesto dei patch e prima del join: il gate (fake_spawn) corre in
        un thread e legge CFG / evaluate_retain del modulo al momento della
        chiamata, e la tmp dir deve sopravvivergli. gate_result puo' essere
        un GateResult o una funzione. result.spawned = [(sid, log_path), …]."""
        gate_result = gate_result or GateResult(
            action="retain", reason="durable_decision", preview="Salvo X.", context="dominio"
        )
        if callable(gate_result):
            gate_mock = mock.Mock(side_effect=gate_result)
        else:
            gate_mock = mock.Mock(return_value=gate_result)
        urlopen_kwargs = (
            {"side_effect": urlopen_effect} if urlopen_effect else {"return_value": FakeResponse()}
        )
        spawned: list = []
        stdout = io.StringIO()
        with mock.patch.object(self.worker, "CFG", cfg or self.cfg()), mock.patch.object(
            self.worker, "evaluate_retain", gate_mock
        ), mock.patch.object(
            self.worker, "_spawn_queued", self.fake_spawn(spawned)
        ), mock.patch("urllib.request.urlopen", **urlopen_kwargs) as urlopen:
            with redirect_stdout(stdout), redirect_stderr(io.StringIO()):
                result = self.worker.retain_at_prompt(
                    prompt, "sess-gate-test", self.tmp.name, self.transcript
                )
                result.spawned = spawned
                inspect(result, gate_mock, urlopen)
                if result._proc is not None:
                    result._proc.join(timeout=10)
                    self.assertFalse(result._proc.is_alive())
        self.assertEqual(result.launched, bool(spawned))
        # niente su stdout nemmeno col gate in corso (lo stdout e' del JSON
        # dell'hook recall)
        self.assertEqual(stdout.getvalue(), "")
        return result, gate_mock, urlopen

    def outbox(self) -> str:
        return self.worker.outbox_path("sess-gate-test")

    def test_retain_at_prompt_no_pending_runs_gate_and_output_is_idempotent(self):
        preview = "Vale la pena salvare la decisione sul gate?"
        self.enqueue(self.hook, "1700000000100000-1")
        seen = {}

        def inspect(result, gate_mock, urlopen):
            self.assertIsNone(result.outcome)
            self.assertEqual(result.consent_output, {})
            self.assertEqual(result.notice, "")
            self.assertFalse(result.saved)
            self.assertFalse(result.stop_here)
            self.assertTrue(result.launched)
            out = result.gate_output(time.monotonic() + 10)
            self.assertIn(f"Vuoi che salvi questa memoria? — {preview} (sì/no)", self.context_of(out))
            self.assertIn(ASK_LAST, self.context_of(out))
            # la chiave interna asks_consent non esce mai verso l'hook
            self.assertNotIn("asks_consent", out)
            # l'outbox e' stato consumato dal polling: niente da raccogliere dopo
            self.assertFalse(os.path.exists(self.outbox()))
            # idempotente: seconda chiamata = stesso dict, nessuna nuova attesa
            self.assertIs(result.gate_output(time.monotonic() + 10), out)
            self.assertIs(result.gate_output(time.monotonic() - 10), out)
            seen["out"] = out

        result, gate_mock, urlopen = self.at_prompt(
            "un prompt qualunque che non e' un consenso",
            inspect,
            gate_result=GateResult(action="uncertain", reason="borderline", preview=preview, context="dominio"),
        )
        self.assertEqual(gate_mock.call_count, 1)
        urlopen.assert_not_called()
        self.assertEqual(self.queue_names(), [])  # entry consumata dal figlio
        self.assertTrue(seen)
        # il launcher riceve la sessione e il log sotto cache_dir()
        self.assertEqual(len(result.spawned), 1)
        self.assertEqual(result.spawned[0][0], "sess-gate-test")
        self.assertTrue(result.spawned[0][1].endswith("hs-retain.log"))

    def test_retain_at_prompt_consent_saved_and_gate_still_runs(self):
        preview = self.make_pending()
        self.enqueue(self.hook, "1700000000100000-1")

        def inspect(result, gate_mock, urlopen):
            self.assertTrue(result.saved)
            self.assertTrue(result.stop_here)
            self.assertEqual(result.notice, "")
            self.assertEqual(result.outcome["action"], "saved")
            self.assertEqual(result.outcome["context_source"], "gate")
            message = result.consent_output["systemMessage"]
            self.assertEqual(message, f"Hindsight: memoria salvata — {preview}")
            self.assertIn(
                "## Hindsight retain\n\nLa memoria in attesa di conferma è stata salvata",
                result.consent_output["hookSpecificOutput"]["additionalContext"],
            )
            self.assertEqual(
                result.consent_output["hookSpecificOutput"]["hookEventName"], "UserPromptSubmit"
            )
            # il gate e' partito comunque: retain con context -> POST silenziosa
            self.assertEqual(result.gate_output(time.monotonic() + 10), {})

        result, gate_mock, urlopen = self.at_prompt("sì", inspect)
        self.assertEqual(gate_mock.call_count, 1)
        # due POST: quella del consenso (pending) e quella del retain differito
        self.assertEqual(urlopen.call_count, 2)
        self.assertEqual(self.queue_names(), [])
        # il pending e' consumato: un secondo si' non trova nulla
        self.assertIsNone(handle_retain_consent("si", "sess-gate-test", self.tmp.name))

    def test_retain_at_prompt_context_source_label_and_no_notice_on_negative(self):
        # context mancante -> label della provenienza nel messaggio (qui la
        # riga repo/branch di ultima risorsa: nessuna proposta nel transcript)
        rc, out, _gate, _urlopen = self.run_main(
            self.cfg(),
            GateResult(action="retain", reason="durable_decision", preview="Salvo X.", context=""),
        )
        self.assertIn("<PROPOSTA>", self.context_of(out))

        def inspect(result, gate_mock, urlopen):
            self.assertTrue(result.saved)
            self.assertIn(
                " [context «sessione Claude Code», ricavato da repo/branch]",
                result.consent_output["systemMessage"],
            )

        self.at_prompt("sì", inspect)

        # "no": scarto silenzioso (nessuna notifica), niente stop
        self.make_pending()

        def inspect_no(result, gate_mock, urlopen):
            self.assertEqual(result.outcome["action"], "discarded")
            self.assertEqual(result.outcome["reason"], "negative")
            self.assertEqual(result.notice, "")
            self.assertFalse(result.stop_here)
            self.assertEqual(result.consent_output, {})
            self.assertEqual(result.gate_output(time.monotonic() + 10), {})

        self.at_prompt("no", inspect_no)

    def test_retain_at_prompt_new_prompt_sets_notice(self):
        # Il transcript di setUp NON contiene la domanda di consenso: Claude
        # l'ha omessa (additionalContext e' consultivo). La notifica di scarto
        # non deve presupporre una domanda mai vista: lo dice esplicitamente.
        preview = self.make_pending()

        def inspect(result, gate_mock, urlopen):
            self.assertEqual(result.outcome["action"], "discarded")
            self.assertEqual(result.outcome["reason"], "new_prompt")
            self.assertEqual(
                result.notice,
                "Hindsight: memoria in attesa scartata (domanda non posta da Claude) "
                f"— {preview}",
            )
            self.assertFalse(result.saved)
            self.assertFalse(result.stop_here)
            self.assertEqual(result.consent_output, {})
            # nessuna entry in coda: nessun processo lanciato, {} subito
            self.assertFalse(result.launched)
            t0 = time.monotonic()
            self.assertEqual(result.gate_output(time.monotonic() + 10), {})
            self.assertLess(time.monotonic() - t0, 1.0)

        result, gate_mock, urlopen = self.at_prompt("parliamo di tutt'altro adesso", inspect)
        gate_mock.assert_not_called()
        urlopen.assert_not_called()
        self.assertEqual(result.spawned, [])

        # Domanda POSTA (ultimo testo assistant la contiene): notifica classica.
        preview = self.make_pending()
        with open(self.transcript, "a", encoding="utf-8") as handle:
            handle.write(json.dumps(user_record("ok e poi?")) + "\n")
            handle.write(
                json.dumps(
                    assistant_record(
                        f"Ecco la risposta.\n\nVuoi che salvi questa memoria? — {preview} (sì/no)"
                    )
                )
                + "\n"
            )

        def inspect_asked(result, gate_mock, urlopen):
            self.assertEqual(result.notice, f"Hindsight: memoria in attesa scartata — {preview}")

        self.at_prompt("parliamo di tutt'altro adesso", inspect_asked)

    def test_retain_at_prompt_error_restored_skips_gate_and_keeps_queue(self):
        self.make_pending()
        entry = self.enqueue(self.hook, "1700000000100000-1")

        def inspect(result, gate_mock, urlopen):
            self.assertEqual(result.outcome["action"], "error")
            self.assertTrue(result.outcome["restored"])
            self.assertTrue(result.stop_here)
            self.assertFalse(result.saved)
            message = result.consent_output["systemMessage"]
            self.assertIn("Hindsight: salvataggio della memoria in attesa NON riuscito — ", message)
            self.assertIn("OSError", message)
            self.assertIn("Rispondi «sì» al prossimo prompt per riprovare.", message)
            self.assertNotIn("hookSpecificOutput", result.consent_output)
            # gate NON partito: un nuovo pending calpesterebbe quello ripristinato
            self.assertFalse(result.launched)
            self.assertEqual(result.gate_output(time.monotonic() + 10), {})

        result, gate_mock, _urlopen = self.at_prompt(
            "sì", inspect, urlopen_effect=OSError("connection refused")
        )
        gate_mock.assert_not_called()
        self.assertEqual(result.spawned, [])
        # l'entry resta in coda per il prompt successivo
        self.assertEqual(self.queue_names(), [os.path.basename(entry)])
        # e il pending ripristinato e' ancora li': un secondo si' lo ritrova
        with mock.patch("urllib.request.urlopen", return_value=FakeResponse()):
            retry = handle_retain_consent("si", "sess-gate-test", self.tmp.name)
        self.assertEqual(retry["action"], "saved")

    def read_events(self, log_path: str) -> list[dict]:
        with open(log_path, encoding="utf-8") as handle:
            return [json.loads(line) for line in handle if line.strip()]

    def test_retain_at_prompt_deadline_passed_carries_over_without_marker(self):
        # Gate ancora in volo alla deadline: {} SUBITO, NESSUN marker di
        # fallimento (nulla si perde: il processo continua e scrive l'outbox),
        # e il prompt successivo lo raccoglie (pickup) — qui la domanda del
        # pending, quindi il consenso di quel prompt viene saltato.
        preview = "Vale la pena salvare la decisione sul gate?"
        self.enqueue(self.hook, "1700000000100000-1")
        log_path = os.path.join(self.tmp.name, "debug.log")
        cfg = self.cfg(debug_log_enabled=True, debug_log_file=log_path)
        release = threading.Event()

        def slow_gate(*_args, **_kwargs):
            release.wait(10)  # il gate "e' ancora in volo" finche' il test non lo libera
            return GateResult(action="uncertain", reason="borderline", preview=preview, context="dominio")

        def inspect(result, gate_mock, urlopen):
            self.assertTrue(result.launched)
            # deadline gia' passata e gate ancora in volo: {} SUBITO, senza aspettare
            t0 = time.monotonic()
            self.assertEqual(result.gate_output(time.monotonic() - 1), {})
            self.assertLess(time.monotonic() - t0, 1.0)
            # cache: anche con una deadline generosa non si ri-aspetta
            self.assertEqual(result.gate_output(time.monotonic() + 10), {})
            release.set()

        cache = os.path.join(self.tmp.name, "xdg-cache")
        with mock.patch.dict(os.environ, {"XDG_CACHE_HOME": cache}):
            self.at_prompt("prompt qualunque", inspect, cfg=cfg, gate_result=slow_gate)
        events = self.read_events(log_path)
        carried = [e for e in events if e.get("event") == "retain_deferred" and e.get("action") == "carried_over"]
        self.assertEqual(len(carried), 1, events)
        self.assertEqual(carried[0]["session"], "sess-gat")
        self.assertFalse(any(e.get("reason") == "deferred_timeout" for e in events), events)
        # NESSUN marker: non e' una perdita
        self.assertFalse(os.path.exists(os.path.join(cache, "trinity", "hs-retain-failed.log")))
        # il figlio ha finito dopo la deadline: outbox su disco con la domanda
        self.assertTrue(os.path.exists(self.outbox()))
        with open(self.outbox(), encoding="utf-8") as handle:
            box = json.load(handle)
        self.assertIs(box["asks_consent"], True)
        self.assertIn(preview, self.context_of(box["output"]))

        # Prompt successivo, l'utente scrive "si'": NON e' la risposta alla
        # domanda mai mostrata -> consenso saltato, pending intatto, la
        # domanda esce ORA da gate_output(), subito, outbox cancellato.
        def inspect_next(result, gate_mock, urlopen):
            self.assertIsNone(result.outcome)
            self.assertFalse(result.stop_here)
            self.assertFalse(result.saved)
            self.assertFalse(result.launched)
            t0 = time.monotonic()
            out = result.gate_output(time.monotonic() + 10)
            self.assertLess(time.monotonic() - t0, 1.0)
            self.assertIn(f"Vuoi che salvi questa memoria? — {preview} (sì/no)", self.context_of(out))
            self.assertNotIn("asks_consent", out)
            self.assertFalse(os.path.exists(self.outbox()))

        with mock.patch.dict(os.environ, {"XDG_CACHE_HOME": cache}):
            result, gate_mock, urlopen = self.at_prompt("sì", inspect_next, cfg=cfg)
        gate_mock.assert_not_called()
        urlopen.assert_not_called()  # il "si'" NON ha eseguito la POST del pending
        picked = [e for e in self.read_events(log_path) if e.get("event") == "retain_deferred" and e.get("action") == "picked_up"]
        self.assertEqual(len(picked), 1)
        self.assertIs(picked[0]["asks_consent"], True)
        # il pending e' ancora li': il "si'" del prompt DOPO lo esegue
        with mock.patch("urllib.request.urlopen", return_value=FakeResponse()):
            outcome = handle_retain_consent("si", "sess-gate-test", self.tmp.name)
        self.assertEqual(outcome["action"], "saved")

    def test_retain_at_prompt_pickup_with_question_skips_consent_and_holds_launch(self):
        # Outbox con domanda mai mostrata + pending in attesa + entry in coda:
        # il consenso si salta (il "si'" non consuma il pending), l'entry NON
        # viene valutata ora (un nuovo pending calpesterebbe quello appena
        # mostrato) e resta in coda per il prompt dopo.
        preview = self.make_pending()
        entry = self.enqueue(self.hook, "1700000000100000-1")
        question = {
            "systemMessage": f"Hindsight: Vuoi che salvi questa memoria? — {preview} (sì/no)",
            "hookSpecificOutput": {"hookEventName": "UserPromptSubmit", "additionalContext": "istruzione"},
        }
        self.worker._write_outbox("sess-gate-test", question, True)

        def inspect(result, gate_mock, urlopen):
            self.assertIsNone(result.outcome)
            self.assertFalse(result.launched)
            self.assertEqual(result.gate_output(time.monotonic() + 10), question)
            self.assertFalse(os.path.exists(self.outbox()))

        result, gate_mock, urlopen = self.at_prompt("sì", inspect)
        gate_mock.assert_not_called()
        urlopen.assert_not_called()
        self.assertEqual(result.spawned, [])
        self.assertEqual(self.queue_names(), [os.path.basename(entry)])
        # pending intatto
        with mock.patch("urllib.request.urlopen", return_value=FakeResponse()):
            self.assertEqual(handle_retain_consent("si", "sess-gate-test", self.tmp.name)["action"], "saved")

    def test_retain_at_prompt_pickup_without_question_runs_consent_and_launches(self):
        # Outbox SENZA domanda (es. notifica di gate error del prompt prima):
        # il consenso gira normalmente (qui: "si'" -> POST del pending), il suo
        # output e' quello di gate_output(), e la coda si valuta comunque
        # (processo lanciato; il suo outbox lo raccogliera' il prompt dopo).
        preview = self.make_pending()
        self.enqueue(self.hook, "1700000000100000-1")
        notice = {"systemMessage": "Hindsight: retain automatico non eseguito — errore tecnico del gate (x)."}
        self.worker._write_outbox("sess-gate-test", notice, False)

        def inspect(result, gate_mock, urlopen):
            self.assertEqual(result.outcome["action"], "saved")
            self.assertTrue(result.stop_here)
            self.assertIn(preview, result.consent_output["systemMessage"])
            self.assertTrue(result.launched)
            self.assertEqual(result.gate_output(time.monotonic() + 10), notice)

        result, gate_mock, urlopen = self.at_prompt("sì", inspect)
        self.assertEqual(len(result.spawned), 1)
        self.assertEqual(gate_mock.call_count, 1)  # il figlio ha valutato l'entry
        self.assertEqual(urlopen.call_count, 2)  # POST del consenso + POST del retain
        self.assertEqual(self.queue_names(), [])
        # l'outbox del figlio (retain OK -> {}) aspetta il prompt successivo
        with open(self.outbox(), encoding="utf-8") as handle:
            self.assertEqual(json.load(handle), {"output": {}, "asks_consent": False})

    def test_retain_at_prompt_retain_disabled_drops_entry_without_spawn(self):
        self.enqueue(self.hook, "1700000000100000-1")

        def inspect(result, gate_mock, urlopen):
            self.assertFalse(result.launched)
            self.assertEqual(result.gate_output(time.monotonic() + 10), {})

        result, gate_mock, urlopen = self.at_prompt(
            "prompt qualunque", inspect, cfg=self.cfg(retain_enabled=False)
        )
        self.assertEqual(result.spawned, [])
        gate_mock.assert_not_called()
        urlopen.assert_not_called()
        self.assertEqual(self.queue_names(), [])  # scartata in-process
        self.assertFalse(os.path.exists(self.outbox()))

    def test_retain_at_prompt_never_raises(self):
        with mock.patch.object(
            self.worker, "handle_retain_consent", side_effect=RuntimeError("boom")
        ):
            result = self.worker.retain_at_prompt("sì", "sess-gate-test", self.tmp.name, "")
        self.assertIsNone(result.outcome)
        self.assertEqual(result.consent_output, {})
        self.assertEqual(result.notice, "")
        self.assertFalse(result.saved)
        self.assertFalse(result.stop_here)
        self.assertFalse(result.launched)
        self.assertEqual(result.gate_output(time.monotonic() + 1), {})
        # un launcher rotto non butta via il consenso gia' calcolato e lascia
        # l'entry in coda
        preview = self.make_pending()
        entry = self.enqueue(self.hook, "1700000000100000-1")
        with mock.patch.object(
            self.worker, "_spawn_queued", side_effect=OSError("no python")
        ), mock.patch("urllib.request.urlopen", return_value=FakeResponse()):
            result = self.worker.retain_at_prompt("sì", "sess-gate-test", self.tmp.name, "")
        self.assertEqual(result.outcome["action"], "saved")
        self.assertIn(preview, result.consent_output["systemMessage"])
        self.assertFalse(result.launched)
        self.assertEqual(result.gate_output(time.monotonic() + 1), {})
        self.assertEqual(self.queue_names(), [os.path.basename(entry)])

    def test_main_queued_writes_outbox(self):
        # Il processo detached: main(["--queued", sid]) valuta l'entry e scrive
        # SEMPRE l'outbox {"output", "asks_consent"}: True solo se pone la
        # domanda del pending; False per retain-con-context (POST), retain
        # disabilitato e coda vuota.
        preview = "Vale la pena salvare la decisione sul gate?"
        cases = (
            (GateResult(action="uncertain", reason="borderline", preview=preview, context="dominio"), True, 0),
            (GateResult(action="retain", reason="durable_decision", preview="Salvo X.", context="dominio"), False, 1),
        )
        for gate, asks, posts in cases:
            with self.subTest(action=gate.action):
                self.enqueue(self.hook, "1700000000100000-1")
                stdout = io.StringIO()
                with mock.patch.object(self.worker, "CFG", self.cfg()), mock.patch.object(
                    self.worker, "evaluate_retain", return_value=gate
                ), mock.patch("urllib.request.urlopen", return_value=FakeResponse()) as urlopen:
                    with redirect_stdout(stdout), redirect_stderr(io.StringIO()):
                        self.assertEqual(self.worker.main(["--queued", "sess-gate-test"]), 0)
                self.assertEqual(stdout.getvalue(), "")  # nulla su stdout: solo l'outbox
                self.assertEqual(urlopen.call_count, posts)
                self.assertEqual(self.queue_names(), [])
                with open(self.outbox(), encoding="utf-8") as handle:
                    box = json.load(handle)
                self.assertIs(box["asks_consent"], asks)
                self.assertNotIn("asks_consent", box["output"])
                if asks:
                    self.assertIn(preview, self.context_of(box["output"]))
                    handle_retain_consent("no", "sess-gate-test", self.tmp.name)  # pulizia pending
                else:
                    self.assertEqual(box["output"], {})
                os.remove(self.outbox())
        # retain disabilitato: entry consumata, outbox vuoto
        self.enqueue(self.hook, "1700000000100000-1")
        with mock.patch.object(self.worker, "CFG", self.cfg(retain_enabled=False)), mock.patch.object(
            self.worker, "evaluate_retain"
        ) as gate_mock:
            with redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
                self.assertEqual(self.worker.main(["--queued", "sess-gate-test"]), 0)
        gate_mock.assert_not_called()
        self.assertEqual(self.queue_names(), [])
        with open(self.outbox(), encoding="utf-8") as handle:
            self.assertEqual(json.load(handle), {"output": {}, "asks_consent": False})
        os.remove(self.outbox())
        # coda vuota: outbox vuoto comunque (chi aspetta distingue "finito" da "in corso")
        with redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
            self.assertEqual(self.worker.main(["--queued", "sess-gate-test"]), 0)
        with open(self.outbox(), encoding="utf-8") as handle:
            self.assertEqual(json.load(handle), {"output": {}, "asks_consent": False})
        # --queued senza session_id: exit 0, nessun outbox
        os.remove(self.outbox())
        with redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
            self.assertEqual(self.worker.main(["--queued"]), 0)
        self.assertEqual(self.queue_names(), [])

    def test_outbox_path_stays_inside_queue_dir(self):
        queue_dir = self.worker.retain_queue_dir()
        for sid in ("../../etc/x", "a/b", "a\\b"):
            path = self.worker.outbox_path(sid)
            self.assertEqual(os.path.dirname(path), queue_dir, sid)
            self.assertTrue(path.endswith(".out.json"))
        # e gli outbox non sono entry di coda: dequeue/drain li ignorano
        self.worker._write_outbox("sess-gate-test", {}, False)
        self.assertEqual(self.worker.drain_queue(), [])
        self.assertIsNone(self.worker.dequeue_for_session("sess-gate-test"))
        self.assertTrue(os.path.exists(self.outbox()))

    def test_sweep_stale_queue_marks_and_removes_old_entries(self):
        cache = os.path.join(self.tmp.name, "xdg-cache")
        stale = self.enqueue(dict(self.hook, session_id="sess-stale-old"), "1600000000000000-1")
        fresh = self.enqueue(self.hook, "1700000000100000-2")
        old_box = self.worker.outbox_path("sess-stale-old")
        self.worker._write_outbox("sess-stale-old", {}, False)
        old = time.time() - 25 * 3600
        os.utime(stale, (old, old))
        os.utime(old_box, (old, old))
        log_path = os.path.join(self.tmp.name, "debug.log")
        cfg = self.cfg(debug_log_enabled=True, debug_log_file=log_path)
        with mock.patch.dict(os.environ, {"XDG_CACHE_HOME": cache}), mock.patch.object(
            self.worker, "CFG", cfg
        ):
            self.assertEqual(self.worker.sweep_stale_queue(), 1)
        self.assertEqual(self.queue_names(), [os.path.basename(fresh)])
        self.assertFalse(os.path.exists(old_box))
        marker = os.path.join(cache, "trinity", "hs-retain-failed.log")
        with open(marker, encoding="utf-8") as handle:
            lines = handle.read().splitlines()
        self.assertEqual(len(lines), 1, lines)
        self.assertIn("piu' vecchia di 24h", lines[0])
        self.assertIn("sess-sta", lines[0])
        events = [e for e in self.read_events(log_path) if e.get("reason") == "queue_stale"]
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0]["session"], "sess-sta")
        # idempotente e silenzioso su coda pulita / inesistente
        self.assertEqual(self.worker.sweep_stale_queue(), 0)
        with mock.patch.dict(os.environ, {"HS_RETAIN_QUEUE_DIR": os.path.join(self.tmp.name, "nope")}):
            self.assertEqual(self.worker.sweep_stale_queue(), 0)
        # ...e retain_at_prompt lo esegue a ogni prompt (anche senza coda propria)
        stale2 = self.enqueue(dict(self.hook, session_id="sess-stale-two"), "1600000000000000-3")
        os.utime(stale2, (old, old))
        with mock.patch.dict(os.environ, {"XDG_CACHE_HOME": cache}):
            self.at_prompt("prompt qualunque", lambda *_: None)
        self.assertEqual(self.queue_names(), [])  # la fresh l'ha consumata il figlio, la stale lo sweep

    def test_should_retain_now_advance_crosses_multiples(self):
        # 0 -> 4 con N=3 attraversa il 3: True; 4 -> 5 no; 5 -> 6 si'.
        cfg = self.cfg(retain_every_n_turns=3)
        with mock.patch.object(self.worker, "CFG", cfg):
            self.assertTrue(self.worker.should_retain_now("sess-gate-test", advance=4))
            self.assertEqual(self.read_state()["sess-gate-test"]["stop_count"], 4)
            self.assertFalse(self.worker.should_retain_now("sess-gate-test", advance=1))
            self.assertEqual(self.read_state()["sess-gate-test"]["stop_count"], 5)
            self.assertTrue(self.worker.should_retain_now("sess-gate-test"))
            self.assertEqual(self.read_state()["sess-gate-test"]["stop_count"], 6)
            # advance non valido -> 1; force non avanza
            self.assertFalse(self.worker.should_retain_now("sess-gate-test", advance=0))
            self.assertEqual(self.read_state()["sess-gate-test"]["stop_count"], 7)
            self.assertTrue(self.worker.should_retain_now("sess-gate-test", force=True, advance=5))
            self.assertEqual(self.read_state()["sess-gate-test"]["stop_count"], 7)

    def test_dequeue_counts_skipped_entries_and_throttling_advances(self):
        # 3 Stop accumulati senza prompt in mezzo (3 entry della stessa
        # sessione): il dequeue ne tiene una e ne scarta 2 -> queued_skipped=2,
        # e con stop_count=0, N=3 il gate viene chiamato SUBITO (3 Stop
        # avvenuti = un multiplo attraversato) invece di slittare di due turni.
        for i in range(3):
            self.enqueue(dict(self.hook, marker=i), f"170000000010000{i}-1")
        entry = self.worker.dequeue_for_session("sess-gate-test")
        self.assertEqual(entry["marker"], 2)
        self.assertEqual(entry["queued_skipped"], 2)
        # entry singola: 0
        self.enqueue(self.hook, "1700000000200000-1")
        self.assertEqual(self.worker.dequeue_for_session("sess-gate-test")["queued_skipped"], 0)

        cfg = self.cfg(retain_every_n_turns=3)
        gate = GateResult(action="retain", reason="durable_decision", preview="x", context="dominio")
        for i in range(3):
            self.enqueue(dict(self.hook, marker=i), f"170000000030000{i}-1")
        with mock.patch.object(self.worker, "CFG", cfg), mock.patch.object(
            self.worker, "evaluate_retain", return_value=gate
        ) as gate_mock, mock.patch("urllib.request.urlopen", return_value=FakeResponse()) as urlopen:
            with redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
                self.assertIsNone(self.worker.evaluate_queued("sess-gate-test"))
        self.assertEqual(gate_mock.call_count, 1)
        self.assertEqual(urlopen.call_count, 1)
        self.assertEqual(self.read_state()["sess-gate-test"]["stop_count"], 3)
        self.assertEqual(self.queue_names(), [])

    def test_post_failure_writes_durable_marker(self):
        cache = os.path.join(self.tmp.name, "xdg-cache")
        with mock.patch.dict(os.environ, {"XDG_CACHE_HOME": cache}):
            gate = GateResult(action="retain", reason="durable_decision", preview="x", context="dominio")
            with mock.patch.object(self.worker, "CFG", self.cfg()), mock.patch.object(
                self.worker, "evaluate_retain", return_value=gate
            ), mock.patch("urllib.request.urlopen", side_effect=OSError("connection refused")):
                stderr = io.StringIO()
                with redirect_stdout(io.StringIO()), redirect_stderr(stderr):
                    rc, out = self.worker.evaluate(self.hook, "deferred")
            self.assertEqual((rc, out), (1, None))
            self.assertIn("[retain] FAIL", stderr.getvalue())
            marker = os.path.join(cache, "trinity", "hs-retain-failed.log")
            with open(marker, encoding="utf-8") as handle:
                lines = handle.read().splitlines()
        self.assertEqual(len(lines), 1)
        ts, _, msg = lines[0].partition("\t")
        self.assertTrue(ts.endswith("Z"), ts)
        self.assertTrue(msg.startswith("non arrivato al server — "), msg)
        self.assertIn("connection refused", msg)

    def test_post_failure_consumes_entry_without_reenqueue(self):
        # Limite ACCETTATO (asimmetria col path del consenso, che ripristina il
        # pending): la POST diretta fallita NON ri-accoda l'entry — al prompt
        # dopo sarebbe comunque throttlata senza un rollback di stop_count — e
        # la finestra si perde con il solo marker durevole per il failcheck.
        # Il test fissa questo comportamento perche' non cambi per sbaglio.
        cache = os.path.join(self.tmp.name, "xdg-cache")
        self.enqueue(self.hook, "1700000000100000-1")
        gate = GateResult(action="retain", reason="durable_decision", preview="x", context="dominio")
        with mock.patch.dict(os.environ, {"XDG_CACHE_HOME": cache}), mock.patch.object(
            self.worker, "CFG", self.cfg()
        ), mock.patch.object(
            self.worker, "evaluate_retain", return_value=gate
        ), mock.patch("urllib.request.urlopen", side_effect=OSError("connection refused")):
            with redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
                out = self.worker.evaluate_queued("sess-gate-test")
        self.assertIsNone(out)
        self.assertEqual(self.queue_names(), [])  # consumata, nessun re-enqueue
        self.assertFalse(os.path.isdir(os.path.join(self.tmp.name, "pending")))  # e nessun pending
        marker = os.path.join(cache, "trinity", "hs-retain-failed.log")
        with open(marker, encoding="utf-8") as handle:
            self.assertIn("non arrivato al server", handle.read())


if __name__ == "__main__":
    unittest.main()
