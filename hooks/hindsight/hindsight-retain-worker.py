"""Worker per hindsight-retain.sh — eseguito in background (fire-and-forget).

Legge il payload del hook da $HOOK_INPUT (env var JSON), parsea il transcript JSONL
e costruisce un riassunto strutturato. Poi POST a /memories con async=true.

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
import json
import os
import re
import subprocess
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone

# Config centralizzata (vedi hindsight.config.json). sys.path insert necessario
# sia quando il worker gira come script sia quando viene importato dai test.
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "lib"))
from hindsight_config import cache_dir, load_config, retain_bank_url
from hindsight_debug import debug_log

CFG = load_config()

HOOK_INPUT = os.environ.get("HOOK_INPUT", "")

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
    Riduce le ri-estrazioni LLM ridondanti su sessioni lunghe. force=True (es. hook
    SessionEnd) ritiene sempre, per catturare la coda della sessione. Senza session_id
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
    r"|## Hindsight (?:persistent memory|knowledge pages).*?Verify mutable facts against the repo\.",
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
# conversazione, ognuna con un document_id timestamped univoco. La finestra
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


def slice_last_turns_by_user_boundary(messages: list[dict], turns: int) -> list[dict]:
    """Ultimi N turni, dove un turno inizia a un messaggio user. Cammina
    all'indietro contando i confini-user. Port di sliceLastTurnsByUserBoundary()."""
    if not messages or turns <= 0:
        return []
    seen = 0
    start = -1
    for i in range(len(messages) - 1, -1, -1):
        if messages[i]["role"] == "user":
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
            txt = strip_memory_block(extract_text(content))
            if txt and not txt.startswith("<"):
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
    """Content di una fetta: la conversazione multi-turno della finestra + file/comandi."""
    if not summary["turns"] and not summary["files_modified"]:
        return None
    parts = [
        "Claude Code session activity (chunk).",
        f"Timestamp: {datetime.now(timezone.utc).isoformat()}",
        f"CWD: {hook.get('cwd', '')}",
        f"Session: {hook.get('session_id', '')}",
        "",
        "## Conversation (recent turns)",
    ]
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


# ---------------------------------------------------------------------------
# context del retain: dominio/i del task (max 3) -> "claude-code/<d1>[/<d2>][/<d3>]".
# In Hindsight il context e' DESCRITTIVO (frame per l'LLM estrattore), non
# strutturale (le relazioni sono entita'+tag). Qui miriamo solo a un frame piu'
# utile del vecchio repo/branch. Due strategie: "llm" (gpt-4.1-nano sul riassunto
# di sessione) con fallback automatico su "heuristic" (domini dai path dei file).
# ---------------------------------------------------------------------------

OPENAI_URL = "https://api.openai.com/v1/chat/completions"

# Prompt iterato empiricamente (vedi test/infer_domains_test.py). Le 4 leve che lo
# fanno funzionare su gpt-4.1-nano: tetto a 3, priorita' ai nomi propri presenti nel
# testo, distinzione soggetto/strumento (no git/mise/...), blocklist delle attivita'.
_DOMAIN_SYSTEM_PROMPT = """You label the technical domain(s) of a software-engineering work session.

You receive a compact summary of one session: what the user asked, what the assistant did, which files were touched, which commands were run. Output the technical SUBSYSTEMS, COMPONENTS, or TOOLS the session is about.

Rules:
1. Output AT MOST 3 domains. Prefer 1. Add a 2nd/3rd ONLY for genuinely distinct areas.
2. Each domain is a short kebab-case slug, 1-3 words.
3. PRIORITY — proper nouns beat generic concepts: if the session works ON a named tool/product/component (e.g. Obsidian, Excalidraw, Hindsight, PostgreSQL), use ITS name lowercased as the slug ("obsidian", "excalidraw", "hindsight"). Only invent a generic slug when no such name exists.
4. SUBJECT vs INSTRUMENT — ask "did we BUILD/CHANGE this, or only USE it to run/ship the work?". A tool used merely as an instrument is NOT a domain. Never output these unless the session is specifically about configuring the tool itself: "git", "mise", "curl", "pip", "bash", "npm", "pnpm", "cargo", "ruby", "python".
5. Name the SUBSYSTEM/COMPONENT, NEVER the ACTIVITY. Forbidden slugs: "debugging", "refactoring", "coding", "testing", "code-review", "analysis", "reading", "documentation", "note-taking", "diagramming", "configuration". If tempted by one of these, name the component it acted on instead.
6. Never output near-synonyms together (e.g. "scheduler" AND "scheduling").
7. Derive domains from concrete nouns: files, tools, components. Ignore filler like "fix this" or "rimetti come era".
8. Input may be Italian or English; slugs are ALWAYS English.
9. No clear technical domain → output exactly ["general"].

Examples:
- Reading hindsight-api source to understand the retain pipeline -> ["hindsight"]   (NOT "code-review")
- Building a scheduler that checks PyPI for updates, run via mise, committed via git -> ["scheduler"]   (NOT "mise", "git")
- Drawing an architecture diagram in Excalidraw and saving it as an Obsidian note -> ["excalidraw", "obsidian"]   (NOT "diagramming", "note-taking")

Return JSON: {"domains": ["...", ...]}"""

