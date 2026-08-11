"""E2e deterministico di hindsight-recall.sh (audit ICH-66, finding B7).

Recall e classificatore sono mockati da un server HTTP locale; l'hook viene
eseguito come vero subprocess bash con HOOK_INPUT su stdin. Copre i rami che
vivono solo nel corpo dell'hook: regola high+medium, consenso/pending end-to-end,
fail-open su classificatore rotto e su save_pending impossibile.
"""

import glob
import json
import os
import shutil
import subprocess
import tempfile
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

HOOKS_DIR = os.path.dirname(os.path.abspath(__file__))
HOOK = os.path.join(HOOKS_DIR, "hindsight-recall.sh")
# Path esplicito: su Windows CreateProcess cerca in System32 PRIMA del PATH e
# "bash" diventerebbe la bash WSL. shutil.which cerca solo nel PATH (MSYS).
BASH = shutil.which("bash") or "bash"


class MockBackend(BaseHTTPRequestHandler):
    """Un solo server per entrambi gli endpoint: /memories/recall e chat/completions."""

    recall_results: list = []
    classifier_spec: object = None  # lista di classifications | ("status", int) | "garbage"
    classifier_calls = 0

    def do_POST(self):
        self.rfile.read(int(self.headers.get("Content-Length") or 0))
        cls = type(self)
        if self.path.endswith("/memories/recall"):
            self._send(200, json.dumps({"results": cls.recall_results}))
        elif self.path.endswith("/chat/completions"):
            cls.classifier_calls += 1
            if isinstance(cls.classifier_spec, tuple):
                self._send(cls.classifier_spec[1], "{}")
            elif cls.classifier_spec == "garbage":
                self._send(200, "not json at all")
            else:
                content = json.dumps({"classifications": cls.classifier_spec})
                self._send(200, json.dumps({"choices": [{"message": {"content": content}}]}))
        else:
            self._send(404, "{}")

    def _send(self, status, body):
        data = body.encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def log_message(self, format, *args):
        pass


class HookE2ETests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = ThreadingHTTPServer(("127.0.0.1", 0), MockBackend)
        cls.port = cls.server.server_address[1]
        threading.Thread(target=cls.server.serve_forever, daemon=True).start()

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.pending_dir = os.path.join(self.tmp.name, "pending")
        MockBackend.recall_results = []
        MockBackend.classifier_spec = []
        MockBackend.classifier_calls = 0

    def tearDown(self):
        self.tmp.cleanup()

    def run_hook(self, prompt, session_id="e2e-session"):
        hook_input = json.dumps(
            {"prompt": prompt, "session_id": session_id, "cwd": self.tmp.name}
        )
        env = {
            **os.environ,
            "HINDSIGHT_API_URL": f"http://127.0.0.1:{self.port}",
            "HS_OPENAI_URL": f"http://127.0.0.1:{self.port}/v1/chat/completions",
            "OPENAI_API_KEY": "test-key",
            "HS_CFG_BANK": '{"recall_banks": []}',
            "HS_CFG_RECALL_PENDING_DIR": self.pending_dir,
            "HS_CFG_RECALL_TIMEOUT": "5",
            "HS_CFG_RECALL_RESULT_FILTER_TIMEOUT": "5",
            "HS_CFG_RECALL_DEBUG_IN_CONTEXT": "false",
        }
        proc = subprocess.run(
            [BASH, HOOK], input=hook_input, env=env,
            capture_output=True, text=True, encoding="utf-8", errors="replace",
            timeout=60,
        )
        self.assertEqual(proc.returncode, 0, proc.stderr)
        if not proc.stdout.strip():
            return None
        return json.loads(proc.stdout)  # stdout non vuoto deve essere JSON valido

    def context(self, output):
        return output["hookSpecificOutput"]["additionalContext"]

    def pending_files(self):
        return glob.glob(os.path.join(self.pending_dir, "*.json"))

    PROMPT = "dimmi qualcosa di rilevante sul progetto per favore"

    def test_high_plus_medium_injects_only_high_without_pending(self):
        MockBackend.recall_results = [
            {"text": "alpha memo", "type": "world", "scores": {"reranker": 0.2}},
            {"text": "beta memo", "type": "world", "scores": {"reranker": 0.3}},
        ]
        MockBackend.classifier_spec = [
            {"index": 0, "confidence": "high", "reason": "directly_actionable"},
            {"index": 1, "confidence": "medium", "reason": "plausible_but_uncertain"},
        ]
        output = self.run_hook(self.PROMPT)
        context = self.context(output)
        self.assertIn("alpha memo", context)
        self.assertNotIn("beta memo", context)
        self.assertNotIn("consenso richiesto", context)
        self.assertEqual(self.pending_files(), [])

    def test_medium_only_asks_consent_then_single_consumption(self):
        MockBackend.recall_results = [
            {"text": "gamma memo", "type": "world", "scores": {"reranker": 0.1}},
        ]
        MockBackend.classifier_spec = [
            {"index": 0, "confidence": "medium", "reason": "plausible_but_uncertain"},
        ]
        output = self.run_hook(self.PROMPT)
        context = self.context(output)
        self.assertIn("consenso richiesto", context)
        self.assertNotIn("gamma memo", context)
        self.assertEqual(len(self.pending_files()), 1)

        consented = self.run_hook("sì")
        self.assertIn("gamma memo", self.context(consented))
        self.assertEqual(self.pending_files(), [])

        again = self.run_hook("sì")
        self.assertIsNone(again)  # consumo singolo: niente reiniezione

    def test_negation_discards_pending_without_injection(self):
        MockBackend.recall_results = [
            {"text": "delta memo", "type": "world", "scores": {"reranker": 0.1}},
        ]
        MockBackend.classifier_spec = [
            {"index": 0, "confidence": "medium", "reason": "plausible_but_uncertain"},
        ]
        self.run_hook(self.PROMPT)
        self.assertEqual(len(self.pending_files()), 1)
        refused = self.run_hook("non usarle")
        self.assertIsNone(refused)
        self.assertEqual(self.pending_files(), [])

    def test_medium_without_session_id_fails_open(self):
        MockBackend.recall_results = [
            {"text": "epsilon memo", "type": "world", "scores": {"reranker": 0.1}},
        ]
        MockBackend.classifier_spec = [
            {"index": 0, "confidence": "medium", "reason": "plausible_but_uncertain"},
        ]
        output = self.run_hook(self.PROMPT, session_id="")
        self.assertIn("epsilon memo", self.context(output))
        self.assertEqual(self.pending_files(), [])

    def test_broken_classifier_fails_open_with_all_results(self):
        MockBackend.recall_results = [
            {"text": "zeta memo", "type": "world", "scores": {"reranker": 0.1}},
            {"text": "eta memo", "type": "world"},
        ]
        for spec in ["garbage", ("status", 500)]:
            with self.subTest(spec=spec):
                MockBackend.classifier_spec = spec
                context = self.context(self.run_hook(self.PROMPT))
                self.assertIn("zeta memo", context)
                self.assertIn("eta memo", context)
                self.assertEqual(self.pending_files(), [])

    def test_bypass_scores_skip_the_classifier(self):
        MockBackend.recall_results = [
            {"text": "theta memo", "type": "world", "scores": {"reranker": 0.95}},
        ]
        context = self.context(self.run_hook(self.PROMPT))
        self.assertIn("theta memo", context)
        self.assertEqual(MockBackend.classifier_calls, 0)


if __name__ == "__main__":
    unittest.main(verbosity=2)
