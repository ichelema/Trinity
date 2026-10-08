"""Worker del retain automatico: valuta un payload di Stop e lo persiste.

Da ICH-86 lo Stop hook (hindsight-retain.sh) NON valuta piu' nulla: accoda il
payload del hook in hs-retain-queue/ e risponde subito. La valutazione avviene
DOPO, in due punti:
  - UserPromptSubmit (hindsight-recall.sh) -> retain_at_prompt(...): TUTTA la
    logica retain del prompt sta qui (l'hook recall ha solo poche righe di
    colla), in quest'ordine: (1) pickup dell'outbox lasciato dal gate del
    prompt PRECEDENTE (se non aveva finito in tempo); (2) consenso del pending
    (handle_retain_consent) in modo sincrono — saltato se l'outbox appena
    raccolto porta una domanda mai mostrata; (3) sweep delle entry di coda
    piu' vecchie di 24h; (4) lancio del gate differito in un PROCESSO DETACHED
    (`--queued <session_id>`, evaluate_queued) parallelo al recall — prende
    l'entry piu' recente della sessione ("deferred": il consenso per
    uncertain/context mancante viaggia in additionalContext, canale nascosto,
    e la domanda viene posta in coda alla risposta successiva) e scrive
    l'esito nell'OUTBOX <queue_dir>/<session_id>.out.json; l'hook aspetta
    l'outbox solo per un breve budget al momento dell'emit
    (PromptRetain.gate_output) e, se il processo non ha finito, esce: nulla
    viene ucciso, l'esito si raccoglie al prompt successivo (punto 1);
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

import hashlib
import json
import os
import re
import shlex
import subprocess
import sys
import time
import urllib.request
from datetime import datetime, timezone

# Config centralizzata (vedi hindsight.config.json). sys.path insert necessario
# sia quando il worker gira come script sia quando viene importato dai test.
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "lib"))
from hindsight_config import cache_dir, load_config, recall_bank_urls, resolve_bank, retain_bank_url, window_max_chars
from hindsight_debug import debug_log
from hindsight_file_lock import file_lock
from hindsight_recall_filter import consume_pending
from hindsight_recall_lib import last_assistant_text, strip_memory_block
from hindsight_retain_gate import (
    RETAIN_PENDING_TTL,
    evaluate_retain,
    fallback_context,
    guided_content,
    handle_invalidate_consent,
    handle_retain_consent,
    invalidate_pending_dir,
    save_invalidate_pending,
    save_retain_pending,
)
from hindsight_secrets import OUTCOME_SECRET_PATTERNS

CFG = load_config()

# Payload del hook per la modalita' script senza flag (parse_hook). I test e
# l'hook recall passano invece l'entry direttamente a evaluate()/evaluate_queued().
HOOK_INPUT = os.environ.get("HOOK_INPUT", "")

# Entry di coda illeggibili piu' giovani di questa soglia vengono lasciate stare:
# potrebbero essere in scrittura da uno Stop concorrente (printf non atomico).
QUEUE_UNPARSABLE_GRACE_S = 60.0

# Entry di coda (di QUALUNQUE sessione) piu' vecchie di cosi' non verranno mai
# piu' valutate dal loro prompt successivo (la sessione e' finita) e la
# sentinella avrebbe dovuto drenarle: si tolgono con un marker durevole
# (note_post_failure) invece di lasciarle accumulare in silenzio.
QUEUE_MAX_AGE_S = 24 * 3600.0

# Passo di polling dell'outbox del gate differito in gate_output().
OUTBOX_POLL_S = 0.05

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

# Esiti dei comandi (ICH-150): la prova che il gate cerca quando chiede
# conoscenza "verificata". Solo comandi falliti e righe di esito dei test.
OUTCOME_MAX_CHARS = 300
OUTCOMES_MAX_CHARS = 2000
OUTCOME_CMD_MAX_CHARS = 80
# Solo righe che SEMBRANO esiti (PASS/FAIL maiuscoli, "3 passed"/"1 failing",
# "OK" o "FAILED" a inizio riga, "ok pkg 0.3s" di Go): la prosa ("fail-closed",
# "password") resta fuori. Niente "Found 3 errors" (ICH-157): e' il riepilogo di
# tsc, non un esito di test; un tsc fallito entra comunque da exit code e ultima riga.
OUTCOME_TEST_LINE = re.compile(
    r"\b(?:PASS(?:ED)?|FAIL(?:ED|URE)?)\b|\b\d+\s+(?:passed|failed|passing|failing)\b"
    r"|(?<!Found )\b\d+\s+errors?\b|^(?:OK|FAILED)\b|^ok\s+\S+\s+(?:\d+(?:\.\d+)?s|\(cached\))"
)
# ICH-157: comandi che stampano testo gia' esistente (codice, log, risultati di
# ricerca): un PASS/FAIL nel loro output e' testo trovato, non un esito.
TEXT_ONLY_CMDS = frozenset({
    "cd", "cat", "head", "tail", "less", "grep", "egrep", "fgrep", "rg", "sed", "awk",
    "sort", "uniq", "wc", "cut", "git grep", "git diff", "git log", "git show",
    "echo", "gh pr view", "gh issue view",
})
# ICH-169: ricerche che escono con 1 quando non trovano nulla.
SEARCH_CMDS = frozenset({"grep", "egrep", "fgrep", "rg", "git grep"})
# ICH-169: opzioni di xargs con il valore nel token seguente (`xargs -n 1 cat`).
XARGS_ARG_OPTS = ("-a", "-d", "-E", "-I", "-L", "-n", "-P", "-s")
CMD_SEPARATORS = frozenset({"|", "||", "&&", ";", "&", "(", ")"})
# tool_result con is_error che non sono comandi falliti: rifiuto e interruzione dell'utente.
USER_STOP_PREFIXES = ("The user doesn't want to proceed", "[Request interrupted by user")
OMISSION_MARKER = "\n[…]\n"
SECRET_CMD_PLACEHOLDER = "[comando omesso: contiene un segreto]"


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

    # Windows: git.exe e' un programma console; se il worker gira senza console
    # visibile (figlio detached dell'hook, sentinella, drain) ogni git aprirebbe
    # una finestra di terminale che lampeggia sullo schermo. CREATE_NO_WINDOW
    # la nasconde qualunque sia lo stato del padre.
    _git_kwargs: dict = (
        {"creationflags": subprocess.CREATE_NO_WINDOW} if os.name == "nt" else {}
    )

    def _run(args: list[str]) -> str:
        try:
            out = subprocess.check_output(
                ["git", *args],
                cwd=cwd,
                stderr=subprocess.DEVNULL,
                timeout=5,
                text=True,
                **_git_kwargs,
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


def _retain_state_path() -> str:
    """File di stato del worker (stop_count, gate_error_notified per sessione).
    In cache_dir() (per-utente, 0700): su Linux /tmp e' scrivibile da tutti.
    Override per i test via HS_RETAIN_STATE_DIR."""
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
# Nella stessa dir vive anche l'OUTBOX del gate differito,
# <session_id>.out.json (vedi outbox_path): non e' un'entry di coda e i
# consumatori la ignorano.
# ---------------------------------------------------------------------------


def retain_queue_dir() -> str:
    """Directory della coda. In cache_dir() (per-utente, 0700) perche' le entry
    contengono cwd e path del transcript. HS_RETAIN_QUEUE_DIR per i test."""
    return os.environ.get("HS_RETAIN_QUEUE_DIR") or cache_dir() + "/hs-retain-queue"


OUTBOX_SUFFIX = ".out.json"


def _queue_files() -> list[str]:
    """Path delle entry *.json in ordine di nome (= ordine di scrittura); gli
    outbox *.out.json della stessa dir sono esclusi (non sono entry)."""
    d = retain_queue_dir()
    try:
        names = sorted(
            n for n in os.listdir(d)
            if n.endswith(".json") and not n.endswith(OUTBOX_SUFFIX)
        )
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
    Le altre sessioni restano in coda. None senza session_id o senza entry.
    Nell'entry ritornata `queued_skipped` = numero di entry PIU' VECCHIE della
    stessa sessione scartate qui (0 se nessuna): ogni entry e' uno Stop
    realmente avvenuto e il throttling deve contarli tutti (should_retain_now
    con advance), altrimenti N Stop consecutivi senza prompt in mezzo
    varrebbero come uno solo e la cadenza `retain_every_n_turns` slitterebbe."""
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
    if newest is not None:
        newest["queued_skipped"] = len(matched) - 1
    return newest