_DOMAIN_RESPONSE_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "domains": {
            "type": "array",
            "minItems": 1,
            "maxItems": 3,
            "items": {"type": "string"},
        }
    },
    "required": ["domains"],
}

# Alias di normalizzazione per l'euristica path-based (segmento -> dominio).
_DOMAIN_ALIASES = {"test": "tests"}


def _clean_domains(raw: list) -> list[str]:
    """Normalizza una lista di slug: lower, kebab, dedup (ordine preservato), max 3."""
    seen: set[str] = set()
    out: list[str] = []
    for d in raw:
        s = str(d).strip().lower().replace(" ", "-")
        if s and s not in seen:
            seen.add(s)
            out.append(s)
    return out[:3]


def _domain_input(summary: dict, hook: dict) -> str:
    """Riassunto compatto di sessione per il modello. Gestisce sia il summary
    'chunked' (turns) sia quello 'legacy' (last_user_prompt/last_assistant_text)."""
    turns = summary.get("turns") or []
    prompt = summary.get("last_user_prompt") or next(
        (t for r, t in turns if r == "user"), ""
    )
    assistant = summary.get("last_assistant_text") or next(
        (t for r, t in reversed(turns) if r == "assistant"), ""
    )
    files = summary.get("files_modified") or []
    cmds = summary.get("bash_cmds") or []
    parts: list[str] = []
    if prompt:
        parts += ["## User asked", prompt, ""]
    if assistant:
        parts += ["## Assistant did", assistant, ""]
    if files:
        parts += ["## Files touched"] + [f"- {f}" for f in files] + [""]
    if cmds:
        parts += ["## Commands"] + [f"- {c}" for c in cmds] + [""]
    return "\n".join(parts).strip()


