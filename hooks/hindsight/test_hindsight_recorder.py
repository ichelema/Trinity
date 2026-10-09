#!/usr/bin/env python
"""Test del recorder dei golden (ICH-173, lib/hindsight_recorder.py).

Ogni caso gira in un processo Python a se': il recorder sostituisce urlopen,
subprocess.check_output, sys.stdout e sys.exit e registra un atexit, cose da
non fare nel processo dei test. XDG_CACHE_HOME punta a una dir temporanea,
quindi record e stato non toccano la cache reale. L'e2e del recall con il
worker --queued sta in test_hindsight_recall_hook.py.
"""

from __future__ import annotations

import glob
import json
import os
import shutil
import subprocess
import sys
import tempfile
import textwrap
import threading
import time
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

HERE = os.path.dirname(os.path.abspath(__file__))
LIB = os.path.join(HERE, "lib")
# Path esplicito: su Windows "bash" sarebbe la bash WSL (vedi test_hindsight_recall_hook).
BASH = shutil.which("bash") or "bash"
KEY_ENV = ("OPENAI_API_KEY", "TYPESAFE_API_KEY", "VOYAGE_API_KEY")
# Finta chiave OpenAI: non deve mai finire su disco.
KEY = "sk-canary-ABCDEFGHIJKLMNOPQRSTUVWX"