def has_queued(session_id: str) -> bool:
    """True se in coda c'e' almeno un'entry della sessione (nessun consumo).
    Scan economico: un listdir + parse delle sole entry presenti; serve a
    retain_at_prompt per non lanciare un processo quando non c'e' nulla."""
    if not session_id:
        return False
    for path in _queue_files():
        entry = _read_queue_entry(path)
        if entry is not None and entry.get("session_id") == session_id:
            return True
    return False


def outbox_path(session_id: str) -> str:
    """Outbox del gate differito della sessione: <queue_dir>/<session_id>.out.json.
    Il processo `--queued` ci scrive {"output": {...}, "asks_consent": bool} in
    modo atomico; l'hook (gate_output) o il prompt successivo (retain_at_prompt)
    lo leggono e lo cancellano. I session id sono UUID, ma i separatori di path
    vengono tolti comunque: il file deve restare DENTRO la dir della coda."""
    safe = re.sub(r"[\\/]+", "_", str(session_id or "")) or "_"
    return os.path.join(retain_queue_dir(), safe + OUTBOX_SUFFIX)


def _write_outbox(session_id: str, output: dict | None, asks_consent: bool) -> None:
    """Scrive l'outbox in modo atomico (tmp + os.replace): chi fa polling vede
    o niente o il file completo, mai una scrittura a meta'. Best-effort."""
    path = outbox_path(session_id)
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        tmp = f"{path}.{os.getpid()}.tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(
                {"output": dict(output or {}), "asks_consent": bool(asks_consent)}, f
            )
        os.replace(tmp, path)
    except Exception as exc:
        print(f"[retain] outbox non scritto: {exc}", file=sys.stderr)


def _read_outbox(session_id: str) -> dict | None:
    """Legge E cancella l'outbox della sessione; None se assente o illeggibile
    (in quel caso lo cancella comunque: non verra' mai piu' valido)."""
    path = outbox_path(session_id)
    if not os.path.exists(path):
        return None
    box = None
    try:
        with open(path, "r", encoding="utf-8") as f:
            box = json.load(f)
    except Exception:
        box = None
    _remove_quiet(path)
    return box if isinstance(box, dict) else None


