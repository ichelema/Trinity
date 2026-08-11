#!/usr/bin/env python
"""Test del gate semantico pre-retain (ICH-67): modulo lib + integrazione worker."""

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
    GateResult,
    dedup_query,
    evaluate_retain,
    fetch_duplicate_candidates,
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
            }),
        )
        self.assertEqual(result.action, "retain")
        self.assertEqual(result.reason, "durable_decision")
        self.assertEqual(result.preview, "Salvo la decisione X perché Y.")
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
            }),
        )
        self.assertEqual(result.action, "uncertain")

    def test_invalid_payloads_fail_closed(self):
        cfg = {"retain_gate_model": "m", "retain_gate_timeout": 5}
        summary = {"turns": []}
        bad_payloads = [
            {},  # schema incompleto
            {"action": "keep", "reason": "duplicate", "preview": "", "duplicate_of": []},
            {"action": "skip", "reason": "unknown_reason", "preview": "", "duplicate_of": []},
            {"action": "retain", "reason": "durable_decision", "preview": "  ", "duplicate_of": []},
            {"action": "skip", "reason": "duplicate", "preview": "", "duplicate_of": ["0"]},
            {"action": "skip", "reason": "duplicate", "preview": "", "duplicate_of": [True]},
            {"action": "skip", "reason": "duplicate", "preview": "", "duplicate_of": [0]},  # fuori range: 0 candidati
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
                }),
            )
            self.assertEqual(duplicated_index.reason, "gate_error")

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

    def test_dedup_query_prefers_last_assistant(self):
        self.assertEqual(
            dedup_query({"turns": [("user", "u1"), ("assistant", "a1"), ("user", "u2")]}),
            "a1",
        )
        self.assertEqual(dedup_query({"turns": [("user", "solo user")]}), "solo user")
        self.assertEqual(dedup_query({"turns": []}), "")
        self.assertEqual(
            dedup_query({"last_user_prompt": "legacy prompt"}), "legacy prompt"
        )

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


class GateConfigTests(unittest.TestCase):
    def test_defaults_and_override_validation(self):
        self.assertEqual(hindsight_config.DEFAULTS["retain_gate_mode"], "off")
        self.assertEqual(hindsight_config.DEFAULTS["retain_gate_model"], "gpt-5.6-luna")
        self.assertEqual(hindsight_config.DEFAULTS["retain_gate_timeout"], 15)

        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "config.json")
            cfg = dict(hindsight_config.DEFAULTS)
            with open(path, "w", encoding="utf-8") as handle:
                json.dump(
                    {
                        "retain_gate_mode": "banana",
                        "retain_gate_timeout": -3,
                        "retain_gate_model": "  ",
                    },
                    handle,
                )
            hindsight_config._merge_json(cfg, path)
            self.assertEqual(cfg["retain_gate_mode"], "off")
            self.assertEqual(cfg["retain_gate_timeout"], 15)
            self.assertEqual(cfg["retain_gate_model"], "gpt-5.6-luna")

            with open(path, "w", encoding="utf-8") as handle:
                json.dump({"retain_gate_mode": "shadow", "retain_gate_timeout": 8}, handle)
            hindsight_config._merge_json(cfg, path)
            self.assertEqual(cfg["retain_gate_mode"], "shadow")
            self.assertEqual(cfg["retain_gate_timeout"], 8)


