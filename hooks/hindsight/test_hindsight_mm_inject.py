"""hindsight-mm-inject.sh contro un backend finto: pagine iniettate, 404 sul
primo id, attesa del server che parte, gate spento, una sola GET per pagina.

L'hook gira come vero subprocess bash; HINDSIGHT_API_URL lo punta al backend
finto (api_url esplicito -> single-bank, gli id sono quelli di
HS_CFG_MENTAL_MODELS_INJECT_IDS).
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import tempfile
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

HERE = os.path.dirname(os.path.abspath(__file__))
HOOK = os.path.join(HERE, "hindsight-mm-inject.sh").replace(os.sep, "/")
# Path esplicito: su Windows "bash" sarebbe la bash WSL (vedi test_hindsight_recall_hook).
BASH = shutil.which("bash") or "bash"
PAGES = {
    "a": {"name": "Pagina A", "content": "contenuto-a"},
    "b": {"name": "Pagina B", "content": "contenuto-b"},
}


class Backend(BaseHTTPRequestHandler):
    unavailable = 0  # richieste che rispondono 503 prima di servire (server che parte)
    paths: list[str] = []

    def do_GET(self):
        Backend.paths.append(self.path)
        if Backend.unavailable > 0:
            Backend.unavailable -= 1
            return self._send(503, {"detail": "starting"})
        mid = self.path.split("?")[0].rsplit("/", 1)[-1]
        if mid in PAGES:
            self._send(200, PAGES[mid])
        else:
            self._send(404, {"detail": "nope"})

    def _send(self, status, body):
        data = json.dumps(body).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def log_message(self, format, *args):
        pass


class MmInjectTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = ThreadingHTTPServer(("127.0.0.1", 0), Backend)
        cls.url = f"http://127.0.0.1:{cls.server.server_address[1]}"
        threading.Thread(target=cls.server.serve_forever, daemon=True).start()

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()

    def setUp(self):
        Backend.unavailable = 0
        Backend.paths = []
        self.tmp = tempfile.TemporaryDirectory()
        # Niente override HS_*/HINDSIGHT_* o config di progetto della shell di chi
        # lancia i test; cache e debug log in tmp.
        self.env = {
            k: v
            for k, v in os.environ.items()
            if not k.startswith(("HS_", "HINDSIGHT_")) and k != "CLAUDE_PROJECT_DIR"
        }
        self.env.update(
            XDG_CACHE_HOME=self.tmp.name,
            PYTHONUTF8="1",
            HS_CFG_DEBUG_LOG_FILE=os.path.join(self.tmp.name, "hindsight-debug.log"),
            HINDSIGHT_API_URL=self.url,
            HS_CFG_MENTAL_MODELS_INJECT_ON_START="1",
        )

    def tearDown(self):
        self.tmp.cleanup()

    def run_hook(self, ids, **extra):
        """additionalContext iniettato, o "" se l'hook non stampa niente."""
        env = dict(self.env, HS_CFG_MENTAL_MODELS_INJECT_IDS=json.dumps(ids), **extra)
        r = subprocess.run([BASH, HOOK], env=env, capture_output=True, text=True, timeout=60)
        self.assertEqual(r.returncode, 0, r.stderr)
        if not r.stdout.strip():
            return ""
        return json.loads(r.stdout)["hookSpecificOutput"]["additionalContext"]

    def test_injects_pages_in_order(self):
        ctx = self.run_hook(["a", "b"])
        self.assertTrue(ctx.startswith("## Hindsight knowledge pages"), ctx)
        self.assertIn("### Pagina A\n\ncontenuto-a\n\n### Pagina B\n\ncontenuto-b", ctx)
        self.assertTrue(ctx.endswith("Verify mutable facts against the repo."), ctx)

    def test_missing_first_page_counts_as_ready(self):
        ctx = self.run_hook(["non-esiste", "b"])
        self.assertNotIn("non-esiste", ctx)
        self.assertIn("### Pagina B", ctx)

    def test_waits_until_server_ready(self):
        Backend.unavailable = 2
        ctx = self.run_hook(["a", "b"])
        self.assertIn("### Pagina A", ctx)
        self.assertIn("### Pagina B", ctx)

    def test_gate_off_makes_no_request(self):
        ctx = self.run_hook(["a"], HS_CFG_MENTAL_MODELS_INJECT_ON_START="0")
        self.assertEqual(ctx, "")
        self.assertEqual(Backend.paths, [])

    def test_one_content_request_per_page(self):
        # La prima GET fa da readiness e si riusa; gli id doppi si scaricano una volta.
        ctx = self.run_hook(["a", "a", "b"])
        self.assertEqual(
            Backend.paths,
            ["/mental-models/a?detail=content", "/mental-models/b?detail=content"],
        )
        self.assertEqual(ctx.count("### Pagina A"), 1)


if __name__ == "__main__":
    unittest.main()