def sweep_stale_queue(max_age_s: float = QUEUE_MAX_AGE_S) -> int:
    """Toglie le entry di coda (di qualunque sessione) piu' vecchie di
    max_age_s: nessun prompt della loro sessione le valutera' piu' e la
    sentinella avrebbe dovuto drenarle a chiusura — se sono ancora qui
    qualcosa non ha funzionato, quindi marker durevole per il failcheck
    (note_post_failure) invece di un accumulo silenzioso. Gli outbox
    *.out.json altrettanto vecchi si cancellano in silenzio: il pending a
    cui si riferivano e' scaduto da un pezzo. Un solo listdir; ritorna il
    numero di entry rimosse."""
    d = retain_queue_dir()
    try:
        names = os.listdir(d)
    except OSError:
        return 0
    now = time.time()
    removed = 0
    for name in names:
        if not name.endswith(".json"):
            continue
        path = os.path.join(d, name)
        try:
            age = now - os.path.getmtime(path)
        except OSError:
            continue
        if age <= max_age_s:
            continue
        if name.endswith(OUTBOX_SUFFIX):
            _remove_quiet(path)
            continue
        entry = _read_queue_entry(path)  # illeggibile e vecchia: gia' rimossa qui
        sid = str((entry or {}).get("session_id") or "")[:8] or "?"
        _remove_quiet(path)
        removed += 1
        note_post_failure(
            "entry di coda del retain piu' vecchia di 24h mai valutata "
            f"(sessione {sid}): la sentinella non ha drenato?"
        )
        debug_log(
            CFG, "retain_skip", reason="queue_stale", session=sid, age_s=int(age)
        )
    return removed


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
        # precedente): sotto file_lock la RMW e' serializzata, ma questa flakiness
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
    session_id: str, force: bool = False, every_n: int | None = None, advance: int = 1
) -> bool:
    """Throttling: ritiene un Stop ogni N (default da HS_RETAIN_EVERY_N, fallback 3).
    Riduce le ri-estrazioni LLM ridondanti su sessioni lunghe. Il contatore
    stop_count avanza di `advance` per chiamata: una volta per Stop REALMENTE
    avvenuto — l'entry consumata piu' quelle piu' vecchie della stessa sessione
    scartate nel dequeue (queued_skipped), stessa cadenza di quando il worker
    girava nello Stop. Ritorna True se l'avanzamento ha ATTRAVERSATO un
    multiplo di N ((nuovo // N) > (vecchio // N); con advance=1 e' l'usuale
    cnt % N == 0), cosi' piu' Stop accumulati senza prompt in mezzo non fanno
    saltare il turno da salvare. force=True (drain a fine sessione,
    HS_RETAIN_FORCE) ritiene sempre e NON avanza il contatore (esce prima), per
    catturare la coda della sessione. Senza session_id o con N<=1 ritiene
    sempre (nessun throttling)."""
    if every_n is None:
        every_n = max(1, int(CFG.get("retain_every_n_turns", 3)))
    if force or not session_id or every_n <= 1:
        return True
    advance = max(1, int(advance))
    path = _retain_state_path()
    # Best-effort (lost update su stop_count): su timeout il corpo gira comunque
    # senza lock — il throttling non e' critico e bloccare un worker async
    # sarebbe peggio del lost update che il lock evita.
    with file_lock(path, timeout=5.0):
        try:
            with open(path, "r", encoding="utf-8") as f:
                state = json.load(f)
        except Exception:
            state = {}
        if not isinstance(state, dict):
            state = {}  # file avvelenato (JSON valido ma non-dict): auto-ripara
        entry = state.get(session_id) or {}
        old = int(entry.get("stop_count", 0))
        cnt = old + advance
        entry["stop_count"] = cnt
        state[session_id] = entry
        _write_retain_state(path, state)
    return (cnt // every_n) > (old // every_n)


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
    with file_lock(path, timeout=5.0):
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


# ---------------------------------------------------------------------------
# Retain "chunked" (sliding window) — ispirato al plugin ufficiale Hindsight.
# Salva FETTE immutabili della conversazione, ognuna con un document_id
# derivato dal contenuto (univoco tra fette diverse, stabile sui replay della
# stessa finestra). La finestra copre gli ultimi (retain_every_n_turns +
# retain_overlap_turns) turni: l'overlap ricuce i confini tra fette consecutive
# cosi' nessun ragionamento a cavallo va perso. La ridondanza tra fette viene
# assorbita dalla consolidation del server (merge per proof_count). Un "turno"
# inizia a ogni messaggio user.
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


def head_tail(text: str, max_chars: int) -> str:
    """Inizio + marcatore + fine entro max_chars (40/60: la conclusione sta in fondo)."""
    if len(text) <= max_chars:
        return text
    if max_chars <= len(OMISSION_MARKER):
        return text[len(text) - max_chars:] if max_chars > 0 else ""
    budget = max_chars - len(OMISSION_MARKER)
    head = budget * 2 // 5
    return text[:head] + OMISSION_MARKER + text[len(text) - (budget - head):]


def _tool_result_text(content) -> str:
    if isinstance(content, list):
        content = "\n".join(
            b.get("text") or "" for b in content if isinstance(b, dict) and b.get("type") == "text"
        )
    return content if isinstance(content, str) else ""


def _first_operand(seg: list[str], arg_opts: tuple[str, ...]) -> int:
    """Indice del primo argomento dopo le opzioni: `git -C path --no-pager diff` -> diff."""
    i = 1
    while i < len(seg) and seg[i].startswith("-"):
        i += 2 if seg[i] in arg_opts else 1
    return i


def _command_name(seg: list[str]) -> str:
    """Nome da confrontare con TEXT_ONLY_CMDS: `git diff`, `gh pr view`, e per
    xargs il comando che lancia (`xargs -0 grep x` -> grep)."""
    name = os.path.basename(seg[0])
    if name == "git":
        i = _first_operand(seg, ("-C", "-c"))
        return "git " + (seg[i] if i < len(seg) else "")
    if name == "gh":
        return " ".join(["gh"] + seg[1:3])
    if name == "xargs":
        i = _first_operand(seg, XARGS_ARG_OPTS)
        return _command_name(seg[i:]) if i < len(seg) else name
    return name


def _command_names(cmd: str) -> list[str]:
    """Nomi dei comandi della riga (`cd x && grep -rn PASS .` -> cd, grep).
    Nel dubbio (quote non chiuse) lista vuota; una variabile d'ambiente in testa
    diventa il nome: vale il riconoscimento normale."""
    lex = shlex.shlex(cmd.replace("\n", ";"), posix=True, punctuation_chars=True)
    lex.whitespace_split = True
    try:
        tokens = list(lex)
    except ValueError:
        return []
    segments: list[list[str]] = [[]]
    for tok in tokens:
        if tok in CMD_SEPARATORS:
            segments.append([])
        else:
            segments[-1].append(tok)
    return [_command_name(seg) for seg in segments if seg]


def command_outcome(cmd: str, result: str, is_error: bool) -> str | None:
    """Esito compatto di un comando Bash, o None se non porta prove: un comando
    fallito (exit code + ultima riga) o le righe di esito dei test. Le righe con
    un segreto vengono scartate prima di tutto."""
    stripped = (ln.strip() for ln in result.splitlines())
    lines = [ln for ln in stripped if ln and not any(p.search(ln) for p in OUTCOME_SECRET_PATTERNS)]
    names = _command_names(cmd)
    text_only = bool(names) and all(n in TEXT_ONLY_CMDS for n in names)
    evidence = [] if text_only else [ln for ln in lines if OUTCOME_TEST_LINE.search(ln)]
    # La scelta sopra guarda il comando intero; in memoria va solo la prima riga.
    cmd = cmd.split("\n", 1)[0][:200]
    # Un tool_use rifiutato o interrotto dall'utente ha is_error ma non e' un comando fallito.
    # ICH-169: neanche una ricerca senza risultati (grep esce con 1 e non stampa nulla).
    # Conta l'ultimo comando: e' il suo l'exit code della pipe (`ls | grep x`).
    no_match = bool(names) and names[-1] in SEARCH_CMDS and lines == ["Exit code 1"]
    if is_error and lines and not lines[0].startswith(USER_STOP_PREFIXES) and not no_match:
        evidence = [lines[0]] + evidence + ([lines[-1]] if len(lines) > 1 else [])
    if not evidence:
        return None
    # Il comando finisce in memoria come l'output: stesso filtro.
    if any(p.search(cmd) for p in OUTCOME_SECRET_PATTERNS):
        cmd = SECRET_CMD_PLACEHOLDER
    else:
        cmd = _clip(cmd, OUTCOME_CMD_MAX_CHARS)
    head = f"- {cmd} → "
    parts = list(dict.fromkeys(evidence))
    # ICH-156: prima riga (exit code) e ultima restano; le intermedie cadono per prime.
    # L'ultima resta in coda anche se ripete una riga precedente.
    parts.remove(evidence[-1])
    parts.append(evidence[-1])
    while len(parts) > 2 and len(head) + len(" | ".join(parts)) > OUTCOME_MAX_CHARS:
        del parts[1]
    room = OUTCOME_MAX_CHARS - len(head)
    if len(parts) == 2 and len(parts[0]) + 3 + len(parts[1]) > room:
        # All'ultima almeno un terzo dello spazio; la prima prende il resto.
        parts[1] = _clip(parts[1], max(room // 3, room - len(parts[0]) - 3))
        parts[0] = _clip(parts[0], room - len(parts[1]) - 3)
    return (head + " | ".join(parts))[:OUTCOME_MAX_CHARS]


def _clip(text: str, max_chars: int) -> str:
    return text if len(text) <= max_chars else text[: max_chars - 1] + "…"


def summarize_window(entries: list[dict], window_turns: int) -> dict:
    """Riassume l'intera finestra di window_turns turni: raccoglie la sequenza
    (role, text) della conversazione + file/comandi della finestra + gli esiti
    dei comandi Bash (ICH-150, indipendenti da retain_tool_calls)."""
    window = slice_last_turns_by_user_boundary(
        _iter_role_messages(entries), window_turns
    )
    turns: list[tuple[str, str]] = []
    files_modified: list[str] = []
    bash_cmds: list[str] = []
    pending_cmds: dict[str, str] = {}
    outcomes: list[str] = []

    for m in window:
        role = m["role"]
        content = m["content"]
        if role == "user":
            if isinstance(content, list):
                for b in content:
                    if isinstance(b, dict) and b.get("type") == "tool_result":
                        cmd = pending_cmds.pop(b.get("tool_use_id") or "", None)
                        if cmd:
                            out = command_outcome(cmd, _tool_result_text(b.get("content")), bool(b.get("is_error")))
                            if out:
                                outcomes.append(out)
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
                if b.get("type") == "tool_use" and b.get("name") == "Bash":
                    cmd = ((b.get("input") or {}).get("command") or "").strip()
                    if cmd and b.get("id"):
                        pending_cmds[b["id"]] = cmd
            if texts:
                turns.append(("assistant", "\n".join(texts)))

    # Tetto della sezione: gli esiti piu' recenti vincono.
    kept: list[str] = []
    for out in reversed(outcomes):
        if sum(len(o) + 1 for o in kept) + len(out) > OUTCOMES_MAX_CHARS:
            break
        kept.insert(0, out)
    return {
        "turns": turns,
        "files_modified": files_modified[-CFG["retain_max_files"] :],
        "bash_cmds": bash_cmds[-CFG["retain_max_cmds"] :],
        "outcomes": kept,
    }


def build_content_chunk(hook: dict, summary: dict) -> str | None:
    """Content di una fetta: la conversazione multi-turno della finestra + file/comandi.
    Niente header Timestamp/CWD/Session (ICH-67): quei valori sono gia' nei
    metadata dell'item e nel campo timestamp — nel content sarebbero solo rumore
    per l'estrattore. Bonus: il content e' stabile per costruzione, quindi il
    document_id derivato dal suo hash resta identico sui replay.

    Budget unico retain_window_max_chars (ICH-151), mai superato. In ordine di
    priorita': l'ultimo messaggio utente e l'ultima risposta (interi, o in
    inizio+fine), poi le sezioni accessorie (esiti in cima, file/comandi in
    fondo), poi gli altri turni dal piu' recente finche' entrano."""
    if not summary["turns"] and not summary["files_modified"]:
        return None
    max_chars = window_max_chars(CFG.get("retain_window_max_chars"))
    head: list[str] = []
    if summary.get("outcomes"):
        head += ["## Command outcomes"] + summary["outcomes"] + [""]
    tail: list[str] = []
    if summary["files_modified"]:
        tail += ["## Files modified"] + [f"- {p}" for p in summary["files_modified"]] + [""]
    if summary["bash_cmds"]:
        tail += ["## Notable commands"] + [f"- {c}" for c in summary["bash_cmds"]] + [""]
    header = "## Conversation (recent turns)"
    # Ogni turno costa len(line) + 1: il separatore "\n" del join finale.
    lines = [f"[{role}] {text}\n" for role, text in summary["turns"]]
    roles = [role for role, _ in summary["turns"]]
    protected = sorted({len(roles) - 1 - roles[::-1].index(r) for r in ("user", "assistant") if r in roles})

    def avail() -> int:
        return max_chars - len("\n".join(head + [header] + tail))

    # Se i turni protetti non hanno almeno un quarto del limite ciascuno, si
    # tolgono prima file/comandi e poi gli esiti.
    need = sum(min(len(lines[j]) + 1, max_chars // 4) for j in protected)
    if avail() < need:
        tail = []
    if avail() < need:
        head = []
    budget = max(0, avail())
    cost = {j: len(lines[j]) + 1 for j in protected}
    if protected and sum(cost.values()) > budget:
        # Il piu' corto prende al massimo meta' dello spazio, l'altro il resto.
        short = min(protected, key=lambda j: cost[j])
        cost[short] = min(cost[short], budget // len(protected))
        for j in protected:
            if j != short:
                cost[j] = budget - cost[short]
    kept = {j: head_tail(lines[j], max(0, cost[j] - 1)) for j in protected}
    budget -= sum(len(line) + 1 for line in kept.values())
    # Storia contigua: al primo turno che non entra si scartano lui e i piu' vecchi.
    for i in range(len(lines) - 1, -1, -1):
        if i in kept:
            continue
        if len(lines[i]) + 1 > budget:
            break
        kept[i] = lines[i]
        budget -= len(lines[i]) + 1
    return "\n".join(head + [header] + [kept[i] for i in sorted(kept)] + tail).strip()


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
        + (
            f"\nJev: score {gate.jev_score:.2f} (soglia {CFG.get('retain_jev_threshold')}) — "
            "p rc/disc/env/eph/repo "
            + "/".join(
                f"{gate.jev_probs[k]:.2f}"
                for k in (
                    "root_cause_or_workaround",
                    "discarded_approach",
                    "environment_constraint",
                    "ephemeral",
                    "repo_recoverable",
                )
            )
            if gate.jev_score is not None
            else (
                f"\nJev: nessun punteggio, errore dopo {gate.jev_latency_ms:.1f} ms"
                if (gate.error or "").startswith("jev:")
                else ""
            )
        )
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


INVALIDATE_TEXT_MAX_CHARS = 300


def _bank_name(bank_url) -> str:
    """Nome del bank: ultimo segmento dell'URL, come nel debug log (ICH-167)."""
    return str(bank_url or "").rsplit("/", 1)[-1]


def ask_invalidation(gate, hook: dict, out: dict | None, mode: str) -> dict | None:
    """ICH-152: se il gate ha trovato memorie smentite dalla finestra, mette
    il ritiro in pending e aggiunge a `out` la domanda (testo della memoria e
    motivo). Solo in deferred: nel drain nessuno puo' rispondere e nessuna
    memoria si ritira. Il ritiro lo esegue handle_invalidate_consent al "si'"."""
    if not gate.contradicted:
        return out
    session_id = hook.get("session_id") or ""
    if mode != "deferred":
        debug_log(CFG, "invalidate_skip", reason=mode, session=session_id[:8])
        return out
    memories = _contradicted_memories(gate)
    if not memories or not save_invalidate_pending(
        session_id, hook.get("cwd") or "", memories, gate.contradiction_reason
    ):
        debug_log(CFG, "invalidate_skip", reason="no_pending", session=session_id[:8])
        return out
    debug_log(
        CFG,
        "invalidate_pending",
        action="saved",
        ids=[m["id"] for m in memories],
        reason=gate.contradiction_reason[:300],
        session=session_id[:8],
    )
    return _with_invalidation_question(out, memories, gate.contradiction_reason)


def _contradicted_memories(gate) -> list[dict]:
    """Memorie smentite dal gate, nel formato del pending di ritiro."""
    return [
        {"id": str(c["id"]), "text": str(c.get("text") or ""), "bank_url": str(c["_bank_url"])}
        for c in (gate.candidates[i] for i in gate.contradicted)
        if c.get("id") and c.get("_bank_url")
    ]


def _with_invalidation_question(out: dict | None, memories: list[dict], reason: str) -> dict:
    """Aggiunge a `out` la domanda di ritiro di `memories` (pending gia' salvato)."""
    head = RETAIN_QUESTION_MARKERS[2] if len(memories) == 1 else RETAIN_QUESTION_MARKERS[3]
    texts = " · ".join(
        f"«{_clip(m['text'], INVALIDATE_TEXT_MAX_CHARS)}» (bank {_bank_name(m['bank_url'])})"
        for m in memories
    )
    question = f"{head} — {texts} Motivo: {reason} (sì/no)"
    instruction = (
        "Hindsight retain gate found existing memories contradicted by a recent "
        "turn. Answer the current prompt normally first. Then, as the very last "
        f"thing in your reply, ask the user verbatim {question!r} and end the turn. "
        "Do not invalidate anything yourself; a yes runs the pending invalidation "
        "at the next prompt."
    )
    merged = dict(out or {})
    merged["systemMessage"] = "\n".join(
        filter(None, [f"Hindsight: {question}", merged.get("systemMessage")])
    )
    hso = dict(merged.get("hookSpecificOutput") or {"hookEventName": "UserPromptSubmit"})
    hso["additionalContext"] = "\n\n".join(
        filter(None, [instruction, hso.get("additionalContext")])
    )
    merged["hookSpecificOutput"] = hso
    merged["asks_consent"] = True
    return merged


# ICH-166: ritiri rinviati perche' il turno ha gia' la domanda del retain.
# Stessa directory dei pending di ritiro, chiave a parte (cwd + suffisso; il
# NUL non compare in un path): handle_invalidate_consent non li legge mai come
# risposta, e la domanda la pone PromptRetain.gate_output al primo turno libero.
DEFERRED_INVALIDATION_SUFFIX = "\0deferred"


def defer_invalidation(gate, hook: dict) -> None:
    """Rinvia il ritiro delle memorie smentite. Ogni memoria porta l'istante
    del rinvio (deferred_at, per il TTL) e si somma ai ritiri gia' rinviati
    della sessione, ognuno col suo motivo."""
    session_id = hook.get("session_id") or ""
    key = (hook.get("cwd") or "") + DEFERRED_INVALIDATION_SUFFIX
    waiting = [
        m
        for m in consume_pending(invalidate_pending_dir(), session_id, key, float("inf")) or []
        if isinstance(m, dict)
    ]
    ids = {m.get("id") for m in waiting}
    now = time.time()
    memories = waiting + [
        dict(m, deferred_at=now) for m in _contradicted_memories(gate) if m["id"] not in ids
    ]
    if not memories or not save_invalidate_pending(
        session_id, key, memories, gate.contradiction_reason
    ):
        debug_log(CFG, "invalidate_skip", reason="no_pending", session=session_id[:8])
        return
    debug_log(
        CFG,
        "invalidate_pending",
        action="deferred",
        ids=[m.get("id") for m in memories],
        reason=gate.contradiction_reason[:300],
        session=session_id[:8],
    )


def ask_deferred_invalidation(out: dict, session_id: str, cwd: str) -> dict:
    """Primo turno libero dopo il rinvio (ICH-166): i ritiri rinviati passano
    nel pending normale e `out` riceve la domanda. Le memorie rinviate da piu'
    di RETAIN_PENDING_TTL cadono con un log."""
    waiting = consume_pending(
        invalidate_pending_dir(), session_id, cwd + DEFERRED_INVALIDATION_SUFFIX, float("inf")
    )
    if not waiting:
        return out
    now = time.time()
    live, expired = [], []
    for m in waiting:
        if isinstance(m, dict):
            fresh = now - float(m.get("deferred_at") or 0) <= RETAIN_PENDING_TTL
            (live if fresh else expired).append(m)
    if expired:
        debug_log(
            CFG,
            "invalidate_skip",
            reason="expired",
            ids=[m.get("id") for m in expired],
            session=session_id[:8],
        )
    if not live:
        return out
    if not save_invalidate_pending(session_id, cwd, live, ""):
        debug_log(CFG, "invalidate_skip", reason="no_pending", session=session_id[:8])
        return out
    debug_log(
        CFG,
        "invalidate_pending",
        action="asked",
        ids=[m.get("id") for m in live],
        session=session_id[:8],
    )
    reason = " · ".join(dict.fromkeys(str(m["reason"]) for m in live if m.get("reason")))
    return _with_invalidation_question(out, live, reason)


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

    # Stop hook non passa 'prompt'; il filtro avviene in build_content_chunk (skip
    # se turns+files_modified entrambi vuoti = finestra senza contenuto utile).
    # drop_unanswered_tail: a UserPromptSubmit il transcript puo' gia' contenere
    # il prompt nuovo; la finestra deve essere quella del turno COMPLETATO.
    transcript = drop_unanswered_tail(load_transcript(hook.get("transcript_path", "")))
    if not transcript:
        debug_log(CFG, "retain_skip", reason="no_transcript")
        return 0, None

    window_turns = max(1, int(CFG.get("retain_every_n_turns", 3))) + int(
        CFG.get("retain_overlap_turns", 1)
    )
    summary = summarize_window(transcript, window_turns)
    content = build_content_chunk(hook, summary)
    if not content:
        debug_log(CFG, "retain_skip", reason="no_content")
        return 0, None

    # Throttling: salta le entry non multiple di N per ridurre le ri-estrazioni
    # LLM ridondanti su sessioni lunghe. force nel drain di fine sessione (cattura
    # la coda) o via HS_RETAIN_FORCE. Il contatore avanza solo sui turni con
    # contenuto utile, e di uno per OGNI Stop realmente avvenuto: l'entry
    # valutata piu' quelle piu' vecchie scartate dal dequeue (queued_skipped).
    session_id = hook.get("session_id") or ""
    force = mode == "drain" or bool(os.environ.get("HS_RETAIN_FORCE"))
    advance = 1 + int(hook.get("queued_skipped") or 0)
    if not should_retain_now(session_id, force=force, advance=advance):
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
        jev_score=None if gate.jev_score is None else round(gate.jev_score, 2),
        jev_latency_ms=gate.jev_latency_ms,
        jev_probs={k: round(v, 2) for k, v in gate.jev_probs.items()},
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
        debug_out = gate_debug_output(gate, "-") if CFG.get("retain_debug_in_context") else None
        return 0, ask_invalidation(gate, hook, debug_out, mode)
    if mode == "drain" and gate.action == "uncertain":
        # Nessun utente a cui chiedere e nessun prompt successivo che possa
        # consumare un pending: l'uncertain a fine sessione si lascia cadere.
        # ask_invalidation non serve: in drain non ritira mai (ICH-152).
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

    # observation_scopes: i tag knowledge:* aggiunti server-side dalle entity_labels
    # frammentano la consolidation (all_strict). Lo scope esplicito dice al
    # consolidatore di usare SOLO i tag fissi; knowledge:* resta sui fatti per il
    # routing alle knowledge page, ma non genera observation separate (ICH-90).
    _retain_kw = (CFG.get("bank") or {}).get("retain_bank", "core")
    _core = (CFG.get("bank") or {}).get("core_bank", "")
    _is_core = resolve_bank(_retain_kw, CFG, hook.get("cwd") or None) == _core
    observation_scopes = [["claude-code"]] if _is_core else [tags]

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

    # document_id: ogni fetta e' un documento con id derivato dal CONTENUTO
    # (fette diverse = documenti diversi, niente perdita tra retain; fetta
    # identica ri-presentata = stesso id, il server fa upsert invece di
    # duplicare — dedup replay esatto, ICH-67). L'hash e' sulla finestra grezza,
    # stabile per costruzione: preview e claims vengono dal LLM del gate e
    # possono cambiare sullo stesso replay.
    if session_id:
        digest = hashlib.sha256(content.encode("utf-8")).hexdigest()[:12]
        doc_id = f"{session_id}-{digest}"
    else:
        doc_id = None

    # ICH-149, variante (c) misurata in ICH-162: claims + preview del gate in
    # cima alla finestra guidano l'estrattore senza togliergli contesto. Senza
    # claims resta la finestra grezza.
    if gate.durable_claims:
        content = guided_content(gate.preview, gate.durable_claims, content)

    item = {
        "content": content,
        "context": context,
        "tags": tags,
        "observation_scopes": observation_scopes,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "metadata": metadata,
    }
    if doc_id:
        item["document_id"] = doc_id

    payload = {"items": [item], "async": True}

    # Per log/dashboard: derivo prompt/assistant dal primo turno user e
    # dall'ultimo turno assistant della finestra — altrimenti i campi
    # apparirebbero vuoti nella dashboard pur essendo il content pieno.
    _turns = summary.get("turns") or []
    log_prompt = next((t for r, t in _turns if r == "user"), "")
    log_assistant = next((t for r, t in reversed(_turns) if r == "assistant"), "")

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
        # La domanda va anche in systemMessage, che Claude Code MOSTRA nel
        # terminale al momento del prompt: additionalContext e' consultivo e
        # nascosto, e l'istruzione compete col task del prompt — se Claude
        # omette la domanda in coda, l'utente la vede comunque qui e puo'
        # rispondere si'/no al prompt dopo (handle_retain_consent non dipende
        # dalla domanda di Claude: context dal gate o, se manca, proposta nel
        # transcript o riga repo/branch). Prima di ICH-86 la reason del
        # decision:block era anch'essa sempre visibile nel transcript.
        if not needs_context:
            visible = f"Hindsight: {question}"
        else:
            visible = (
                f"Hindsight: il gate propone di salvare — {gate.preview.rstrip('.')}. "
                "Claude proporrà un context in coda alla risposta; rispondi "
                "sì / no / `context: …` al prossimo prompt."
            )
        # asks_consent: marca che questo output PONE la domanda del pending.
        # Serve al processo `--queued` per l'outbox: se l'esito arriva solo al
        # prompt successivo, retain_at_prompt deve sapere che la domanda non e'
        # mai stata mostrata e NON leggere quel prompt come risposta. Non
        # arriva mai a Claude Code: la colla del recall fonde solo
        # systemMessage/additionalContext, e main()/gate_output la tolgono.
        out = {
            "systemMessage": visible,
            "hookSpecificOutput": {
                "hookEventName": "UserPromptSubmit",
                "additionalContext": instruction,
            },
            "asks_consent": True,
        }
        if CFG.get("retain_debug_in_context"):
            out["systemMessage"] = "\n".join(
                [visible, gate_debug_context(gate, api_url.rsplit("/", 1)[-1])]
            )
        debug_log(
            CFG,
            "retain_pending",
            action="saved",
            doc_id=doc_id,
            context=context,
            preview=gate.preview[:300],
        )
        if gate.contradicted:
            # Una seconda domanda nello stesso turno renderebbe ambiguo il
            # "si'" (ICH-152): il ritiro si rinvia al turno dopo (ICH-166).
            defer_invalidation(gate, hook)
        return 0, out

    debug_log(
        CFG,
        "retain",
        doc_id=doc_id,
        bank=api_url.rsplit("/", 1)[-1],
        context=context,
        tags=tags,
        content_chars=len(content),
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
    debug_out = None
    if CFG.get("retain_debug_in_context"):
        debug_out = gate_debug_output(gate, api_url.rsplit("/", 1)[-1])
    return 0, ask_invalidation(gate, hook, debug_out, mode)


def evaluate_queued(session_id: str, mode: str = "deferred") -> dict | None:
    """Valutazione differita di UNA sessione (nel processo `--queued` lanciato
    da retain_at_prompt, o in-process nei test): consuma l'entry di coda della
    sessione e la valuta; ritorna il JSON hook-output da fondere con quello del
    recall (None = niente). Non solleva MAI: un bug qui non deve rompere il
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
#   1. PICKUP dell'outbox lasciato dal gate del prompt precedente (se non
#      aveva finito entro il budget dell'hook): il suo output e' quello che
#      gate_output() restituira' per QUESTO prompt. Se portava la domanda del
#      pending (asks_consent), la domanda non e' mai stata mostrata: il
#      consenso di questo prompt va SALTATO — un "si'" digitato ora non puo'
#      riferirsi a lei — e la domanda esce adesso;
#   2. consenso del pending (handle_retain_consent) SINCRONO: risponde alla
#      domanda del turno precedente e puo' consumare il suo pending;
#   3. sweep delle entry di coda piu' vecchie di 24h (di qualunque sessione);
#   4. gate differito in un PROCESSO DETACHED (`--queued <session_id>` ->
#      evaluate_queued -> outbox), PARALLELO al recall che l'hook fa subito
#      dopo, lanciato solo se in coda c'e' un'entry della sessione;
#   5. l'hook chiama gate_output(deadline) al momento dell'emit: aspetta
#      l'outbox al massimo fino alla deadline e fonde l'eventuale output nel
#      suo unico JSON; se il processo non ha finito, esce senza aspettarlo
#      (carried_over) e l'esito si raccoglie al punto 1 del prompt dopo.
# Perche' un processo e non un thread: Claude Code aspetta la chiusura dello
# stdout dell'hook, quindi un thread costringeva l'hook ad aspettare gate LLM
# + POST anche quando l'esito non produce output (skip / retain OK) — fino a
# ~25s di stallo sul prompt. Il processo detached NON eredita stdout/stderr
# dell'hook (log su file), cosi' l'hook puo' uscire e il gate continuare.
# L'ordine consenso -> gate resta quello di prima: il gate puo' creare il
# pending SUCCESSIVO e non deve calpestare quello ancora in attesa; e un "si'"
# non deve mai essere letto come risposta a una domanda non ancora posta.
# I log '[retain]' vanno esplicitamente su stderr: nell'hook lo stdout e' il
# JSON, nel processo `--queued` stdout e stderr sono lo stesso file di log.
# ---------------------------------------------------------------------------


def _strip_marker(output: dict | None) -> dict:
    """Copia dell'output del gate senza la chiave interna asks_consent."""
    out = dict(output or {})
    out.pop("asks_consent", None)
    return out


def _spawn_queued(session_id: str, log_path: str):
    """Lancia `<python> <questo file> --queued <session_id>` DETACHED e ritorna
    il Popen (mai atteso). Il figlio non deve ereditare stdin/stdout/stderr
    dell'hook: Claude Code aspetta la chiusura dello stdout dell'hook, e un
    figlio che lo tenesse aperto ripristinerebbe lo stallo che qui si vuole
    togliere. Quindi stdin DEVNULL, stdout+stderr sul file di log (aperto in
    "w": sovrascritto a ogni lancio, come il vecchio log dello Stop),
    close_fds, e nuova sessione (POSIX) / console NASCOSTA propria + nuovo
    process group (Windows) cosi' non muore con l'hook ne' riceve i suoi
    segnali. Su Windows CREATE_NO_WINDOW e non DETACHED_PROCESS: un figlio
    SENZA console fa allocare una console nuova (visibile: finestre che
    lampeggiano) a ogni nipote console — i git.exe di git_info — e costa
    ~2s in piu' per prompt (misurato 3.6s vs 1.3s); con la console nascosta
    i nipoti si agganciano a quella. Il figlio sopravvive comunque all'uscita
    dell'hook e non tiene aperto il suo stdout (verificato dai test e2e).
    Env copiato dall'hook: HS_*, API_URL, HS_OPENAI_URL ecc. valgono anche
    nel figlio. Funzione a livello di modulo perche' i test la sostituiscono
    con un launcher in-process."""
    kwargs: dict = {}
    if os.name == "nt":
        kwargs["creationflags"] = (
            subprocess.CREATE_NO_WINDOW | subprocess.CREATE_NEW_PROCESS_GROUP
        )
    else:
        kwargs["start_new_session"] = True
    log = open(log_path, "w", encoding="utf-8")
    try:
        return subprocess.Popen(
            [sys.executable, os.path.abspath(str(__file__)), "--queued", session_id],
            stdin=subprocess.DEVNULL,
            stdout=log,
            stderr=subprocess.STDOUT,
            close_fds=True,
            env=os.environ.copy(),
            **kwargs,
        )
    finally:
        # Popen ha gia' duplicato l'handle nel figlio: il nostro si chiude.
        log.close()


class PromptRetain:
    """Esito del lato retain di un prompt (retain_at_prompt) per l'hook recall.
    outcome: esito di handle_retain_consent, o di handle_invalidate_consent se
    il prompt non ha risposto a un pending retain (None = nessun pending o
    consenso saltato per un outbox con domanda mai mostrata);
    consent_output: JSON hook-output del consenso gia' formattato
    (systemMessage / additionalContext), {} se niente;
    notice: "Hindsight: memoria in attesa scartata — …" su prompt nuovo, altrimenti "";
    saved: True su outcome saved o su un "si'" al ritiro -> il chiamante scarta
    i medium pending del recall;
    stop_here: True su saved/error -> il chiamante emette consent_output ed esce
    senza recall (come sempre);
    launched: True se il processo `--queued` e' stato lanciato per questo prompt.
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
        self.launched: bool = False
        # Stato privato del gate: output raccolto dall'outbox del prompt
        # precedente (pickup), processo lanciato (mai atteso), cache di
        # gate_output (idempotente: emit() e finish() possono chiamarla
        # entrambe).
        self._session_id: str = session_id or ""
        self._leftover: dict | None = None
        self._proc = None
        self._gate: dict | None = None
        # ICH-166: cwd della sessione (None = retain_at_prompt fallito: niente
        # ritiri rinviati) e turno gia' occupato da un'altra domanda Hindsight.
        self._cwd: str | None = None
        self._busy: bool = False
        self._leftover_asks: bool = False

    def gate_output(self, deadline: float) -> dict:
        """Output del gate differito per questo prompt, entro deadline
        (time.monotonic). Se c'era un outbox raccolto al pickup e' quello,
        subito. Altrimenti, se il processo e' stato lanciato, fa polling
        dell'outbox fino alla deadline; se non compare in tempo ritorna {} e
        NON segna nessun fallimento: il processo continua per conto suo e
        l'esito viene raccolto al prompt successivo (retain_deferred
        carried_over) — nulla si perde, ne' POST ne' domanda. {} anche senza
        gate. Se il turno resta libero (nessuna domanda del gate, esito del
        gate noto, nessun retry in attesa) aggiunge la domanda dei ritiri
        rinviati (ICH-166). Idempotente: il risultato viene cachato, cosi' una
        seconda chiamata non ri-aspetta ne' cambia esito."""
        if self._gate is not None:
            return self._gate
        self._gate = {}
        # free: l'esito del gate di questo turno e' noto e non pone domande.
        # Con un gate ancora in corso il turno non e' libero: il processo
        # potrebbe ancora porre una domanda o scrivere i ritiri rinviati.
        free = not self._busy
        if self._leftover is not None:
            self._gate = _strip_marker(self._leftover)
            free = free and not self._leftover_asks and not self.launched
        elif self.launched:
            free = False
            try:
                while True:
                    box = _read_outbox(self._session_id)
                    if box is not None:
                        self._gate = _strip_marker(box.get("output") or {})
                        free = not self._busy and not box.get("asks_consent")
                        break
                    if time.monotonic() >= deadline:
                        debug_log(
                            CFG,
                            "retain_deferred",
                            action="carried_over",
                            session=self._session_id[:8],
                        )
                        break
                    time.sleep(OUTBOX_POLL_S)
            except Exception as exc:
                debug_log(
                    CFG,
                    "retain_error",
                    where="gate_output",
                    error=f"{type(exc).__name__}: {exc}"[:300],
                    session=self._session_id[:8],
                )
                self._gate = {}
        if free and self._cwd is not None:
            try:
                self._gate = _strip_marker(
                    ask_deferred_invalidation(self._gate, self._session_id, self._cwd)
                )
            except Exception as exc:
                debug_log(
                    CFG,
                    "retain_error",
                    where="ask_deferred_invalidation",
                    error=f"{type(exc).__name__}: {exc}"[:300],
                    session=self._session_id[:8],
                )
        return self._gate


# Marcatori delle domande di consenso poste da Claude (i testi sono cablati nel
# ramo pending di evaluate()): servono per capire, al prompt successivo, se la
# domanda e' stata DAVVERO posta oppure omessa.
RETAIN_QUESTION_MARKERS = (
    "Vuoi che salvi questa memoria?",
    "Salvo questa memoria con context",
    # Domande di ritiro (ICH-152), usate anche da ask_invalidation.
    "Ritiro la memoria contraddetta?",
    "Ritiro le memorie contraddette?",
)


def _question_was_asked(transcript_path: str) -> bool:
    """True se l'ultimo testo assistant contiene una delle domande di consenso.
    Senza transcript non si puo' dire: si assume posta (notifica classica)."""
    if not transcript_path:
        return True
    try:
        text = last_assistant_text(transcript_path)
    except Exception:
        return True
    return any(marker in text for marker in RETAIN_QUESTION_MARKERS)


def _consent_output(outcome: dict, transcript_path: str = "") -> tuple[dict, str, bool, bool]:
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
    # Se Claude ha OMESSO la domanda in coda alla risposta (additionalContext e'
    # consultivo), la notifica non deve presupporre una domanda mai vista: lo
    # si dice esplicitamente, cosi' l'utente capisce perche' non ha risposto.
    if outcome.get("reason") == "new_prompt":
        preview = outcome.get("preview") or ""
        asked = _question_was_asked(transcript_path)
        head = (
            "Hindsight: memoria in attesa scartata"
            if asked
            else "Hindsight: memoria in attesa scartata (domanda non posta da Claude)"
        )
        notice = f"{head} — {preview}" if preview else head
        return {}, notice, False, False
    return {}, "", False, False


def _invalidate_output(outcome: dict, transcript_path: str = "") -> tuple[dict, str, bool, bool]:
    """Come _consent_output, per l'esito di handle_invalidate_consent (ICH-152).
    Sul "si'" (ritiro eseguito o fallito) saved=True: lo stesso "si'" non
    autorizza anche le memorie medium in pending del recall."""
    action = outcome.get("action")
    memories = outcome.get("memories") or []
    if action == "invalidated":
        lines = [
            f"Hindsight: memoria ritirata — «{_clip(str(m.get('text') or ''), INVALIDATE_TEXT_MAX_CHARS)}» "
            f"(bank {_bank_name(m.get('bank_url'))}, id {m.get('id')}). "
            "Per ripristinarla: invalidate_memory con restore=true."
            for m in memories
        ]
        output = {
            "systemMessage": "\n".join(lines),
            "hookSpecificOutput": {
                "hookEventName": "UserPromptSubmit",
                "additionalContext": (
                    "## Hindsight invalidate\n\nLe memorie contraddette sono state "
                    "ritirate (reversibile). Non serve alcuna azione manuale."
                ),
            },
        }
        return output, "", True, True
    if action == "error":
        done = [
            f"{m.get('id')} (bank {_bank_name(m.get('bank_url'))})"
            for m in outcome.get("invalidated") or []
        ]
        message = "Hindsight: ritiro della memoria NON riuscito — " + str(outcome.get("error") or "")
        if done:
            message += f" Già ritirate: {', '.join(done)}."
        if outcome.get("restored"):
            message += " Rispondi «sì» al prossimo prompt per riprovare."
        return {"systemMessage": message}, "", True, True
    if outcome.get("reason") == "new_prompt":
        head = (
            "Hindsight: ritiro della memoria annullato"
            if _question_was_asked(transcript_path)
            else "Hindsight: ritiro della memoria annullato (domanda non posta da Claude)"
        )
        texts = " · ".join(
            f"«{_clip(str(m.get('text') or ''), INVALIDATE_TEXT_MAX_CHARS)}»" for m in memories
        )
        return {}, f"{head} — {texts}" if texts else head, False, False
    return {}, "", False, False


def retain_at_prompt(
    prompt: str, session_id: str, cwd: str, transcript_path: str
) -> PromptRetain:
    """Lato retain di un UserPromptSubmit, nell'ordine del commento di sezione:
    pickup dell'outbox del prompt precedente, consenso del pending (sincrono,
    con la stessa chiamata e lo stesso debug_log di sempre; saltato se
    l'outbox porta una domanda mai mostrata), sweep delle entry stantie e
    lancio del gate differito in un processo detached (`--queued`), il cui
    esito il chiamante ritira con gate_output(deadline). Non solleva MAI:
    qualunque eccezione va nel debug log e ritorna un PromptRetain a campi
    vuoti (l'hook recall prosegue come se non ci fosse nulla da fare lato
    retain).
    Il gate NON parte in due casi, per la stessa ragione — un nuovo pending
    della stessa sessione sovrascriverebbe (un file per session+cwd) quello
    ancora in attesa di risposta: (a) il "si'" e' fallito e il pending e'
    stato RIMESSO in attesa (restored); (b) l'outbox raccolto ora pone la
    domanda del pending, che l'utente vede solo adesso. L'entry in coda resta
    e si valuta al prompt dopo. Con retain_enabled false l'entry si scarta
    qui, in-process, senza lanciare nulla."""
    result = PromptRetain(session_id)
    try:
        # 1. Pickup: l'esito del gate del prompt precedente, se non era
        # arrivato in tempo. Va PRIMA del consenso: se porta la domanda del
        # pending, quel pending non e' mai stato mostrato e il prompt attuale
        # non puo' esserne la risposta.
        skip_consent = False
        leftover = _read_outbox(session_id) if session_id else None
        result._cwd = cwd or ""
        if leftover is not None:
            result._leftover = dict(leftover.get("output") or {})
            skip_consent = bool(leftover.get("asks_consent"))
            result._leftover_asks = skip_consent
            debug_log(
                CFG,
                "retain_deferred",
                action="picked_up",
                asks_consent=skip_consent,
                session=session_id[:8],
            )
        # 2. Consenso PRIMA di tutto il resto, incluso il gate recall_enabled
        # dell'hook: la domanda del gate retain e' sempre la piu' recente
        # (posta alla fine del turno precedente), quindi un si'/no secco (o
        # un `context: …`) appartiene a lei, e va onorata anche nei progetti
        # col recall spento. Il transcript serve a ripescare il context
        # proposto da Claude nella domanda.
        outcome = None
        if not skip_consent:
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
            ) = _consent_output(outcome, transcript_path)
        # 2b. Consenso al ritiro (ICH-152). Se il prompt ha gia' risposto a un
        # pending retain, il pending di ritiro si scarta senza leggere il
        # prompt: lo stesso "si'" non vale per due domande.
        if not skip_consent:
            invalidation = handle_invalidate_consent(
                prompt if outcome is None else "", session_id, cwd
            )
            if invalidation and outcome is None:
                debug_log(
                    CFG,
                    "invalidate_pending",
                    action=invalidation.get("action"),
                    reason=invalidation.get("reason"),
                    error=invalidation.get("error"),
                    ids=[m.get("id") for m in invalidation.get("memories") or []],
                )
                result.outcome = invalidation
                (
                    result.consent_output,
                    result.notice,
                    result.saved,
                    result.stop_here,
                ) = _invalidate_output(invalidation, transcript_path)
        # 3. Entry stantie di qualunque sessione: via, con marker.
        sweep_stale_queue()
        # 4. Lancio del gate differito, solo se c'e' qualcosa da valutare.
        # result.outcome: il retain o, se non ha risposto, il ritiro (ICH-152).
        # Un retry in attesa ("rispondi si' per riprovare") occupa il turno:
        # niente domanda dei ritiri rinviati (ICH-166).
        result._busy = bool(result.outcome and result.outcome.get("restored"))
        if result._busy or skip_consent:
            return result
        if not has_queued(session_id):
            return result
        if not CFG.get("retain_enabled", True):
            # Interruttore master spento: l'entry si consuma e basta (come
            # farebbe evaluate()), senza pagare un processo per non fare nulla.
            dequeue_for_session(session_id)
            debug_log(CFG, "retain_skip", reason="disabled", session=session_id[:8])
            return result
        try:
            result._proc = _spawn_queued(
                session_id, os.path.join(cache_dir(), "hs-retain.log")
            )
            result.launched = True
            debug_log(CFG, "retain_deferred", action="launched", session=session_id[:8])
        except Exception as exc:
            # Lancio fallito (interprete, permessi, log non scrivibile): il
            # consenso appena calcolato non va buttato con lui — si logga e
            # l'entry resta in coda per il prompt dopo (o per il drain).
            debug_log(
                CFG,
                "retain_error",
                where="spawn_queued",
                error=f"{type(exc).__name__}: {exc}"[:300],
                session=session_id[:8],
            )
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


def run_queued(session_id: str) -> None:
    """Corpo del processo detached `--queued <session_id>` (lanciato da
    retain_at_prompt): la stessa valutazione di evaluate_queued(session_id,
    "deferred"), ma l'esito finisce SEMPRE nell'outbox — anche {} (niente da
    dire, coda vuota, retain disabilitato: evaluate esce prima e l'entry e'
    comunque consumata) — cosi' chi aspetta (gate_output nell'hook, o il
    pickup del prompt dopo) distingue "finito senza output" da "ancora in
    corso". asks_consent va nell'involucro, non nell'output. Non solleva."""
    out = None
    try:
        out = evaluate_queued(session_id, "deferred")
    finally:
        out = dict(out or {})
        asks_consent = bool(out.pop("asks_consent", False))
        _write_outbox(session_id, out, asks_consent)


def main(argv: list[str] | None = None) -> int:
    """Modalita' script. `--drain`: svuota la coda valutando ogni entry in
    "drain" (sentinel di fine sessione), best-effort per entry. `--queued
    <session_id>`: processo detached lanciato da retain_at_prompt, valuta
    l'entry della sessione in "deferred" e scrive l'outbox (run_queued); exit
    0 sempre (una POST non arrivata lascia il marker come al solito). Senza
    flag: valuta $HOOK_INPUT in "deferred" e stampa 'HSGATE {json}' su stdout
    quando c'e' output (tools/hindsight-check.sh e run manuali), senza la
    chiave interna asks_consent; i log '[retain]' vanno su stderr in tutte le
    modalita'."""
    args = list(sys.argv[1:] if argv is None else argv)
    if "--queued" in args:
        idx = args.index("--queued")
        session_id = args[idx + 1] if idx + 1 < len(args) else ""
        if session_id:
            run_queued(session_id)
        else:
            print("[retain] --queued senza session_id", file=sys.stderr)
        return 0
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
    out = _strip_marker(out)
    if out:
        print("HSGATE " + json.dumps(out, ensure_ascii=False))
    return rc


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