class Backend(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path == "/missing":
            self._send(404, {"detail": "nope"})
        elif self.path == "/slow":
            time.sleep(1.0)
            self._send(200, {"slow": True})
        elif self.path == "/stall":
            # 10 byte su 100 promessi, poi silenzio: solo la deadline sblocca il read.
            self.send_response(200)
            self.send_header("Content-Length", "100")
            self.end_headers()
            self.wfile.write(b"x" * 10)
            self.wfile.flush()
            time.sleep(5.0)
        elif self.path == "/key":
            self._send(200, {"echo": KEY})
        else:
            self._send(200, {"ok": True})

    def do_POST(self):
        self.rfile.read(int(self.headers.get("Content-Length") or 0))
        self._send(200, {"ok": True})

    def _send(self, status, body):
        data = json.dumps(body).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def log_message(self, format, *args):
        pass


class QuietServer(ThreadingHTTPServer):
    # I client di /slow e /stall chiudono prima della risposta: niente traceback
    # a video, e server_close non aspetta gli handler ancora in sleep.
    block_on_close = False

    def handle_error(self, request, client_address):
        pass


class RecorderTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = QuietServer(("127.0.0.1", 0), Backend)
        cls.url = f"http://127.0.0.1:{cls.server.server_address[1]}"
        threading.Thread(target=cls.server.serve_forever, daemon=True).start()

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.cache = os.path.join(self.tmp.name, "trinity")
        os.makedirs(self.cache)
        # Niente override HS_*, HOOK_INPUT o chiavi della shell di chi lancia i test.
        self.env = {
            k: v
            for k, v in os.environ.items()
            if not k.startswith(("HS_", "HINDSIGHT_", "HOOK_INPUT")) and k not in KEY_ENV
        }
        self.env.update(XDG_CACHE_HOME=self.tmp.name, PYTHONUTF8="1")

    def tearDown(self):
        self.tmp.cleanup()

    def run_script(self, body, script="hindsight-recall", args=(), env=None, pre=""):
        """body in un python a se', con il recorder avviato come negli hook;
        pre gira prima di start (fault injection)."""
        code = (
            f"import sys; sys.path.insert(0, {LIB!r})\n"
            + pre
            + f"import hindsight_recorder; hindsight_recorder.start({script!r})\n"
            + textwrap.dedent(body)
        )
        proc = subprocess.run(
            [sys.executable, "-c", code, *args],
            env={**self.env, **(env or {})},
            capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=60,
        )
        return proc, self.records(script)

    def golden_files(self, script):
        return sorted(glob.glob(os.path.join(self.cache, "hs-golden", script, "*.json")))

    def records(self, script):
        out = []
        for path in self.golden_files(script):
            with open(path, encoding="utf-8") as handle:
                out.append(json.load(handle))
        return out

    def test_http_git_stdout_and_exit_code_are_recorded(self):
        proc, records = self.run_script(f"""
            import json, subprocess, threading, urllib.error, urllib.request
            req = urllib.request.Request(
                {self.url!r} + "/ok", data=json.dumps({{"q": "x"}}).encode(), method="POST")
            with urllib.request.urlopen(req, timeout=5) as r:
                json.load(r)
            try:
                urllib.request.urlopen({self.url!r} + "/missing", timeout=5)
            except urllib.error.HTTPError:
                pass
            try:
                urllib.request.urlopen({self.url!r} + "/slow", timeout=0.2).read()
            except OSError:
                pass
            threads = [
                threading.Thread(target=lambda: urllib.request.urlopen({self.url!r} + "/ok", timeout=5).read())
                for _ in range(3)
            ]
            for t in threads:
                t.start()
            for t in threads:
                t.join()
            subprocess.check_output([sys.executable, "-c", "print('hi')"], text=True)
            print("done")
            sys.exit(3)
        """)
        self.assertEqual(proc.returncode, 3, proc.stderr)
        self.assertEqual(proc.stdout, "done\n")
        [rec] = records
        self.assertEqual((rec["version"], rec["script"], rec["exit_code"]), (1, "hindsight-recall", 3))
        self.assertEqual(rec["stdout"], "done\n")
        self.assertIsNone(rec["exception"])
        post, missing, slow = rec["http"][:3]
        self.assertEqual((post["method"], post["status"], post["timeout"]), ("POST", 200, 5))
        self.assertEqual(post["request_body"], {"q": "x"})
        self.assertEqual(post["response_body"], {"ok": True})
        self.assertEqual(missing["status"], 404)
        self.assertIn("404", missing["error"])
        self.assertIsNone(slow["status"])
        self.assertTrue(slow["error"])
        fanout = rec["http"][3:]
        self.assertEqual(len(fanout), 3)
        self.assertTrue(all(ex["response_body"] == {"ok": True} for ex in fanout))
        self.assertTrue(all(ex["thread"] != "MainThread" for ex in fanout))
        [call] = rec["subprocess"]
        self.assertEqual(call["args"][1:], ["-c", "print('hi')"])
        self.assertEqual(call["output"], "hi\n")
        self.assertFalse(rec["redacted"])

    def test_uncaught_exception_and_fallthrough_exit_codes(self):
        proc, [rec] = self.run_script("raise ValueError('boom')\n")
        self.assertEqual((proc.returncode, rec["exit_code"]), (1, 1))
        self.assertIn("ValueError: boom", rec["exception"])
        shutil.rmtree(os.path.join(self.cache, "hs-golden"))
        proc, [rec] = self.run_script("pass\n")
        self.assertEqual((proc.returncode, rec["exit_code"], rec["stdout"]), (0, 0, ""))

    def test_no_secret_reaches_disk(self):
        hook_input = json.dumps({"session_id": "s1", "prompt": "password=hunter2hunter2"})
        proc, [rec] = self.run_script(f"""
            import json, urllib.request
            req = urllib.request.Request(
                {self.url!r} + "/ok", method="POST",
                data=json.dumps({{"api_key": "zzz-not-a-real-key", "text": "testo innocuo"}}).encode(),
                headers={{"Authorization": "Bearer {KEY}"}})
            urllib.request.urlopen(req, timeout=5).read()
            urllib.request.urlopen({self.url!r} + "/key", timeout=5).read()
        """, env={"OPENAI_API_KEY": KEY, "HOOK_INPUT": hook_input})
        self.assertEqual(proc.returncode, 0, proc.stderr)
        with open(self.golden_files("hindsight-recall")[0], encoding="utf-8") as handle:
            raw = handle.read()
        for secret in (KEY, "hunter2hunter2", "zzz-not-a-real-key", "Bearer"):
            self.assertNotIn(secret, raw)
        self.assertTrue(rec["redacted"])
        self.assertEqual(rec["stdin"]["prompt"], "[REDACTED]")
        self.assertEqual(rec["http"][0]["request_body"]["text"], "testo innocuo")
        self.assertEqual(
            rec["keys_present"],
            {"OPENAI_API_KEY": True, "TYPESAFE_API_KEY": False, "VOYAGE_API_KEY": False},
        )

    def test_recorder_failure_keeps_stdout_and_exit_code(self):
        # hs-golden e' un file: la scrittura del record fallisce, l'hook no.
        open(os.path.join(self.cache, "hs-golden"), "w").close()
        proc, records = self.run_script("print('out')\n")
        self.assertEqual((proc.returncode, proc.stdout, records), (0, "out\n", []))
        self.assertIn("[hs-record]", proc.stderr)

    def test_start_failure_keeps_stdout_and_exit_code(self):
        # Errore nell'installazione dei wrapper (qui atexit.register): start non
        # solleva, l'hook prosegue e l'errore resta su stderr.
        proc, records = self.run_script(
            "print('out')\n", pre="import hindsight_recorder; hindsight_recorder.atexit = None\n"
        )
        self.assertEqual((proc.returncode, proc.stdout, records), (0, "out\n", []))
        self.assertIn("[hs-record] AttributeError", proc.stderr)

    def test_read_with_deadline_still_enforced(self):
        proc, [rec] = self.run_script(f"""
            import time, urllib.request
            from hindsight_recall_filter import read_with_deadline
            r = urllib.request.urlopen({self.url!r} + "/stall", timeout=10)
            t = time.monotonic()
            try:
                read_with_deadline(r, time.monotonic() + 0.5)
            except OSError:
                pass
            print(round(time.monotonic() - t, 1))
        """)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        # Senza la deadline il read aspetterebbe la chiusura del server (5 s).
        self.assertLess(float(proc.stdout), 3.0)
        self.assertIn("read_error", rec["http"][0])

    def test_state_and_transcript_are_snapshotted(self):
        transcript = os.path.join(self.tmp.name, "t.jsonl")
        with open(transcript, "w", encoding="utf-8") as handle:
            handle.writelines(f'{{"n": {i}}}\n' for i in range(250))
        queue = os.path.join(self.cache, "hs-retain-queue")
        os.makedirs(queue)
        entry = os.path.join(queue, "1700000000000000-1.json")
        with open(entry, "w", encoding="utf-8") as handle:
            json.dump({"session_id": "s1", "transcript_path": transcript}, handle)
        state = os.path.join(self.cache, "hs-retain-state.json")
        with open(state, "w", encoding="utf-8") as handle:
            json.dump({"a": 1}, handle)
        open(os.path.join(self.cache, "hs-python-real.path"), "w").close()
        proc, [rec] = self.run_script(
            f"""
            import json, os
            os.remove({entry!r})
            with open({state!r}, "w") as f:
                json.dump({{"a": 2}}, f)
            """,
            script="hindsight-retain-worker",
            args=("--queued", "s1"),
            env={"HOOK_INPUT": json.dumps({"session_id": "parent"})},
        )
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertEqual((rec["argv"], rec["session_id"]), (["--queued", "s1"], "s1"))
        # HOOK_INPUT ereditato dal prompt che ha lanciato il worker: non e' il suo input.
        self.assertIsNone(rec["stdin"])
        before, after = rec["state_before"], rec["state_after"]
        key = "hs-retain-queue/1700000000000000-1.json"
        self.assertEqual(before[key]["content"]["session_id"], "s1")
        self.assertNotIn(key, after)
        self.assertEqual(before["hs-retain-state.json"]["content"], {"a": 1})
        self.assertEqual(after["hs-retain-state.json"]["content"], {"a": 2})
        self.assertFalse(any("hs-python" in name for name in before))
        tail = rec["transcripts"][transcript]
        self.assertEqual(len(tail["tail"]), 200)
        self.assertEqual(tail["tail"][-1], '{"n": 249}')
        self.assertFalse(tail["changed"])

    def test_entry_points_record_only_with_record_1(self):
        # Guardia nei punti d'ingresso: un record per failcheck, mm-inject e
        # worker --drain con HINDSIGHT_RECORD=1, nessuno con un altro valore.
        queue = os.path.join(self.tmp.name, "queue")
        os.makedirs(queue)
        env = {
            "HS_CFG_FAILCHECK_ENABLED": "false",
            "HS_CFG_MENTAL_MODELS_INJECT_ON_START": "false",
            "HS_RETAIN_QUEUE_DIR": queue,
            "HS_RETAIN_STATE_DIR": self.tmp.name,
        }
        runs = {
            "hindsight-failcheck": [BASH, os.path.join(HERE, "hindsight-failcheck.sh").replace(os.sep, "/")],
            "hindsight-mm-inject": [BASH, os.path.join(HERE, "hindsight-mm-inject.sh").replace(os.sep, "/")],
            "hindsight-retain-worker": [sys.executable, os.path.join(HERE, "hindsight-retain-worker.py"), "--drain"],
        }
        for value, expected in (("0", 0), ("1", 1)):
            for script, cmd in runs.items():
                with self.subTest(script=script, record=value):
                    proc = subprocess.run(
                        cmd, input="{}", env={**self.env, **env, "HINDSIGHT_RECORD": value},
                        capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=60,
                    )
                    self.assertEqual(proc.returncode, 0, proc.stderr)
                    records = self.records(script)
                    self.assertEqual(len(records), expected)
                    if records:
                        self.assertEqual(records[0]["exit_code"], 0)


if __name__ == "__main__":
    unittest.main()