class FakeResponse:
    status = 200

    def read(self):
        return b'{"success": true}'

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False


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
                "retain_gate_mode": "off",
            }
        )
        base.update(overrides)
        return base

    def run_main(self, cfg, gate_result=None):
        stdout = io.StringIO()
        gate_mock = mock.Mock(return_value=gate_result)
        with mock.patch.object(self.worker, "CFG", cfg), mock.patch.object(
            self.worker, "evaluate_retain", gate_mock
        ), mock.patch("urllib.request.urlopen", return_value=FakeResponse()) as urlopen:
            with redirect_stdout(stdout):
                rc = self.worker.main()
        return rc, stdout.getvalue(), gate_mock, urlopen

    def test_gate_not_called_before_third_stop(self):
        cfg = self.cfg(retain_gate_mode="shadow", retain_every_n_turns=3)
        gate_result = GateResult(action="skip", reason="trivial_or_ephemeral")
        calls = []
        for _ in range(3):
            rc, _out, gate_mock, _urlopen = self.run_main(cfg, gate_result)
            self.assertEqual(rc, 0)
            calls.append(gate_mock.call_count)
        self.assertEqual(calls, [0, 0, 1])

    def test_enforce_retain_emits_block_without_post(self):
        cfg = self.cfg(retain_gate_mode="enforce")
        gate_result = GateResult(
            action="retain",
            reason="durable_decision",
            preview="Salvo: gate semantico prima della POST perché riduce il rumore.",
        )
        rc, out, gate_mock, urlopen = self.run_main(cfg, gate_result)
        self.assertEqual(rc, 0)
        self.assertEqual(gate_mock.call_count, 1)
        urlopen.assert_not_called()

        gate_lines = [l for l in out.splitlines() if l.startswith("HSGATE ")]
        self.assertEqual(len(gate_lines), 1)
        payload = json.loads(gate_lines[0][len("HSGATE ") :])
        self.assertEqual(payload["decision"], "block")
        self.assertTrue(payload["reason"])
        self.assertEqual(payload["hookSpecificOutput"]["hookEventName"], "Stop")
        self.assertIn("mcp__hindsight__retain", payload["hookSpecificOutput"]["additionalContext"])
        self.assertIn(gate_result.preview, payload["hookSpecificOutput"]["additionalContext"])
        self.assertIn(gate_result.preview, payload["systemMessage"])

    def test_enforce_skip_and_uncertain_are_silent(self):
        cfg = self.cfg(retain_gate_mode="enforce")
        for action, reason in (
            ("skip", "repo_recoverable"),
            ("uncertain", "borderline"),
        ):
            rc, out, _gate, urlopen = self.run_main(
                cfg, GateResult(action=action, reason=reason)
            )
            self.assertEqual(rc, 0)
            urlopen.assert_not_called()
            self.assertNotIn("HSGATE", out)

    def test_shadow_logs_but_does_not_block(self):
        cfg = self.cfg(retain_gate_mode="shadow")
        rc, out, gate_mock, urlopen = self.run_main(
            cfg, GateResult(action="skip", reason="trivial_or_ephemeral")
        )
        self.assertEqual(rc, 0)
        self.assertEqual(gate_mock.call_count, 1)
        self.assertEqual(urlopen.call_count, 1)  # POST normale nonostante skip
        self.assertNotIn("HSGATE", out)

    def test_gate_off_never_calls_gate(self):
        cfg = self.cfg()
        rc, _out, gate_mock, urlopen = self.run_main(
            cfg, GateResult(action="skip", reason="trivial_or_ephemeral")
        )
        self.assertEqual(rc, 0)
        gate_mock.assert_not_called()
        self.assertEqual(urlopen.call_count, 1)

    def test_chunked_doc_id_stable_on_replay(self):
        cfg = self.cfg()
        payloads = []

        def capture(req, timeout=10):
            payloads.append(json.loads(req.data.decode("utf-8")))
            return FakeResponse()

        with mock.patch.object(self.worker, "CFG", cfg), mock.patch(
            "urllib.request.urlopen", side_effect=capture
        ):
            with redirect_stdout(io.StringIO()):
                self.assertEqual(self.worker.main(), 0)
                self.assertEqual(self.worker.main(), 0)

        self.assertEqual(len(payloads), 2)
        first, second = (p["items"][0] for p in payloads)
        self.assertEqual(first["document_id"], second["document_id"])
        self.assertTrue(first["document_id"].startswith("sess-gate-test-"))
        # Il timestamp nel content cambia ma non deve cambiare l'id.
        self.assertNotEqual(first["content"], second["content"])

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
        with mock.patch.object(self.worker, "CFG", cfg), mock.patch(
            "urllib.request.urlopen", side_effect=capture
        ):
            with redirect_stdout(io.StringIO()):
                self.assertEqual(self.worker.main(), 0)
        self.assertNotEqual(payloads[2]["items"][0]["document_id"], first["document_id"])


if __name__ == "__main__":
    unittest.main()
