"""hindsight-ensure-up.sh con un ssh finto nel PATH, senza rete.

Lo script gira su porte libere (copia con le porte locali sostituite, per non
toccare un tunnel vero su 8888/9999). Due casi:
- ssh esce subito (VPS irraggiungibile, auth fallita): l'hook smette di
  aspettare dopo TUNNEL_GRACE_SECS invece di arrivare a DEADLINE_SECS;
- il tunnel apre la porta dopo qualche secondo: l'hook aspetta ed esce pronto.
"""

from __future__ import annotations

import os
import shutil
import socket
import subprocess
import sys
import tempfile
import textwrap
import time
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
HOOK = os.path.join(HERE, "hindsight-ensure-up.sh")
# Path esplicito: su Windows "bash" sarebbe la bash WSL (vedi test_hindsight_recall_hook).
BASH = shutil.which("bash") or "bash"

# Finto server MCP: risponde a ogni POST con un initialize valido.
MOCK = textwrap.dedent('''
    import os, sys
    from http.server import BaseHTTPRequestHandler, HTTPServer
    class H(BaseHTTPRequestHandler):
        def do_POST(self):
            self.rfile.read(int(self.headers.get("Content-Length") or 0))
            body = b'{"jsonrpc":"2.0","id":1,"result":{"serverInfo":{"name":"mock"}}}'
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        def log_message(self, *a):
            pass
    open(sys.argv[2], "w").write(str(os.getpid()))
    HTTPServer(("127.0.0.1", int(sys.argv[1])), H).serve_forever()
''')

# ssh finto: "fail" esce come un ssh che non si connette; "up" dopo FAKE_DELAY
# secondi apre la porta locale del primo -L con il finto server MCP.
FAKE_SSH = textwrap.dedent('''\
    #!/usr/bin/env bash
    [ "$FAKE_MODE" = fail ] && exit 255
    while [ $# -gt 0 ]; do
        [ "$1" = -L ] && { port="${2#127.0.0.1:}"; port="${port%%:*}"; break; }
        shift
    done
    sleep "$FAKE_DELAY"
    exec "$MOCK_PY" "$MOCK_FILE" "$port" "$MOCK_PIDFILE"
''')


def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


class EnsureUpTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        port, port2 = free_port(), free_port()
        with open(HOOK, encoding="utf-8") as f:
            src = f.read()
        for old, new in (
            ("127.0.0.1:8888/mcp", f"127.0.0.1:{port}/mcp"),
            ("-L 127.0.0.1:8888:", f"-L 127.0.0.1:{port}:"),
            ("-L 127.0.0.1:9999:", f"-L 127.0.0.1:{port2}:"),
        ):
            self.assertIn(old, src, "porte cambiate nello script: aggiorna il test")
            src = src.replace(old, new)
        self.script = os.path.join(self.tmp, "ensure-up.sh")
        with open(self.script, "w", encoding="utf-8", newline="\n") as f:
            f.write(src)
        bindir = os.path.join(self.tmp, "bin")
        os.mkdir(bindir)
        with open(os.path.join(bindir, "ssh"), "w", encoding="utf-8", newline="\n") as f:
            f.write(FAKE_SSH)
        os.chmod(os.path.join(bindir, "ssh"), 0o755)
        with open(os.path.join(self.tmp, "mock.py"), "w", encoding="utf-8") as f:
            f.write(MOCK)
        self.pidfile = os.path.join(self.tmp, "mock.pid")
        # PATH nel formato nativo: su Windows la bash MSYS lo converte all'avvio.
        self.env = dict(
            os.environ,
            PATH=bindir + os.pathsep + os.environ["PATH"],
            HINDSIGHT_SSH_TUNNEL="vps-finta",
            MOCK_PY=sys.executable.replace(os.sep, "/"),
            MOCK_FILE=os.path.join(self.tmp, "mock.py").replace(os.sep, "/"),
            MOCK_PIDFILE=self.pidfile.replace(os.sep, "/"),
            FAKE_DELAY="3",
        )

    def tearDown(self):
        if os.path.exists(self.pidfile):
            try:
                with open(self.pidfile) as f:
                    os.kill(int(f.read()), 15)
            except (OSError, ValueError):
                pass
        shutil.rmtree(self.tmp, ignore_errors=True)

    def run_hook(self, mode):
        t = time.monotonic()
        r = subprocess.run([BASH, self.script.replace(os.sep, "/")], env=dict(self.env, FAKE_MODE=mode),
                           capture_output=True, text=True, timeout=60)
        self.assertEqual(r.returncode, 0, r.stderr)
        return r.stdout, time.monotonic() - t

    def test_dead_tunnel_stops_after_grace(self):
        out, elapsed = self.run_hook("fail")
        self.assertIn("non si e' aperto", out)
        self.assertLess(elapsed, 30, "ha aspettato fino a DEADLINE_SECS")

    def test_tunnel_opening_late_is_awaited(self):
        out, elapsed = self.run_hook("up")
        self.assertEqual(out, "")
        self.assertLess(elapsed, 15)


if __name__ == "__main__":
    unittest.main()
