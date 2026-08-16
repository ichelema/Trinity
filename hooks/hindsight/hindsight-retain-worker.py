"""Worker del retain automatico: valuta un payload di Stop e lo persiste.

Da ICH-86 lo Stop hook (hindsight-retain.sh) NON valuta piu' nulla: accoda il
payload del hook in hs-retain-queue/ e risponde subito. La valutazione avviene
DOPO, in due punti:
  - UserPromptSubmit (hindsight-recall.sh) -> retain_at_prompt(...): TUTTA la
    logica retain del prompt sta qui (l'hook recall ha solo poche righe di
    colla): consenso del pending (handle_retain_consent) in modo sincrono, poi
    evaluate_queued(session_id) in un thread daemon PARALLELO al recall —
    prende l'entry piu' recente della sessione ("deferred": il consenso per
    uncertain/context mancante viaggia in additionalContext, canale nascosto,
    e la domanda viene posta in coda alla risposta successiva); l'hook fonde
    l'output del gate al momento dell'emit (PromptRetain.gate_output);
  - chiusura (hindsight-sentinel.sh) -> `--drain`: valuta le code rimaste in
    modalita' "drain" (force, nessuna domanda: retain -> POST, uncertain -> skip).
Per ogni entry: parsea il transcript JSONL, costruisce la finestra, passa dal
gate semantico e fa POST a /memories con async=true.
Log diagnostici '[retain] ...' su STDERR (mai su stdout: importato dall'hook
recall, lo stdout e' il JSON del hook). Modalita' script senza flag
(tools/hindsight-check.sh, run manuali): valuta $HOOK_INPUT in "deferred" e
stampa 'HSGATE {json}' su stdout quando c'e' output.

Filosofia: salvare cio' che e' DURABILE e UTILE per future sessioni:
  - ultimo prompt utente (cosa ho chiesto)
  - ultima risposta sintetica (cosa l'agente ha fatto)
  - file Write/Edit (cosa e' cambiato)
  - comandi Bash significativi (git, build, deploy)
  - commit creati

Filtri rumore: niente output di tool, niente codice raw, niente env dump.
"""

from __future__ import annotations

import contextlib
import hashlib
import json
import os
import re
import subprocess
import sys
import threading
import time
import urllib.request
from datetime import datetime, timezone

# Config centralizzata (vedi hindsight.config.json). sys.path insert necessario
# sia quando il worker gira come script sia quando viene importato dai test.
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "lib"))
from hindsight_config import cache_dir, load_config, recall_bank_urls, retain_bank_url
from hindsight_debug import debug_log
from hindsight_retain_gate import (
    evaluate_retain,
    fallback_context,
    handle_retain_consent,
    save_retain_pending,
)

CFG = load_config()

# Payload del hook per la modalita' script senza flag (parse_hook). I test e
# l'hook recall passano invece l'entry direttamente a evaluate()/evaluate_queued().
HOOK_INPUT = os.environ.get("HOOK_INPUT", "")

# Entry di coda illeggibili piu' giovani di questa soglia vengono lasciate stare:
# potrebbero essere in scrittura da uno Stop concorrente (printf non atomico).
QUEUE_UNPARSABLE_GRACE_S = 60.0

NOISY_BASH_PREFIXES = ("ls", "cat", "head", "tail", "echo", "pwd", "which", "type ")
INTERESTING_BASH_PATTERNS = (
    "git ",
    "npm ",
    "pnpm ",
    "ruby ",
    "python ",
    "mise ",
    "curl ",
    "pip ",
    "gem ",
    "cargo ",
    "go ",
)


def parse_hook() -> dict:
    try:
        return json.loads(HOOK_INPUT)
    except Exception:
        return {}


def git_info(cwd: str) -> dict:
    """Best-effort estrazione info git dal cwd. Restituisce dict con chiavi
    'repo', 'branch', 'commit' (stringhe vuote se git non disponibile / non repo)."""
    if not cwd or not os.path.exists(cwd):
        return {"repo": "", "branch": "", "commit": ""}

    def _run(args: list[str]) -> str:
        try:
            out = subprocess.check_output(
                ["git", *args], cwd=cwd, stderr=subprocess.DEVNULL, timeout=5, text=True
            )
            return out.strip()
        except Exception:
            return ""

    repo_root = _run(["rev-parse", "--show-toplevel"])
    # repo: preferisci il nome dal remote 'origin' (identificativo STABILE del progetto,
    # invariante allo spostamento/rinomina della cartella locale). Fallback al basename
    # della root solo per repo locali senza remote. Cosi' il tag 'repo:' resta portabile.
    repo = ""
    remote = _run(["config", "--get", "remote.origin.url"])
    if remote:
        base = re.split(r"[/:]", remote.rstrip("/"))[-1]
        repo = base[:-4] if base.endswith(".git") else base
    if not repo and repo_root:
        repo = os.path.basename(repo_root)
    return {
        "repo": repo,
        "branch": _run(["branch", "--show-current"]),
        "commit": _run(["rev-parse", "--short=12", "HEAD"]),
    }


def build_tags(hook: dict, git: dict) -> list[str]:
    """Solo tag UTILI al recall filtering: pochi, stabili, bassa cardinalita' e
    PORTABILI. 'repo' viene dal NOME DEL REMOTE (vedi git_info), non dal nome
    cartella → resta valido se sposti/rinomini la cartella, e permette di filtrare
    per progetto. La provenienza completa (cwd, commit, source, session) resta nei
    metadata.

    REGOLA CHIAVE — i tag hanno DUE lavori, non uno:
      1. filtro di recall (visibilita')
      2. SCOPE di consolidation: le observation si fondono SOLO tra memorie con lo
         stesso set di tag, perche' la consolidation cerca con tags_match='all_strict'
         (AND, esclude untagged — consolidator.py:_find_related_observations). Un tag
         ad ALTA CARDINALITA' nello scope NON arricchisce: AVVELENA, perche' impedisce
         a observation identiche di fondersi e a proof_count di crescere.
      → Nei tag mettiamo SOLO valori stabili e a bassa cardinalita'.

    Esclusi di proposito:
      - session:<id>             → ALTA CARDINALITA': cambia ogni sessione. Nello scope
                                   all_strict frammenta la consolidation (una observation-
                                   silo per sessione, proof_count cross-sessione mai > 1) e
                                   ha zero valore di recall (non filtri mai 'solo questa
                                   sessione'). Resta nei metadata.session_id per provenienza.
      - source:claude-code-hook  → ridondante con 'claude-code' (stesso insieme)
      - cwd:<dir>                → ridondante + fragile (nome cartella); resta in metadata
      - commit:<hash>            → cardinalita' illimitata, zero uso nel recall (gia' nel git)
    """
    tags = ["claude-code"]  # filtro principale del recall
    if git["repo"]:
        tags.append(
            f"repo:{git['repo']}"
        )  # scoping progetto (nome repo dal remote, stabile)
    if git["branch"]:
        tags.append(
            f"branch:{git['branch']}"
        )  # scoping branch (portabile, bassa card.)
    return tags


def load_transcript(path: str, max_lines: int = 200) -> list[dict]:
    if not path or not os.path.exists(path):
        return []
    out = []
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as f:
            for line in f.readlines()[-max_lines:]:
                line = line.strip()
                if not line:
                    continue
                try:
                    out.append(json.loads(line))
                except Exception:
                    continue
    except Exception:
        return []
    return out