def infer_domains_llm(text: str, model: str, timeout: int = 12) -> list[str]:
    """Estrae max 3 domini via LLM. Ritorna [] su qualunque errore (no key, rete,
    timeout, JSON invalido): il chiamante ricade su euristica/context piano."""
    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key or not text:
        return []
    body = json.dumps(
        {
            "model": model,
            "messages": [
                {"role": "system", "content": _DOMAIN_SYSTEM_PROMPT},
                {"role": "user", "content": text},
            ],
            "temperature": 0.0,
            "response_format": {
                "type": "json_schema",
                "json_schema": {
                    "name": "domains",
                    "schema": _DOMAIN_RESPONSE_SCHEMA,
                    "strict": True,
                },
            },
        }
    ).encode("utf-8")
    req = urllib.request.Request(
        OPENAI_URL,
        data=body,
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as res:
            data = json.loads(res.read().decode("utf-8"))
        content = data["choices"][0]["message"]["content"]
        return _clean_domains(json.loads(content).get("domains", []))
    except Exception as e:  # noqa: BLE001 — non deve mai rompere il retain
        debug_log(CFG, "context_infer_error", error=f"{type(e).__name__}: {e}")
        return []


def _significant_segment(path: str, cwd: str) -> str | None:
    """Dal path di un file modificato ricava il nome del sottosistema. Salta i
    prefissi noti (.claude/skills|hooks/<X>), normalizza suffisso -skill e alias."""
    p = path.replace("\\", "/")
    c = (cwd or "").replace("\\", "/").rstrip("/")
    if c and p.startswith(c + "/"):
        p = p[len(c) + 1 :]
    segs = [s for s in p.split("/") if s and s != "."]
    if not segs:
        return None
    if len(segs) >= 3 and segs[0] == ".claude" and segs[1] in ("skills", "hooks"):
        name = segs[2]
    elif len(segs) >= 2:
        name = segs[0]  # top-dir per file annidati
    else:
        name = segs[0]  # file in root (es. .mise.toml)
    n = name.strip().lower().lstrip(".")
    if n.endswith("-skill"):
        n = n[:-6]
    n = _DOMAIN_ALIASES.get(n, n)
    return n or None


def domains_from_paths(files: list[str], cwd: str) -> list[str]:
    """Euristica deterministica (zero rete): domini dai path dei file modificati."""
    raw = [seg for f in files if (seg := _significant_segment(f, cwd))]
    return _clean_domains(raw)


def resolve_context(summary: dict, hook: dict) -> str:
    """Costruisce il context del retain secondo la config. Catena:
    llm -> (fallback) heuristic -> "claude-code" piano. Mai solleva."""
    if not CFG.get("context_extraction", False):
        return "claude-code"
    strategy = CFG.get("context_extraction_strategy", "llm")
    files = summary.get("files_modified") or []
    cwd = hook.get("cwd") or ""
    domains: list[str] = []
    if strategy == "llm":
        domains = infer_domains_llm(
            _domain_input(summary, hook),
            CFG.get("context_extraction_model", "gpt-4.1-nano"),
        )
        if not domains:  # rete di sicurezza quando l'LLM non risponde
            domains = domains_from_paths(files, cwd)
    elif strategy == "heuristic":
        domains = domains_from_paths(files, cwd)
    if not domains:
        return "claude-code"
    return "claude-code/" + "/".join(domains)


def main() -> int:
    # Interruttore master: se il retain automatico e' disattivato in config, esci
    # subito — niente parse del transcript, niente POST, niente estrazione LLM.
    if not CFG.get("retain_enabled", True):
        debug_log(CFG, "retain_skip", reason="disabled")
        return 0

    hook = parse_hook()
    # Stop hook non passa 'prompt'; il filtro avviene in build_content (skip se
    # last_user_prompt+files_modified entrambi vuoti = turno senza contenuto utile).
    transcript = load_transcript(hook.get("transcript_path", ""))
    if not transcript:
        debug_log(CFG, "retain_skip", reason="no_transcript")
        return 0

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
        return 0

    # Throttling: salta i Stop non multipli di N per ridurre le ri-estrazioni LLM
    # ridondanti su sessioni lunghe. force su SessionEnd (cattura la coda) o via
    # HS_RETAIN_FORCE. Il contatore avanza solo sui turni con contenuto utile.
    session_id = hook.get("session_id") or ""
    force = hook.get("hook_event_name") == "SessionEnd" or bool(
        os.environ.get("HS_RETAIN_FORCE")
    )
    if not should_retain_now(session_id, force=force):
        print("[retain] skip: throttling (turno non multiplo di N, niente SessionEnd)")
        debug_log(CFG, "retain_skip", reason="throttling", session=session_id[:8])
        return 0

    git = git_info(hook.get("cwd") or "")
    tags = build_tags(hook, git)

    # context: dominio/i del task (max 3), schema "claude-code/<d1>[/<d2>][/<d3>]".
    # repo/branch NON vanno qui (sono gia' nei tag e nei metadata): nel context
    # darebbero cardinalita' ~1 e zero segnale. Vedi resolve_context() e la config
    # context_extraction*. Mai solleva: peggio caso ritorna "claude-code".
    context = resolve_context(summary, hook)

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

    # document_id: in chunked ogni fetta e' un documento IMMUTABILE con id
    # timestamped (niente upsert distruttivo, niente perdita tra retain). In legacy
    # resta l'id stabile per-sessione con guardia compaction (compute_document_id,
    # che fa upsert — verificato lossy sul testo non-ultimo).
    if retain_mode == "chunked":
        doc_id = f"{session_id}-{int(time.time() * 1000)}" if session_id else None
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
            print(f"[retain] OK {res.status} {body[:200]}")
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
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
