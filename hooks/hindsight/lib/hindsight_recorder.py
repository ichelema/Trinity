"""Recorder dei golden per il porting nella mod trinity-memory (ICH-173).

Con HINDSIGHT_RECORD=1 ogni esecuzione di un hook Python (recall, failcheck,
mm-inject) o del worker scrive UN record JSON in
<cache_dir>/hs-golden/<script>/<UTC>-<pid>.json: input, scambi HTTP, chiamate
git, stdout, exit code, file di stato prima/dopo, coda del transcript. Il
Python e' l'oracolo: il codice TS deve rifare le stesse richieste e dare lo
stesso output.

Si importa SOLO dietro la guardia nei punti d'ingresso: senza la variabile
questo modulo non viene caricato. Nessun errore del recorder cambia stdout o
exit code dell'hook: finisce su stderr con prefisso [hs-record]. Mai header
HTTP ne' variabili d'ambiente nel record (solo la presenza delle chiavi API).
"""

from __future__ import annotations

import atexit
import json
import os
import stat
import subprocess
import sys
import threading
import time
import traceback
import urllib.error
import urllib.request
from datetime import datetime, timezone
from typing import Any

# Doppio percorso come gli altri moduli di lib/: top-level negli hook, relativo
# se importato come package (lib.<modulo>).
try:
    from hindsight_config import cache_dir, load_config
    from hindsight_secrets import OUTCOME_SECRET_PATTERNS
except ImportError:
    from .hindsight_config import cache_dir, load_config
    from .hindsight_secrets import OUTCOME_SECRET_PATTERNS

VERSION = 1
REDACTED = "[REDACTED]"
KEY_ENV = ("OPENAI_API_KEY", "TYPESAFE_API_KEY", "VOYAGE_API_KEY")
# Campi il cui valore e' sempre un segreto. Match esatto sul nome: "token" per
# sottostringa redigerebbe max_tokens in ogni payload.
SECRET_KEYS = {
    "authorization", "api_key", "apikey", "x-api-key", "token", "access_token",
    "auth_token", "password", "passwd", "secret", "client_secret",
}
# ponytail: file di stato oltre questa soglia solo size e mtime (omitted: non
# rigiocabili); oggi la supera solo hs-reranker-degraded.log, che ruota a 5 MB.
MAX_INLINE = 256 * 1024
# Coda del transcript: le stesse righe di load_transcript del worker (il recall
# ne legge 80 con last_assistant_text). Solo per gli script che lo leggono.
TRANSCRIPT_LINES = 200
TRANSCRIPT_SCRIPTS = ("hindsight-recall", "hindsight-retain-worker")

_lock = threading.Lock()
_rec: dict = {}
_http: list = []
_calls: list = []
_t0 = 0.0
_name = ""


def start(script: str) -> None:
    """Avvia la registrazione di questo processo. Non solleva mai: un errore
    finisce su stderr e l'hook prosegue. Raccoglie prima tutto e solo alla fine
    installa i wrapper, tutti pass-through: anche un'installazione a meta'
    lascia l'hook com'era (senza atexit, solo nessun record)."""
    global _t0, _name
    try:
        _t0 = time.monotonic()
        argv = sys.argv[1:]
        # Il worker --queued/--drain eredita HOOK_INPUT dal prompt che l'ha
        # lanciato: il suo input vero e' l'entry di coda, gia' in state_before.
        raw = None if ("--queued" in argv or "--drain" in argv) else os.environ.get("HOOK_INPUT")
        stdin = _decode(raw)
        cfg = load_config()
        state = _snapshot(_state_paths(cfg))
        session = stdin.get("session_id") if isinstance(stdin, dict) else None
        if "--queued" in argv and argv.index("--queued") + 1 < len(argv):
            session = argv[argv.index("--queued") + 1]
        now = datetime.now(timezone.utc)
        _name = now.strftime("%Y%m%dT%H%M%S%fZ") + f"-{os.getpid()}.json"
        _rec.update(
            version=VERSION,
            script=script,
            argv=argv,
            pid=os.getpid(),
            ppid=os.getppid(),
            cwd=os.getcwd(),
            platform=sys.platform,
            started_at=now.isoformat(),
            session_id=session,
            stdin=stdin,
            config=cfg,
            keys_present={k: bool(os.environ.get(k)) for k in KEY_ENV},
            state_before=state,
            transcripts=_transcripts(stdin, state) if script in TRANSCRIPT_SCRIPTS else {},
        )
        urllib.request.urlopen = _recording_urlopen(urllib.request.urlopen)
        subprocess.check_output = _recording_check_output(subprocess.check_output)
        sys.stdout = _Tee(sys.stdout)
        sys.exit = _recording_exit(sys.exit)
        atexit.register(_finish)
    except Exception as exc:
        _warn(exc)