def count_transcript_lines(path: str) -> int:
    """Conta le righe non vuote del transcript (cheap, niente parse JSON).
    Misura robusta per rilevare la compaction anche oltre il window di load_transcript."""
    if not path or not os.path.exists(path):
        return 0
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as f:
            return sum(1 for line in f if line.strip())
    except Exception:
        return 0


def _retain_state_path() -> str:
    """File di stato per il tracking compaction. In cache_dir() (per-utente, 0700):
    su Linux /tmp e' scrivibile da tutti. Override per i test via HS_RETAIN_STATE_DIR."""
    d = os.environ.get("HS_RETAIN_STATE_DIR") or cache_dir()
    return os.path.join(d, "hs-retain-state.json")


# ---------------------------------------------------------------------------
# Coda dei payload Stop (ICH-86). Lo Stop hook scrive il HOOK_INPUT verbatim in
# <queue_dir>/<EPOCHREALTIME senza punto>-<pid>.json e non aspetta nessuno; il
# nome ordina lessicograficamente per istante di scrittura, quindi "il piu'
# recente" e' l'ultimo in sorted(). I consumatori (UserPromptSubmit e drain)
# prendono l'entry, cancellano i file e valutano. Una sola entry conta per
# sessione: la finestra e' calcolata sul transcript ATTUALE, quindi entry
# vecchie della stessa sessione darebbero la stessa fetta (o una piu' corta).
# ---------------------------------------------------------------------------


def retain_queue_dir() -> str:
    """Directory della coda. In cache_dir() (per-utente, 0700) perche' le entry
    contengono cwd e path del transcript. HS_RETAIN_QUEUE_DIR per i test."""
    return os.environ.get("HS_RETAIN_QUEUE_DIR") or cache_dir() + "/hs-retain-queue"


def _queue_files() -> list[str]:
    """Path delle entry *.json in ordine di nome (= ordine di scrittura)."""
    d = retain_queue_dir()
    try:
        names = sorted(n for n in os.listdir(d) if n.endswith(".json"))
    except OSError:
        return []
    return [os.path.join(d, n) for n in names]


def _read_queue_entry(path: str) -> dict | None:
    """Entry parsata, o None se illeggibile. Un file illeggibile piu' vecchio di
    QUEUE_UNPARSABLE_GRACE_S non e' piu' "in scrittura": si cancella per non
    rileggerlo a ogni prompt. Uno giovane si lascia stare (puo' essere a meta'
    della printf dello Stop hook)."""
    try:
        with open(path, "r", encoding="utf-8") as f:
            entry = json.load(f)
        if isinstance(entry, dict):
            return entry
    except Exception:
        pass
    try:
        if time.time() - os.path.getmtime(path) > QUEUE_UNPARSABLE_GRACE_S:
            os.remove(path)
    except OSError:
        pass
    return None


def _remove_quiet(path: str) -> None:
    try:
        os.remove(path)
    except OSError:
        pass


def dequeue_for_session(session_id: str) -> dict | None:
    """Entry PIU' RECENTE della sessione; cancella TUTTE le entry della sessione
    (anche le piu' vecchie: stessa finestra, valutarle sarebbe lavoro doppio).
    Le altre sessioni restano in coda. None senza session_id o senza entry."""
    if not session_id:
        return None
    newest = None
    matched: list[str] = []
    for path in _queue_files():
        entry = _read_queue_entry(path)
        if entry is None or entry.get("session_id") != session_id:
            continue
        matched.append(path)
        newest = entry
    for path in matched:
        _remove_quiet(path)
    return newest


def drain_queue() -> list[dict]:
    """Svuota la coda: una entry per sessione (la piu' recente), in ordine di
    scrittura; tutti i file parsabili vengono cancellati. Entry senza session_id
    restano distinte (non si sa se sono la stessa sessione). Usata da --drain."""
    latest: dict[str, dict] = {}
    for path in _queue_files():
        entry = _read_queue_entry(path)
        if entry is None:
            continue
        key = str(entry.get("session_id") or "") or path
        latest[key] = entry
        _remove_quiet(path)
    return list(latest.values())


def drop_unanswered_tail(entries: list[dict]) -> list[dict]:
    """Toglie i messaggi user in coda dopo l'ULTIMO messaggio assistant. A
    UserPromptSubmit il transcript puo' gia' contenere il prompt appena
    inviato (e i suoi wrapper <system-reminder>): non e' un turno completato e
    farebbe scivolare la finestra di un turno rispetto a quella che lo Stop
    avrebbe visto. Senza nessun assistant non c'e' nulla di completato: []."""
    def role_of(e) -> str | None:
        if not isinstance(e, dict):
            return None
        msg = e.get("message")
        return (msg.get("role") if isinstance(msg, dict) else None) or e.get("type")

    roles = [role_of(e) for e in entries]
    if "assistant" not in roles:
        return []
    last_assistant = len(roles) - 1 - roles[::-1].index("assistant")
    return list(entries[: last_assistant + 1]) + [
        e for e, r in zip(entries[last_assistant + 1 :], roles[last_assistant + 1 :])
        if r != "user"
    ]


@contextlib.contextmanager
def _state_lock(path: str, timeout: float = 5.0):
    """Lock interprocesso best-effort sul file di stato condiviso (flock su POSIX,
    msvcrt su Windows). Serializza il read-modify-write di piu' worker Stop concorrenti
    (piu' finestre Claude Code sullo stesso utente): senza, l'ultimo writer sovrascrive
    l'update dell'altra sessione (lost update su stop_count e line_count/chunk).
    Best-effort: se il lock non si prende entro timeout, procede senza — il throttling
    non e' critico e bloccare un worker async sarebbe peggio del lost update che evita.
    Il lock e' legato al fd, quindi si rilascia da solo se il worker viene killato."""
    lock_path = path + ".lock"
    f = release = None
    # Setup in un try SENZA yield: un errore qui (import, open, acquire) degrada a
    # "procedi senza lock". Lo yield deve stare FUORI da questo try: se ci finisse
    # dentro, un'eccezione nel CORPO del with rientrerebbe qui via throw(), l'except
    # farebbe un secondo yield e il chiamante riceverebbe RuntimeError("generator
    # didn't stop after throw()") che maschera l'errore originale.
    try:
        try:
            import fcntl

            def acquire(fd):
                fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)

            def _release(fd):
                fcntl.flock(fd, fcntl.LOCK_UN)
        except ImportError:
            import msvcrt

            def acquire(fd):
                msvcrt.locking(fd, msvcrt.LK_NBLCK, 1)

            def _release(fd):
                msvcrt.locking(fd, msvcrt.LK_UNLCK, 1)
        f = open(lock_path, "a+")
        deadline = time.monotonic() + timeout
        while True:
            try:
                # msvcrt.locking blocca dalla posizione corrente: seek(0) cosi' tutti
                # i worker contendono lo stesso byte 0 (per flock la posizione e' ininfluente).
                f.seek(0)
                acquire(f.fileno())
                release = _release
                break
            except OSError:
                if time.monotonic() >= deadline:
                    break  # timeout: procede senza lock (best-effort)
                time.sleep(0.05)
    except Exception:
        pass  # qualunque problema col lock non deve bloccare il retain
    try:
        yield
    finally:
        if f is not None:
            if release is not None:
                try:
                    f.seek(0)
                    release(f.fileno())
                except Exception:
                    pass
            f.close()


