"""E2e deterministico di hindsight-recall.sh (audit ICH-66, finding B7; ICH-73).

Recall, classificatore e POST /memories sono mockati da un server HTTP locale;
l'hook viene eseguito come vero subprocess bash con HOOK_INPUT su stdin. Copre
i rami che vivono solo nel corpo dell'hook: regola high+medium, consenso/pending
end-to-end, fail-open su classificatore rotto e su save_pending impossibile, e
il consenso del RETAIN pending (ICH-73): scarto visibile su prompt nuovo, context
dalla proposta di Claude nel transcript o dalla risposta `context: ...`, sempre
con UN SOLO oggetto JSON su stdout.
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
from unittest import mock

from lib.hindsight_retain_gate import save_retain_pending

HOOKS_DIR = os.path.dirname(os.path.abspath(__file__))
HOOK = os.path.join(HOOKS_DIR, "hindsight-recall.sh")
# Path esplicito: su Windows CreateProcess cerca in System32 PRIMA del PATH e
# "bash" diventerebbe la bash WSL. shutil.which cerca solo nel PATH (MSYS).
BASH = shutil.which("bash") or "bash"


class MockBackend(BaseHTTPRequestHandler):
    """Un solo server per tutti gli endpoint: /memories/recall, chat/completions
    e la POST /memories eseguita dal consenso del retain pending (ICH-73)."""

    recall_results: list = []
    classifier_spec: object = None  # lista di classifications | ("status", int) | "garbage"
    classifier_calls = 0
    retain_posts: list = []  # body JSON delle POST /memories, in ordine

    def do_POST(self):
        body = self.rfile.read(int(self.headers.get("Content-Length") or 0))
        cls = type(self)
        if self.path.endswith("/memories/recall"):
            self._send(200, json.dumps({"results": cls.recall_results}))
        elif self.path.endswith("/memories"):
            cls.retain_posts.append(json.loads(body.decode("utf-8")))
            self._send(200, json.dumps({"success": True}))
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
        self.retain_pending_dir = os.path.join(self.tmp.name, "retain-pending")
        MockBackend.recall_results = []
        MockBackend.classifier_spec = []
        MockBackend.classifier_calls = 0
        MockBackend.retain_posts = []

    def tearDown(self):
        self.tmp.cleanup()

    def run_hook(self, prompt, session_id="e2e-session", transcript_path=None):
        hook = {"prompt": prompt, "session_id": session_id, "cwd": self.tmp.name}
        if transcript_path is not None:
            hook["transcript_path"] = transcript_path
        hook_input = json.dumps(hook)
        env = {
            **os.environ,
            "HINDSIGHT_API_URL": f"http://127.0.0.1:{self.port}",
            "HS_OPENAI_URL": f"http://127.0.0.1:{self.port}/v1/chat/completions",
            "OPENAI_API_KEY": "test-key",
            "HS_CFG_BANK": '{"recall_banks": []}',
            "HS_CFG_RECALL_PENDING_DIR": self.pending_dir,
            "HS_RETAIN_PENDING_DIR": self.retain_pending_dir,
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
        # stdout non vuoto deve essere UN SOLO oggetto JSON valido: due oggetti
        # (es. notifica + contesto stampati separatamente) fanno fallire il parse.
        return json.loads(proc.stdout)

    def context(self, output):
        return output["hookSpecificOutput"]["additionalContext"]

    def pending_files(self):
        return glob.glob(os.path.join(self.pending_dir, "*.json"))

    def save_retain_pending(self, preview, context="", metadata=None):
        """Pending del retain (gate ICH-67/73) come lo lascia il worker allo Stop:
        stessa lib e stessa dir che l'hook legge via HS_RETAIN_PENDING_DIR."""
        item = {
            "content": "finestra e2e",
            "context": context,
            "tags": ["claude-code"],
            "timestamp": "2026-08-15T10:00:00+00:00",
            "metadata": (
                {"source": "claude-code-hook", "repo": "Trinity", "branch": "main"}
                if metadata is None
                else metadata
            ),
        }
        with mock.patch.dict(os.environ, {"HS_RETAIN_PENDING_DIR": self.retain_pending_dir}):
            saved = save_retain_pending(
                "e2e-session",
                self.tmp.name,
                f"http://127.0.0.1:{self.port}/banks/t",
                {"items": [item], "async": True},
                preview,
            )
        self.assertTrue(saved)

    def write_transcript(self, assistant_text):
        """Transcript JSONL il cui ultimo messaggio assistant e' assistant_text."""
        path = os.path.join(self.tmp.name, "transcript.jsonl")
        records = [
            {"type": "user", "message": {"role": "user", "content": "domanda dell'utente"}},
            {
                "type": "assistant",
                "message": {
                    "role": "assistant",
                    "content": [{"type": "text", "text": assistant_text}],
                },
            },
        ]
        with open(path, "w", encoding="utf-8") as handle:
            for record in records:
                handle.write(json.dumps(record, ensure_ascii=False) + "\n")
        return path

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

    def test_retain_pending_discarded_on_new_prompt_is_visible(self):
        self.save_retain_pending("Salvo la decisione e2e.")
        output = self.run_hook(self.PROMPT)
        # Il pending viene scartato in modo VISIBILE (ICH-73), e il recall
        # prosegue: nessun risultato -> nessun additionalContext, ma la notifica
        # esce comunque, come unico oggetto JSON.
        self.assertIn(
            "memoria in attesa scartata — Salvo la decisione e2e.", output["systemMessage"]
        )
        self.assertNotIn("hookSpecificOutput", output)
        self.assertEqual(MockBackend.retain_posts, [])

    def test_retain_pending_discard_notice_merges_with_recall_context(self):
        # Caso limite oltre il contratto (documentato): stesso scarto, ma il
        # recall HA contenuto -> notifica e additionalContext devono uscire nello
        # STESSO oggetto JSON (path emit(), non finish()); run_hook fallirebbe
        # su due oggetti separati.
        self.save_retain_pending("Salvo la decisione e2e.")
        MockBackend.recall_results = [
            {"text": "iota memo", "type": "world", "scores": {"reranker": 0.95}},
        ]
        output = self.run_hook(self.PROMPT)
        self.assertIn(
            "memoria in attesa scartata — Salvo la decisione e2e.", output["systemMessage"]
        )
        self.assertIn("iota memo", self.context(output))
        self.assertEqual(MockBackend.retain_posts, [])

    def test_retain_pending_yes_uses_transcript_proposal(self):
        self.save_retain_pending("Salvo la decisione e2e.", context="")
        transcript = self.write_transcript(
            "Salvo questa memoria con context «dominio e2e»? (sì / no / context: …)"
        )
        output = self.run_hook("sì", transcript_path=transcript)
        message = output["systemMessage"]
        self.assertIn("memoria salvata", message)
        self.assertIn("Salvo la decisione e2e.", message)
        self.assertIn("dominio e2e", message)
        self.assertIn("proposto da Claude", message)
        self.assertEqual(len(MockBackend.retain_posts), 1)
        self.assertEqual(MockBackend.retain_posts[-1]["items"][0]["context"], "dominio e2e")
        self.assertIn("## Hindsight retain", self.context(output))

    def test_retain_pending_context_reply(self):
        self.save_retain_pending("Salvo la decisione e2e.", context="")
        output = self.run_hook("context: dominio esplicito")
        message = output["systemMessage"]
        self.assertIn("memoria salvata", message)
        self.assertIn("dominio esplicito", message)
        self.assertIn("indicato da te", message)
        self.assertEqual(len(MockBackend.retain_posts), 1)
        self.assertEqual(
            MockBackend.retain_posts[-1]["items"][0]["context"], "dominio esplicito"
        )


if __name__ == "__main__":
    unittest.main(verbosity=2)