def _state_paths(cfg: dict) -> dict:
    """Nome logico -> path dei file di stato degli hook, risolti come fa il
    codice (override dei test e recall_pending_dir della config compresi). Per
    una directory si registrano tutti i suoi file."""
    base = cache_dir()
    env = os.environ.get
    return {
        "hs-retain-queue": env("HS_RETAIN_QUEUE_DIR") or base + "/hs-retain-queue",
        "hs-recall-pending": cfg.get("recall_pending_dir") or base + "/hs-recall-pending",
        "hs-retain-pending": env("HS_RETAIN_PENDING_DIR") or base + "/hs-retain-pending",
        "hs-invalidate-pending": env("HS_INVALIDATE_PENDING_DIR") or base + "/hs-invalidate-pending",
        "hs-repo-cache": base + "/hs-repo-cache",
        "hs-retain-state.json": (env("HS_RETAIN_STATE_DIR") or base) + "/hs-retain-state.json",
        "hs-retain-failed.log": base + "/hs-retain-failed.log",
        "hs-retain-failed.log.reading": base + "/hs-retain-failed.log.reading",
        "hs-failcheck-seen.json": base + "/hs-failcheck-seen.json",
        "hs-reranker-degraded.log": base + "/hs-reranker-degraded.log",
        "hs-reranker-notified.ts": base + "/hs-reranker-notified.ts",
    }


def _snapshot(paths: dict) -> dict:
    out: dict = {}
    for name, path in paths.items():
        if not os.path.isdir(path):
            _read_state(out, name, path)
            continue
        try:
            entries = sorted(os.listdir(path))
        except OSError:
            continue  # sparita tra isdir e listdir
        for entry in entries:
            if not entry.endswith((".lock", ".tmp")):
                _read_state(out, name + "/" + entry, os.path.join(path, entry))
    return out


def _read_state(out: dict, key: str, path: str) -> None:
    try:
        st = os.stat(path)
        if not stat.S_ISREG(st.st_mode):
            return
        item: dict = {"size": st.st_size, "mtime": st.st_mtime}
        if st.st_size > MAX_INLINE:
            item["omitted"] = True
        else:
            with open(path, "rb") as f:
                item["content"] = _decode(f.read())
        out[key] = item
    except OSError:
        pass  # sparito tra listdir e open: per lo snapshot non c'era


def _transcripts(stdin, state: dict) -> dict:
    """Coda dei transcript che lo script leggera': quello del prompt (recall) e
    quelli delle entry di coda (worker). size e mtime servono a dire in
    _finish se il file e' cresciuto durante l'esecuzione."""
    paths = [stdin.get("transcript_path")] if isinstance(stdin, dict) else []
    for key, item in state.items():
        content = item.get("content")
        if key.startswith("hs-retain-queue/") and isinstance(content, dict):
            paths.append(content.get("transcript_path"))
    out: dict = {}
    for path in paths:
        if not isinstance(path, str) or not path or path in out:
            continue
        try:
            st = os.stat(path)
            with open(path, encoding="utf-8", errors="replace") as f:
                tail = [line.rstrip("\n") for line in f.readlines()[-TRANSCRIPT_LINES:]]
            out[path] = {"size": st.st_size, "mtime": st.st_mtime, "tail": tail}
        except OSError:
            out[path] = {"missing": True}
    return out


def _decode(data):
    """bytes/str -> JSON parsato se valido, altrimenti testo; None resta None."""
    if data is None:
        return None
    if isinstance(data, (bytes, bytearray)):
        data = bytes(data).decode("utf-8", "replace")
    if not isinstance(data, str):
        return repr(type(data))  # body non bytes (file, iterabile): negli hook non capita
    try:
        return json.loads(data)
    except ValueError:
        return data


def _ms() -> int:
    return round((time.monotonic() - _t0) * 1000)


def _recording_urlopen(real):
    def urlopen(url, *args, **kwargs):
        data = getattr(url, "data", None)
        if data is None:
            data = args[0] if args else kwargs.get("data")
        if hasattr(url, "get_method"):
            method = url.get_method()
        else:
            method = "POST" if data is not None else "GET"
        exchange = {
            "t_ms": _ms(),
            "thread": threading.current_thread().name,
            "method": method,
            "url": getattr(url, "full_url", url),
            "timeout": kwargs.get("timeout", args[1] if len(args) > 1 else None),
            "request_body": _decode(data),
            "status": None,
            "error": None,
        }
        with _lock:
            _http.append(exchange)
        began = time.monotonic()
        try:
            response = real(url, *args, **kwargs)
        except urllib.error.HTTPError as exc:
            exchange["status"] = exc.code
            exchange["error"] = str(exc)
            raise
        except BaseException as exc:
            exchange["error"] = f"{type(exc).__name__}: {exc}"
            raise
        finally:
            exchange["elapsed_ms"] = round((time.monotonic() - began) * 1000)
        exchange["status"] = getattr(response, "status", None)
        _tee_read(response, exchange)
        return response

    return urlopen


def _tee_read(response, exchange: dict) -> None:
    """Sostituisce read dell'istanza: registra i byte che il chiamante legge
    davvero (non sempre il body intero) e gli errori di lettura. response.fp
    resta intatto, quindi read_with_deadline regola ancora il socket."""
    chunks: list = []
    exchange["_chunks"] = chunks
    real_read = response.read

    def read(*args, **kwargs):
        try:
            data = real_read(*args, **kwargs)
        except BaseException as exc:
            exchange["read_error"] = f"{type(exc).__name__}: {exc}"
            raise
        if data:
            chunks.append(data)
        return data

    response.read = read