def compute_document_id(session_id: str, line_count: int) -> str | None:
    """document_id stabile per sessione → il server fa upsert invece di duplicare.
    Guardia compaction: se il transcript si accorcia (line_count < ultimo visto),
    incrementa un suffisso chunk per non sovrascrivere il documento pre-compaction.
    Ritorna None se session_id assente (il server genera un id casuale)."""
    if not session_id:
        return None
    path = _retain_state_path()
    with _state_lock(path):
        try:
            with open(path, "r", encoding="utf-8") as f:
                state = json.load(f)
        except Exception:
            state = {}
        if not isinstance(state, dict):
            state = {}  # file avvelenato (JSON valido ma non-dict): auto-ripara
        entry = state.get(session_id) or {}
        chunk = entry.get("chunk", 0)
        if line_count < entry.get("line_count", 0):
            chunk += 1
        # merge: preserva altri campi (es. stop_count del throttling)
        entry["line_count"] = line_count
        entry["chunk"] = chunk
        state[session_id] = entry
        _write_retain_state(path, state)
    return session_id if chunk == 0 else f"{session_id}-c{chunk}"


def _write_retain_state(path: str, state: dict) -> None:
    """Scrive lo stato in modo atomico (best-effort). Cappa la crescita del file."""
    if len(state) > 5000:
        for k in sorted(state)[: len(state) // 2]:
            del state[k]
    try:
        tmp = path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(state, f)
        # os.replace su Windows fallisce con PermissionError se un altro processo
        # tiene aperto path per un istante (antivirus/indexer, o il worker Stop
        # precedente): sotto _state_lock la RMW e' serializzata, ma questa flakiness
        # del rename resta e perderebbe l'update in silenzio. Ritenta brevemente.
        for attempt in range(5):
            try:
                os.replace(tmp, path)
                return
            except PermissionError:
                if attempt == 4:
                    raise
                time.sleep(0.02)
    except Exception:
        pass


def should_retain_now(
    session_id: str, force: bool = False, every_n: int | None = None
) -> bool:
    """Throttling: ritiene un Stop ogni N (default da HS_RETAIN_EVERY_N, fallback 3).
    Riduce le ri-estrazioni LLM ridondanti su sessioni lunghe. Il contatore avanza
    a ogni entry di coda CONSUMATA (una per Stop): stessa cadenza di quando il
    worker girava nello Stop. force=True (drain a fine sessione, HS_RETAIN_FORCE)
    ritiene sempre, per catturare la coda della sessione. Senza session_id
    o con N<=1 ritiene sempre (nessun throttling)."""
    if every_n is None:
        every_n = max(1, int(CFG.get("retain_every_n_turns", 3)))
    if force or not session_id or every_n <= 1:
        return True
    path = _retain_state_path()
    with _state_lock(path):
        try:
            with open(path, "r", encoding="utf-8") as f:
                state = json.load(f)
        except Exception:
            state = {}
        if not isinstance(state, dict):
            state = {}  # file avvelenato (JSON valido ma non-dict): auto-ripara
        entry = state.get(session_id) or {}
        cnt = entry.get("stop_count", 0) + 1
        entry["stop_count"] = cnt
        state[session_id] = entry
        _write_retain_state(path, state)
    return cnt % every_n == 0


def note_gate_error(session_id: str) -> bool:
    """Errore tecnico del gate (fail-closed): rollback di stop_count di 1 (min 0)
    cosi' la prossima valutazione rivede una finestra che conserva 3 dei 4 turni,
    e flag gate_error_notified nella stessa entry. Ritorna True se e' la PRIMA
    notifica della sessione (il chiamante emette il systemMessage solo allora).
    Senza session_id: nessuno stato, ritorna True. Se la valutazione era `force`
    (HS_RETAIN_FORCE del check) o every_n<=1 il contatore
    non era salito: il decremento e' innocuo (clamp a 0; al piu' la prossima
    valutazione slitta di uno Stop), non vale un ramo dedicato."""
    if not session_id:
        return True
    path = _retain_state_path()
    with _state_lock(path):
        try:
            with open(path, "r", encoding="utf-8") as f:
                state = json.load(f)
        except Exception:
            state = {}
        if not isinstance(state, dict):
            state = {}  # file avvelenato (JSON valido ma non-dict): auto-ripara
        entry = state.get(session_id) or {}
        entry["stop_count"] = max(0, entry.get("stop_count", 0) - 1)
        first = not entry.get("gate_error_notified", False)
        entry["gate_error_notified"] = True
        state[session_id] = entry
        _write_retain_state(path, state)
    return first


# Anti-feedback-loop: rimuove blocchi-memoria iniettati dal recall hook prima di
# ritenere il testo. Senza strip, una memoria citata nel turno verrebbe ri-ritenuta
# e la memoria "mangerebbe se stessa". Match precisi su marcatori che controlliamo:
#   - <hindsight_memories>...</hindsight_memories>  (forma a tag, difensiva)
#   - "## Hindsight persistent memory ... Verify mutable facts against the repo."
#     (blocco markdown iniettato da hindsight-recall.sh: header e trailer fissi)
#   - "## Hindsight knowledge pages ... Verify mutable facts against the repo."
#     (blocco iniettato a SessionStart da hindsight-mm-inject.sh)
_MEMORY_BLOCK_RE = re.compile(
    r"<hindsight_memories>.*?</hindsight_memories>"
    r"|## Hindsight (?:persistent memory|knowledge pages|recall debug|retain debug).*?Verify mutable facts against the repo\.",
    re.DOTALL,
)


def strip_memory_block(text: str) -> str:
    """Rimuove i blocchi-memoria iniettati. Restituisce il testo ripulito."""
    if not text:
        return text
    return _MEMORY_BLOCK_RE.sub("", text).strip()


def extract_text(content) -> str:
    """Da content (str o list di blocks) estrae solo il testo umano."""
    if isinstance(content, str):
        return content.strip()
    if isinstance(content, list):
        parts = []
        for b in content:
            if isinstance(b, dict) and b.get("type") == "text":
                parts.append((b.get("text") or "").strip())
        return "\n".join(p for p in parts if p)
    return ""


def summarize(entries: list[dict]) -> dict:
    last_user_prompt = ""
    last_assistant_text = ""
    files_modified: list[str] = []
    bash_cmds: list[str] = []

    for e in entries:
        etype = e.get("type")
        msg = e.get("message") or {}
        role = msg.get("role") or etype

        if role == "user":
            txt = strip_memory_block(extract_text(msg.get("content")))
            if txt and not txt.startswith("<"):
                last_user_prompt = txt

        elif role == "assistant":
            content = msg.get("content") or []
            if isinstance(content, list):
                for b in content:
                    if not isinstance(b, dict):
                        continue
                    if b.get("type") == "text":
                        t = strip_memory_block((b.get("text") or "").strip())
                        if t:
                            last_assistant_text = t
                    elif (
                        CFG.get("retain_tool_calls", False)
                        and b.get("type") == "tool_use"
                    ):
                        tool = b.get("name") or ""
                        inp = b.get("input") or {}
                        if tool in ("Write", "Edit", "MultiEdit"):
                            fp = inp.get("file_path") or ""
                            if fp and fp not in files_modified:
                                files_modified.append(fp)
                        elif tool == "Bash":
                            cmd = (inp.get("command") or "").strip()
                            if not cmd:
                                continue
                            first = cmd.split("\n", 1)[0][:200]
                            if any(first.startswith(p) for p in NOISY_BASH_PREFIXES):
                                continue
                            if any(p in first for p in INTERESTING_BASH_PATTERNS):
                                if first not in bash_cmds:
                                    bash_cmds.append(first)

    trunc = CFG["retain_text_truncate"]
    return {
        "last_user_prompt": last_user_prompt[:trunc],
        "last_assistant_text": last_assistant_text[:trunc],
        "files_modified": files_modified[-CFG["retain_max_files"] :],
        "bash_cmds": bash_cmds[-CFG["retain_max_cmds"] :],
    }


def build_content(hook: dict, summary: dict) -> str | None:
    if not summary["last_user_prompt"] and not summary["files_modified"]:
        return None
    parts = [
        "Claude Code session activity.",
        f"Timestamp: {datetime.now(timezone.utc).isoformat()}",
        f"CWD: {hook.get('cwd', '')}",
        f"Session: {hook.get('session_id', '')}",
        "",
    ]
    if summary["last_user_prompt"]:
        parts += ["## Last user prompt", summary["last_user_prompt"], ""]
    if summary["last_assistant_text"]:
        parts += ["## Last assistant text", summary["last_assistant_text"], ""]
    if summary["files_modified"]:
        parts += (
            ["## Files modified"] + [f"- {p}" for p in summary["files_modified"]] + [""]
        )
    if summary["bash_cmds"]:
        parts += (
            ["## Notable commands"] + [f"- {c}" for c in summary["bash_cmds"]] + [""]
        )
    return "\n".join(parts).strip()


# ---------------------------------------------------------------------------
# Modalita' "chunked" (sliding window) — ispirata al plugin ufficiale Hindsight.
# Invece di sovrascrivere un unico documento-sessione con l'ultimo scambio
# (lossy: vedi build_content/summarize), salva FETTE immutabili della
# conversazione, ognuna con un document_id derivato dal contenuto (univoco tra
# fette diverse, stabile sui replay della stessa finestra). La finestra
# copre gli ultimi (retain_every_n_turns + retain_overlap_turns) turni: l'overlap
# ricuce i confini tra fette consecutive cosi' nessun ragionamento a cavallo va
# perso. La ridondanza tra fette viene assorbita dalla consolidation del server
# (merge per proof_count). Un "turno" inizia a ogni messaggio user.
# ---------------------------------------------------------------------------


def _iter_role_messages(entries: list[dict]) -> list[dict]:
    """Lista ordinata dei soli messaggi user/assistant, con il loro content grezzo."""
    msgs = []
    for e in entries:
        msg = e.get("message") or {}
        role = msg.get("role") or e.get("type")
        if role in ("user", "assistant"):
            msgs.append({"role": role, "content": msg.get("content")})
    return msgs


def _human_user_text(content) -> str:
    """Testo UMANO di un messaggio user; stringa vuota per i messaggi sintetici.
    Nel transcript anche i tool_result hanno ruolo user (content senza blocchi
    text) e i wrapper <system-reminder>/<command-...> iniziano con "<": nessuno
    dei due e' un turno di dialogo. E' il criterio unico usato sia per i confini
    di finestra sia per i turni raccolti da summarize_window."""
    txt = strip_memory_block(extract_text(content))
    if txt and not txt.startswith("<"):
        return txt
    return ""


def slice_last_turns_by_user_boundary(messages: list[dict], turns: int) -> list[dict]:
    """Ultimi N turni, dove un turno inizia a un messaggio user con testo UMANO.
    Cammina all'indietro contando i confini. Contare ogni messaggio ruolo-user
    (come il port originale di sliceLastTurnsByUserBoundary) consumava la
    finestra con gli pseudo-turni muti dei tool_result: fette con soli testi
    assistant e prompt umani spinti fuori (visto 2026-08-12)."""
    if not messages or turns <= 0:
        return []
    seen = 0
    start = -1
    for i in range(len(messages) - 1, -1, -1):
        if messages[i]["role"] == "user" and _human_user_text(messages[i]["content"]):
            seen += 1
            if seen >= turns:
                start = i
                break
    return messages[start:] if start != -1 else list(messages)


def summarize_window(entries: list[dict], window_turns: int) -> dict:
    """Come summarize() ma sull'intera finestra di window_turns turni: raccoglie
    la sequenza (role, text) della conversazione + file/comandi della finestra."""
    window = slice_last_turns_by_user_boundary(
        _iter_role_messages(entries), window_turns
    )
    turns: list[tuple[str, str]] = []
    files_modified: list[str] = []
    bash_cmds: list[str] = []

    for m in window:
        role = m["role"]
        content = m["content"]
        if role == "user":
            txt = _human_user_text(content)
            if txt:
                turns.append(("user", txt))
        elif role == "assistant" and isinstance(content, list):
            texts = []
            for b in content:
                if not isinstance(b, dict):
                    continue
                if b.get("type") == "text":
                    t = strip_memory_block((b.get("text") or "").strip())
                    if t:
                        texts.append(t)
                # retain_tool_calls (default false, come il plugin ufficiale): i tool
                # non danno valore semantico alla memoria — i file sono nel git e il
                # testo dell'assistant gia' descrive cosa e' stato fatto. Off = niente
                # sezioni "Files modified"/"Notable commands", solo il dialogo.
                elif (
                    CFG.get("retain_tool_calls", False) and b.get("type") == "tool_use"
                ):
                    tool = b.get("name") or ""
                    inp = b.get("input") or {}
                    if tool in ("Write", "Edit", "MultiEdit"):
                        fp = inp.get("file_path") or ""
                        if fp and fp not in files_modified:
                            files_modified.append(fp)
                    elif tool == "Bash":
                        cmd = (inp.get("command") or "").strip()
                        if cmd:
                            first = cmd.split("\n", 1)[0][:200]
                            if not any(
                                first.startswith(p) for p in NOISY_BASH_PREFIXES
                            ) and any(p in first for p in INTERESTING_BASH_PATTERNS):
                                if first not in bash_cmds:
                                    bash_cmds.append(first)
            if texts:
                turns.append(("assistant", "\n".join(texts)))

    trunc = CFG["retain_text_truncate"]
    return {
        "turns": [(r, t[:trunc]) for r, t in turns],
        "files_modified": files_modified[-CFG["retain_max_files"] :],
        "bash_cmds": bash_cmds[-CFG["retain_max_cmds"] :],
    }


def build_content_chunk(hook: dict, summary: dict) -> str | None:
    """Content di una fetta: la conversazione multi-turno della finestra + file/comandi.
    Niente header Timestamp/CWD/Session (ICH-67): quei valori sono gia' nei
    metadata dell'item e nel campo timestamp — nel content sarebbero solo rumore
    per l'estrattore. Bonus: il content e' stabile per costruzione, quindi il
    document_id derivato dal suo hash resta identico sui replay."""
    if not summary["turns"] and not summary["files_modified"]:
        return None
    parts = ["## Conversation (recent turns)"]
    for role, text in summary["turns"]:
        parts += [f"[{role}] {text}", ""]
    if summary["files_modified"]:
        parts += (
            ["## Files modified"] + [f"- {p}" for p in summary["files_modified"]] + [""]
        )
    if summary["bash_cmds"]:
        parts += (
            ["## Notable commands"] + [f"- {c}" for c in summary["bash_cmds"]] + [""]
        )
    return "\n".join(parts).strip()


def gate_debug_context(gate, bank: str) -> str:
    """Blocco '## Hindsight retain debug' per systemMessage/additionalContext
    (retain_debug_in_context, speculare al debug del recall). Header e trailer
    combaciano con _MEMORY_BLOCK_RE: il retain successivo lo scarta
    (anti-feedback-loop)."""
    return (
        "## Hindsight retain debug\n\n"
        f"Gate: {gate.action} ({gate.reason})\n"
        f"Model: {CFG.get('retain_gate_model')}\n"
        f"Gate latency: {gate.latency_ms:.1f} ms\n"
        f"Bank: {bank}"
        + (f"\nPreview: {gate.preview}" if gate.preview else "")
        + (f"\nGate error (fail-closed): {gate.error}" if gate.error else "")
        + "\n\nUse as consultative context. Verify mutable facts against the repo."
    )


def gate_debug_output(gate, bank: str) -> dict:
    """JSON hook-output di solo debug: visibile (systemMessage) e nel contesto."""
    context = gate_debug_context(gate, bank)
    return {
        "systemMessage": context,
        "hookSpecificOutput": {
            "hookEventName": "UserPromptSubmit",
            "additionalContext": context,
        },
    }


def note_post_failure(msg: str) -> None:
    """Traccia DUREVOLE di una POST non arrivata al server (server giu', rete,
    bank irraggiungibile): non esiste nessuna async operation da interrogare,
    quindi hindsight-failcheck.sh — che fa GET operations?status=failed — e'
    cieco proprio qui. Stesso file e formato (ts \\t messaggio) di
    ops/hindsight-drain-retain.py; il failcheck lo raccoglie al prossimo prompt.
    Best-effort: un problema di scrittura non deve mascherare l'errore vero."""
    try:
        with open(
            os.path.join(cache_dir(), "hs-retain-failed.log"), "a", encoding="utf-8"
        ) as f:
            f.write(
                f"{datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')}\t{msg}\n"
            )
    except Exception:
        pass


def evaluate(hook: dict, mode: str = "deferred") -> tuple[int, dict | None]:
    """Valuta UN payload di Stop. Ritorna (rc, hook_output): hook_output e' il
    JSON per Claude Code (None = niente da dire); rc 1 solo se la POST non e'
    arrivata al server. mode:
      "deferred" -> chiamato a UserPromptSubmit dall'hook recall: throttling
                    normale; uncertain/context mancante -> pending + istruzione
                    in additionalContext (la domanda chiude la risposta successiva).
      "drain"    -> chiamato dal sentinel a fine sessione: force (nessun
                    throttling), nessun utente a cui chiedere: retain -> POST
                    (context di fallback se il gate non l'ha dato), uncertain e
                    errore del gate -> skip silenzioso."""
    # Interruttore master: se il retain automatico e' disattivato in config, esci
    # subito — niente parse del transcript, niente POST, niente estrazione LLM.
    if not CFG.get("retain_enabled", True):
        debug_log(CFG, "retain_skip", reason="disabled")
        return 0, None

    # Stop hook non passa 'prompt'; il filtro avviene in build_content (skip se
    # last_user_prompt+files_modified entrambi vuoti = turno senza contenuto utile).
    # drop_unanswered_tail: a UserPromptSubmit il transcript puo' gia' contenere
    # il prompt nuovo; la finestra deve essere quella del turno COMPLETATO.
    transcript = drop_unanswered_tail(load_transcript(hook.get("transcript_path", "")))
    if not transcript:
        debug_log(CFG, "retain_skip", reason="no_transcript")
        return 0, None

    # Modalita': "chunked" (default) salva fette immutabili con sliding window;
    # qualsiasi altro valore mantiene il vecchio comportamento legacy (un documento
    # per sessione, upsert, solo ultimo scambio — lossy).
    retain_mode = CFG.get("retain_mode", "chunked")
    if retain_mode == "chunked":
        window_turns = max(1, int(CFG.get("retain_every_n_turns", 3))) + int(
            CFG.get("retain_overlap_turns", 1)
        )
        summary = summarize_window(transcript, window_turns)
        content = build_content_chunk(hook, summary)
    else:
        summary = summarize(transcript)
        content = build_content(hook, summary)
    if not content:
        debug_log(CFG, "retain_skip", reason="no_content")
        return 0, None

    # Throttling: salta le entry non multiple di N per ridurre le ri-estrazioni
    # LLM ridondanti su sessioni lunghe. force nel drain di fine sessione (cattura
    # la coda) o via HS_RETAIN_FORCE. Il contatore avanza solo sui turni con
    # contenuto utile.
    session_id = hook.get("session_id") or ""
    force = mode == "drain" or bool(os.environ.get("HS_RETAIN_FORCE"))
    if not should_retain_now(session_id, force=force):
        print("[retain] skip: throttling (turno non multiplo di N, niente drain)", file=sys.stderr)
        debug_log(CFG, "retain_skip", reason="throttling", session=session_id[:8])
        return 0, None

    # Gate semantico pre-retain (ICH-67), DOPO il throttling cosi' paga solo sui
    # turni che salverebbero davvero. Attivo sempre (retain_enabled e' l'unico
    # interruttore): retain -> POST diretta silenziosa; skip -> niente;
    # uncertain -> POST in pending + domanda all'utente (ramo piu' sotto).
    # Un errore TECNICO del gate e' FAIL-CLOSED (ICH-73): nessun salvataggio,
    # notifica non bloccante una volta per sessione e rollback del contatore
    # cosi' la prossima valutazione rivede la finestra (con overlap: 3 turni su
    # 4 sopravvivono). Salvare "come prima del gate" con un LLM giu' produceva
    # memorie senza context e senza giudizio.
    gate = evaluate_retain(
        content, summary, recall_bank_urls(CFG, hook.get("cwd") or None), CFG
    )
    debug_log(
        CFG,
        "retain_gate",
        action=gate.action,
        reason=gate.reason,
        duplicates=len(gate.duplicate_of),
        latency_ms=gate.latency_ms,
        error=gate.error,
        preview=gate.preview[:300],
        mode=mode,
    )
    if gate.error:
        print(f"[retain] skip: gate error ({gate.error})", file=sys.stderr)
        if mode == "drain":
            # La sessione e' finita: nessuno a cui notificare, nessun "prossimo
            # turno" per cui fare rollback del contatore.
            debug_log(
                CFG,
                "retain_skip",
                reason="gate_error_drain",
                error=gate.error,
                session=session_id[:8],
            )
            return 0, None
        first = note_gate_error(session_id)
        debug_log(
            CFG,
            "retain_skip",
            reason="gate_error",
            error=gate.error,
            session=session_id[:8],
            notified=first,
        )
        # rc 0 anche qui: rc!=0 e' riservato alla POST non arrivata al server
        # (note_post_failure), etichetta sbagliata per un gate giu'.
        out: dict = {}
        if first:
            out["systemMessage"] = (
                "Hindsight: retain automatico non eseguito — errore tecnico del gate "
                f"({gate.error}). Nessuna memoria salvata per questa finestra; il "
                "prossimo turno riprova."
            )
        if CFG.get("retain_debug_in_context"):
            debug = gate_debug_context(gate, "-")
            out["systemMessage"] = "\n\n".join(
                filter(None, [out.get("systemMessage"), debug])
            )
            out["hookSpecificOutput"] = {
                "hookEventName": "UserPromptSubmit",
                "additionalContext": debug,
            }
        return 0, out or None
    if gate.action == "skip":
        print(f"[retain] skip: gate ({gate.reason})", file=sys.stderr)
        debug_log(CFG, "retain_skip", reason=f"gate_{gate.reason}", session=session_id[:8])
        if CFG.get("retain_debug_in_context"):
            return 0, gate_debug_output(gate, "-")
        return 0, None
    if mode == "drain" and gate.action == "uncertain":
        # Nessun utente a cui chiedere e nessun prompt successivo che possa
        # consumare un pending: l'uncertain a fine sessione si lascia cadere.
        print(f"[retain] skip: gate uncertain in drain ({gate.preview[:120]})", file=sys.stderr)
        debug_log(
            CFG,
            "retain_skip",
            reason="gate_uncertain_drain",
            session=session_id[:8],
            preview=gate.preview[:300],
        )
        return 0, None

    git = git_info(hook.get("cwd") or "")
    tags = build_tags(hook, git)

    # context: riga descrittiva del dominio prodotta dal GATE (legge gia' tutta
    # la finestra: una chiamata LLM in meno e un frame piu' ricco per
    # l'estrattore della "categoria secca" claude-code/<slug>). Puo' essere
    # vuota: in quel caso NON si inventa nulla qui — la POST va in pending e
    # il context lo propone Claude / lo indica l'utente al prompt successivo
    # (ramo pending piu' sotto; catena in handle_retain_consent, ICH-73).
    context = gate.context

    # metadata: filter values stringa (lo schema accetta dict[str,str]). Tutti i
    # valori opzionali vengono inclusi solo se non vuoti per non sporcare il dict.
    metadata = {"source": "claude-code-hook"}
    for k, v in (
        ("cwd", hook.get("cwd")),
        ("session_id", hook.get("session_id")),
        ("repo", git["repo"]),
        ("branch", git["branch"]),
        ("commit", git["commit"]),
    ):
        if v:
            metadata[k] = str(v)

    if mode == "drain" and not context:
        # In drain nessuno puo' proporre o dettare un context: si usa l'ultima
        # risorsa della catena del consenso (riga repo/branch, zero rete) invece
        # di perdere una finestra che il gate ha giudicato da ritenere.
        context = fallback_context(metadata)
        debug_log(
            CFG,
            "retain_context",
            context_source="fallback",
            context=context,
            session=session_id[:8],
        )

    # document_id: in chunked ogni fetta e' un documento con id derivato dal
    # CONTENUTO (fette diverse = documenti diversi, niente perdita tra retain;
    # fetta identica ri-presentata = stesso id, il server fa upsert invece di
    # duplicare — dedup replay esatto, ICH-67). Il content e' stabile per
    # costruzione: build_content_chunk non contiene piu' righe volatili. In legacy
    # resta l'id stabile per-sessione con guardia compaction (compute_document_id,
    # che fa upsert — verificato lossy sul testo non-ultimo).
    if retain_mode == "chunked":
        if session_id:
            digest = hashlib.sha256(content.encode("utf-8")).hexdigest()[:12]
            doc_id = f"{session_id}-{digest}"
        else:
            doc_id = None
    else:
        doc_id = compute_document_id(
            session_id,
            count_transcript_lines(hook.get("transcript_path", "")),
        )

    item = {
        "content": content,
        "context": context,
        "tags": tags,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "metadata": metadata,
    }
    if doc_id:
        item["document_id"] = doc_id

    payload = {"items": [item], "async": True}

    # Per log/dashboard: in chunked il summary ha 'turns' (non last_user_prompt/
    # last_assistant_text), quindi derivo prompt/assistant dal primo turno user e
    # dall'ultimo turno assistant della finestra — altrimenti i campi apparirebbero
    # vuoti nella dashboard pur essendo il content pieno. Fallback ai campi legacy.
    _turns = summary.get("turns") or []
    log_prompt = summary.get("last_user_prompt") or next(
        (t for r, t in _turns if r == "user"), ""
    )
    log_assistant = summary.get("last_assistant_text") or next(
        (t for r, t in reversed(_turns) if r == "assistant"), ""
    )

    # Bank di scrittura: env API_URL esplicita (test/override) ha precedenza,
    # poi bank.retain_bank risolto sul cwd della sessione ("auto" = slug repo;
    # il bank si auto-crea al primo retain, nessun provisioning).
    api_url = os.environ.get("API_URL") or retain_bank_url(CFG, hook.get("cwd") or None)

    # Pending + domanda (solo deferred: in drain uncertain e' gia' uscito e il
    # context e' gia' risolto sopra): la POST pronta va in pending (stessa
    # meccanica dei medium del recall ICH-66: file per session+cwd, TTL, consumo
    # singolo) e l'istruzione va a Claude via additionalContext, il canale
    # NASCOSTO di UserPromptSubmit (ICH-86: niente piu' decision:block, che qui
    # non esiste e comunque interromperebbe il prompt appena inviato). Claude
    # risponde al prompt corrente e mette la domanda come ULTIMA cosa della
    # risposta: retain_context_from_transcript legge last_assistant_text per
    # recuperare la «proposta». Ci si arriva per uncertain (come sempre) e, da
    # ICH-73, anche per retain/uncertain con context VUOTO: Claude propone una
    # riga di dominio e l'utente risponde si' / no / `context: …`. Il si' al
    # prompt successivo esegue la POST dall'hook recall (handle_retain_consent,
    # che risolve il context: esplicito -> gate -> proposta nel transcript ->
    # repo/branch); no/prompt nuovo la scartano. gate.error non arriva qui: e'
    # fail-closed piu' sopra.
    needs_context = not context
    if gate.action == "uncertain" or needs_context:
        if not save_retain_pending(
            session_id, hook.get("cwd") or "", api_url, payload, gate.preview
        ):
            # Senza pending affidabile (niente session_id / stato non scrivibile)
            # la domanda non potrebbe mantenere la promessa del si': non si salva.
            debug_log(CFG, "retain_skip", reason=f"gate_{gate.action}_no_pending")
            return 0, None
        # I testi delle DOMANDE restano identici (li riconoscono i test e la
        # regex della proposta); cambia solo la cornice: prima la risposta al
        # prompt corrente, poi la domanda in chiusura.
        if not needs_context:  # uncertain + context: domanda classica
            question = f"Vuoi che salvi questa memoria? — {gate.preview} (sì/no)"
            instruction = (
                "Hindsight retain gate was uncertain about the previous turn. "
                "Answer the current prompt normally first. Then, as the very last "
                f"thing in your reply, ask the user verbatim {question!r} and end "
                "the turn. Do not save anything yourself; a yes runs the pending "
                "save at the next prompt."
            )
        else:
            propose = (
                "Propose ONE short descriptive line for the technical domain of this "
                "window (subject and project, e.g. \"architettura del recall automatico "
                "Hindsight nel plugin Trinity\"; never a bare category), in the language "
                "of the conversation, and put it in place of <PROPOSTA>. "
            )
            if gate.action == "retain":
                question = "Salvo questa memoria con context «<PROPOSTA>»? (sì / no / context: …)"
                instruction = (
                    "Hindsight retain gate approved the previous turn but produced "
                    f"no context. {propose}"
                    "Answer the current prompt normally first. Then, as the very last "
                    f"thing in your reply, ask the user verbatim {question!r} and end "
                    f"the turn. Preview: {gate.preview}. Do not save anything yourself; "
                    "a yes (or a `context: …` reply) runs the pending save at the next "
                    "prompt."
                )
            else:  # uncertain senza context
                # rstrip('.') evita "…gate.. Context proposto": le preview del
                # gate sono frasi e finiscono quasi sempre col punto.
                question = (
                    f"Vuoi che salvi questa memoria? — {gate.preview.rstrip('.')}. "
                    "Context proposto: «<PROPOSTA>» (sì / no / context: …)"
                )
                instruction = (
                    "Hindsight retain gate was uncertain about the previous turn and "
                    f"produced no context. {propose}"
                    "Answer the current prompt normally first. Then, as the very last "
                    f"thing in your reply, ask the user verbatim {question!r} and end "
                    "the turn. Do not save anything yourself; a yes (or a `context: …` "
                    "reply) runs the pending save at the next prompt."
                )
        out = {
            "hookSpecificOutput": {
                "hookEventName": "UserPromptSubmit",
                "additionalContext": instruction,
            }
        }
        if CFG.get("retain_debug_in_context"):
            out["systemMessage"] = gate_debug_context(gate, api_url.rsplit("/", 1)[-1])
        debug_log(
            CFG,
            "retain_pending",
            action="saved",
            doc_id=doc_id,
            context=context,
            preview=gate.preview[:300],
        )
        return 0, out

    debug_log(
        CFG,
        "retain",
        doc_id=doc_id,
        bank=api_url.rsplit("/", 1)[-1],
        context=context,
        tags=tags,
        content_chars=len(content),
        mode=retain_mode,
        n_turns=len(_turns),
        prompt=log_prompt[:300],
        assistant=log_assistant[:300],
        files=summary.get("files_modified", []),
        cmds=summary.get("bash_cmds", []),
    )

    req = urllib.request.Request(
        api_url + "/memories",
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )

    try:
        with urllib.request.urlopen(req, timeout=10) as res:
            body = res.read().decode("utf-8", errors="replace")
            print(f"[retain] OK {res.status} {body[:200]}", file=sys.stderr)
            debug_log(
                CFG,
                "retain_result",
                doc_id=doc_id,
                status=res.status,
                response=body[:300],
            )
    except Exception as exc:
        print(f"[retain] FAIL {exc}", file=sys.stderr)
        debug_log(CFG, "retain_error", doc_id=doc_id, error=str(exc)[:200])
        note_post_failure(f"non arrivato al server — {exc}")
        return 1, None
    if CFG.get("retain_debug_in_context"):
        return 0, gate_debug_output(gate, api_url.rsplit("/", 1)[-1])
    return 0, None


def evaluate_queued(session_id: str, mode: str = "deferred") -> dict | None:
    """Entry point per l'hook recall a UserPromptSubmit: consuma l'entry di coda
    della sessione e la valuta; ritorna il JSON hook-output da fondere con quello
    del recall (None = niente). Non solleva MAI: un bug qui non deve rompere il
    prompt dell'utente (l'errore finisce nel debug log)."""
    try:
        entry = dequeue_for_session(session_id)
        if entry is None:
            return None
        _rc, out = evaluate(entry, mode)
        return out
    except Exception as exc:
        try:
            debug_log(
                CFG,
                "retain_error",
                error=f"{type(exc).__name__}: {exc}"[:300],
                session=(session_id or "")[:8],
                where="evaluate_queued",
            )
        except Exception:
            pass
        return None


# ---------------------------------------------------------------------------
# Lato UserPromptSubmit (ICH-86). Tutta la logica retain del prompt vive qui,
# hindsight-recall.sh la chiama con poche righe di colla:
#   1. consenso del pending (handle_retain_consent) SINCRONO: risponde alla
#      domanda del turno precedente e puo' consumare il suo pending;
#   2. gate differito (evaluate_queued) in un thread daemon, PARALLELO al
#      recall che l'hook fa subito dopo: la latenza aggiunta al prompt diventa
#      ~max(gate, recall) invece della somma (gate fino a 15s + POST 10s);
#   3. l'hook chiama gate_output(deadline) al momento dell'emit e fonde
#      l'eventuale output del gate nel suo unico JSON.
# L'ordine consenso -> gate resta quello di prima: il gate puo' creare il
# pending SUCCESSIVO e non deve calpestare quello ancora in attesa; e un "si'"
# non deve mai essere letto come risposta a una domanda non ancora posta.
# Niente redirect_stdout qui: e' globale al processo e dirotterebbe anche il
# print del JSON del thread principale — per questo i log '[retain]' vanno
# esplicitamente su stderr.
# ---------------------------------------------------------------------------


class PromptRetain:
    """Esito del lato retain di un prompt (retain_at_prompt) per l'hook recall.
    outcome: esito di handle_retain_consent (None = nessun pending);
    consent_output: JSON hook-output del consenso gia' formattato
    (systemMessage / additionalContext), {} se niente;
    notice: "Hindsight: memoria in attesa scartata — …" su prompt nuovo, altrimenti "";
    saved: True su outcome saved -> il chiamante scarta i medium pending del recall;
    stop_here: True su saved/error -> il chiamante emette consent_output ed esce
    senza recall (come sempre).
    Classe semplice e non @dataclass di proposito: il worker viene caricato per
    path (spec_from_file_location, fuori da sys.modules) dall'hook recall e dai
    test, e con `from __future__ import annotations` dataclasses risolve le
    annotazioni-stringa via sys.modules[cls.__module__] -> AttributeError."""

    def __init__(self, session_id: str = "") -> None:
        self.outcome: dict | None = None
        self.consent_output: dict = {}
        self.notice: str = ""
        self.saved: bool = False
        self.stop_here: bool = False
        # Stato privato del gate in parallelo: thread, box del risultato,
        # cache del join (gate_output e' idempotente: emit() e finish()
        # possono chiamarla entrambe).
        self._session_id: str = session_id or ""
        self._thread: threading.Thread | None = None
        self._box: dict = {}
        self._gate: dict | None = None

    def gate_output(self, deadline: float) -> dict:
        """Join del thread del gate entro deadline (time.monotonic). {} se non
        c'era gate, se ha dato niente, se e' andato in errore o se non ha
        finito in tempo. Idempotente: il risultato (anche il timeout) viene
        cachato, cosi' una seconda chiamata non ri-aspetta ne' cambia esito."""
        if self._gate is not None:
            return self._gate
        self._gate = {}
        thread = self._thread
        if thread is None:
            return self._gate
        try:
            thread.join(timeout=max(0.0, deadline - time.monotonic()))
            if thread.is_alive():
                # Il thread e' daemon: muore col processo dell'hook e la
                # finestra di questo turno va persa, come una mancata per
                # throttling. Accettabile e raro: la deadline e' ~55s contro
                # gate 15s + POST 10s; il pending, se c'e', e' gia' su disco e
                # l'overlap delle finestre ricuce il buco al prossimo turno.
                debug_log(
                    CFG,
                    "retain_skip",
                    reason="deferred_timeout",
                    session=self._session_id[:8],
                )
                return self._gate
            self._gate = dict(self._box.get("out") or {})
        except Exception as exc:
            debug_log(
                CFG,
                "retain_error",
                where="gate_output",
                error=f"{type(exc).__name__}: {exc}"[:300],
                session=self._session_id[:8],
            )
            self._gate = {}
        return self._gate


def _consent_output(outcome: dict) -> tuple[dict, str, bool, bool]:
    """Traduce l'esito di handle_retain_consent nei campi dell'hook:
    (consent_output, notice, saved, stop_here). Testi identici a quelli che
    l'hook recall stampava in proprio prima di ICH-86 (WP-D)."""
    action = outcome.get("action")
    if action == "saved":
        preview = outcome.get("preview") or ""
        message = f"Hindsight: memoria salvata — {preview}"
        # Context non prodotto dal gate: si dice all'utente quale e' finito
        # nella memoria e da dove viene (risposta sua, proposta di Claude nel
        # transcript, oppure la riga repo/branch di ultima risorsa).
        source = outcome.get("context_source")
        if source != "gate":
            label = {
                "explicit": "indicato da te",
                "proposal": "proposto da Claude",
                "fallback": "ricavato da repo/branch",
            }.get(source, source)
            message += f" [context «{outcome.get('context') or ''}», {label}]"
        output = {
            "systemMessage": message,
            "hookSpecificOutput": {
                "hookEventName": "UserPromptSubmit",
                "additionalContext": (
                    "## Hindsight retain\n\nLa memoria in attesa di conferma è stata "
                    "salvata nel bank. Non serve alcun retain manuale."
                ),
            },
        }
        return output, "", True, True
    if action == "error":
        # Il pending e' stato rimesso in attesa (restored): l'utente puo'
        # riprovare con un altro "si'" senza rifare il retain a mano.
        message = (
            "Hindsight: salvataggio della memoria in attesa NON riuscito — "
            + str(outcome.get("error") or "")
        )
        if outcome.get("restored"):
            message += " Rispondi «sì» al prossimo prompt per riprovare."
        return {"systemMessage": message}, "", False, True
    # "discarded": col "no" resta silenzioso; su prompt NUOVO l'utente deve
    # sapere che la domanda del gate e' decaduta (altrimenti crede di aver
    # salvato). La notifica viaggia con QUALUNQUE uscita dell'hook (la fonde
    # emit()/finish() del recall): lo stdout resta un solo oggetto JSON.
    if outcome.get("reason") == "new_prompt":
        preview = outcome.get("preview") or ""
        notice = (
            f"Hindsight: memoria in attesa scartata — {preview}"
            if preview
            else "Hindsight: memoria in attesa scartata"
        )
        return {}, notice, False, False
    return {}, "", False, False


def retain_at_prompt(
    prompt: str, session_id: str, cwd: str, transcript_path: str
) -> PromptRetain:
    """Lato retain di un UserPromptSubmit: consenso del pending (sincrono, con
    la stessa chiamata e lo stesso debug_log di sempre) e avvio del gate
    differito in un thread daemon (evaluate_queued), il cui esito il chiamante
    ritira con gate_output(deadline). Non solleva MAI: qualunque eccezione va
    nel debug log e ritorna un PromptRetain a campi vuoti (l'hook recall
    prosegue come se non ci fosse nulla da fare lato retain).
    Eccezione voluta: se il "si'" e' fallito e il pending e' stato RIMESSO in
    attesa (restored), il gate NON parte — un nuovo pending della stessa
    sessione lo sovrascriverebbe (un file per session+cwd): l'entry in coda
    resta e si valuta al prompt dopo."""
    result = PromptRetain(session_id)
    try:
        # Consenso PRIMA di tutto il resto, incluso il gate recall_enabled
        # dell'hook: la domanda del gate retain e' sempre la piu' recente
        # (posta alla fine del turno precedente), quindi un si'/no secco (o
        # un `context: …`) appartiene a lei, e va onorata anche nei progetti
        # col recall spento. Il transcript serve a ripescare il context
        # proposto da Claude nella domanda.
        outcome = handle_retain_consent(
            prompt, session_id, cwd, transcript_path=transcript_path
        )
        result.outcome = outcome
        if outcome:
            debug_log(
                CFG,
                "retain_pending",
                action=outcome.get("action"),
                reason=outcome.get("reason"),
                status=outcome.get("status"),
                error=outcome.get("error"),
                context=outcome.get("context"),
                context_source=outcome.get("context_source"),
                preview=(outcome.get("preview") or "")[:300],
            )
            (
                result.consent_output,
                result.notice,
                result.saved,
                result.stop_here,
            ) = _consent_output(outcome)
        if outcome and outcome.get("restored"):
            return result

        def _run_gate() -> None:
            try:
                result._box["out"] = evaluate_queued(session_id) or {}
            except Exception:  # evaluate_queued non solleva; cintura e bretelle
                result._box["out"] = {}

        thread = threading.Thread(
            target=_run_gate, name="hs-retain-gate", daemon=True
        )
        thread.start()
        result._thread = thread
        return result
    except Exception as exc:
        try:
            debug_log(
                CFG,
                "retain_error",
                where="retain_at_prompt",
                error=f"{type(exc).__name__}: {exc}"[:300],
                session=(session_id or "")[:8],
            )
        except Exception:
            pass
        return PromptRetain(session_id)


def main(argv: list[str] | None = None) -> int:
    """Modalita' script. `--drain`: svuota la coda valutando ogni entry in
    "drain" (sentinel di fine sessione), best-effort per entry. Senza flag:
    valuta $HOOK_INPUT in "deferred" e stampa 'HSGATE {json}' su stdout quando
    c'e' output (tools/hindsight-check.sh e run manuali); i log '[retain]'
    vanno su stderr in entrambe le modalita'."""
    args = list(sys.argv[1:] if argv is None else argv)
    if "--drain" in args:
        for entry in drain_queue():
            try:
                evaluate(entry, "drain")
            except Exception as exc:
                print(f"[retain] drain error: {type(exc).__name__}: {exc}", file=sys.stderr)
                debug_log(
                    CFG,
                    "retain_error",
                    error=f"{type(exc).__name__}: {exc}"[:300],
                    session=str(entry.get("session_id") or "")[:8],
                    where="drain",
                )
        return 0
    rc, out = evaluate(parse_hook(), "deferred")
    if out:
        print("HSGATE " + json.dumps(out, ensure_ascii=False))
    return rc


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