def _recording_check_output(real):
    """git del worker (git_info) e della config (_git_root_and_slug): decidono
    bank, tag e metadata, quindi servono per rigiocare l'esecuzione."""

    def check_output(*args, **kwargs):
        cmd = args[0] if args else kwargs.get("args")
        call = {
            "t_ms": _ms(),
            "args": list(cmd) if isinstance(cmd, (list, tuple)) else cmd,
            "cwd": kwargs.get("cwd"),
            "timeout": kwargs.get("timeout"),
            "output": None,
            "error": None,
        }
        with _lock:
            _calls.append(call)
        try:
            out = real(*args, **kwargs)
        except BaseException as exc:
            call["error"] = f"{type(exc).__name__}: {exc}"
            raise
        call["output"] = out if isinstance(out, str) else bytes(out).decode("utf-8", "replace")
        return out

    return check_output


def _recording_exit(real):
    def _exit(status=None):
        _rec["exit_code"] = 0 if status is None else status if isinstance(status, int) else 1
        real(status)

    return _exit


class _Tee:
    """sys.stdout che scrive prima sullo stream vero e poi registra: stesso
    valore di ritorno, stesse eccezioni (BrokenPipe compreso). Il resto
    (flush, reconfigure, encoding, isatty) passa allo stream vero."""

    def __init__(self, stream):
        self._stream = stream
        self.parts: list = []

    def write(self, s):
        n = self._stream.write(s)
        self.parts.append(s)
        return n

    def __getattr__(self, name):
        return getattr(self._stream, name)


def _finish() -> None:
    try:
        with _lock:
            http = [dict(ex) for ex in _http]
            calls = [dict(c) for c in _calls]
        for ex in http:
            chunks = ex.pop("_chunks", None)
            ex["response_body"] = _decode(b"".join(chunks)) if chunks else None
        # Eccezione non gestita: l'interprete la lascia in sys.last_value prima
        # di atexit (exit 1); sys.exit non la imposta.
        err = getattr(sys, "last_value", None)
        code = _rec.get("exit_code")
        if code is None:
            code = 1 if err is not None else 0
        tee = sys.stdout
        _rec.update(
            duration_ms=_ms(),
            http=http,
            subprocess=calls,
            stdout="".join(tee.parts) if isinstance(tee, _Tee) else None,
            exit_code=code,
            exception=(
                "".join(traceback.format_exception(type(err), err, err.__traceback__))
                if err is not None
                else None
            ),
            state_after=_snapshot(_state_paths(_rec["config"])),
        )
        for path, item in _rec["transcripts"].items():
            if "size" in item:
                try:
                    st = os.stat(path)
                    item["changed"] = (st.st_size, st.st_mtime) != (item["size"], item["mtime"])
                except OSError:
                    item["changed"] = True
        literals = [v for v in (os.environ.get(k) for k in KEY_ENV) if v and len(v) >= 8]
        hits: list = []
        record = _scrub(_rec, literals, hits)
        record["redacted"] = bool(hits)
        _write(record)
    except BaseException as exc:
        _warn(exc)


def _scrub(value: Any, literals: list, hits: list) -> Any:
    """Copia ripulita del record. Una stringa in cui un pattern di
    hindsight_secrets trova un segreto diventa REDACTED per intero: i pattern
    nascono per search(), e sostituire solo il match lascerebbe pezzi di chiave
    (il corpo di un PEM). I valori letterali delle chiavi API spariscono
    ovunque; i campi con nome segreto perdono il valore. hits dice se e'
    successo: il record non e' piu' fedele all'esecuzione."""
    if isinstance(value, str):
        out = value
        for literal in literals:
            out = out.replace(literal, REDACTED)
        if any(p.search(out) for p in OUTCOME_SECRET_PATTERNS):
            out = REDACTED
        if out != value:
            hits.append(True)
        return out
    if isinstance(value, dict):
        clean = {}
        for key, item in value.items():
            if isinstance(key, str) and key.lower() in SECRET_KEYS and isinstance(item, str) and item:
                clean[key] = REDACTED
                hits.append(True)
            else:
                clean[key] = _scrub(item, literals, hits)
        return clean
    if isinstance(value, list):
        return [_scrub(item, literals, hits) for item in value]
    return value


def _write(record: dict) -> None:
    folder = os.path.join(cache_dir(), "hs-golden", record["script"])
    os.makedirs(folder, mode=0o700, exist_ok=True)
    path = os.path.join(folder, _name)
    tmp = path + ".tmp"
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        json.dump(record, f, ensure_ascii=False, indent=1, default=str)
    os.replace(tmp, path)


def _warn(exc: BaseException) -> None:
    try:
        print(f"[hs-record] {type(exc).__name__}: {exc}", file=sys.stderr)
    except Exception:
        pass
