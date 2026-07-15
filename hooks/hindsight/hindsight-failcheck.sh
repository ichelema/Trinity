#!/usr/bin/env bash
# UserPromptSubmit hook: rileva i retain (e altri task async) falliti SILENZIOSAMENTE
# lato server Hindsight e avvisa l'utente via additionalContext.
#
# Perche' serve: retain() e' asincrono -> ritorna subito {status:"accepted"}. Se
# l'estrazione fatti (OpenAI gpt-4.1-nano) fallisce (credito esaurito, rate limit),
# l'operation finisce in stato "failed" DOPO i retry, senza che il chiamante se ne
# accorga: la memoria NON viene salvata ma sembra accettata. Questo hook interroga
# GET .../operations?status=failed e segnala le failed recenti, UNA volta ciascuna.
#
# Indipendente dal recall (recall_enabled non lo tocca). Latenza ~10ms/bank (query
# DB locale). De-dup via state file: ogni evento e' notificato una sola volta.
set -uo pipefail

HOOKS_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
HOOK_INPUT="$(cat)"
export HOOK_INPUT HOOKS_DIR

. "$HOOKS_DIR/lib/hs-python.sh"

"$HS_PY" <<'PY' 2>/dev/null
import json, os, sys, urllib.request
from datetime import datetime, timezone, timedelta

# Forza UTF-8 su stdout: il python MSYS UCRT64 usa cp1252 di default e il testo
# dell'avviso contiene caratteri fuori da Latin-1 (es. "—", emoji), che altrimenti
# lanciano UnicodeEncodeError. Non dipendiamo da PYTHONUTF8 nell'ambiente.
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

sys.path.insert(0, os.path.join(os.environ["HOOKS_DIR"], "lib"))
from hindsight_config import cache_dir, load_config, retain_bank_url, recall_bank_urls

cfg = load_config()

# Interruttore master dedicato: non dipende da recall/retain_enabled.
if not cfg.get("failcheck_enabled", True):
    sys.exit(0)

try:
    hook = json.loads(os.environ["HOOK_INPUT"])
except Exception:
    sys.exit(0)
cwd = hook.get("cwd") or None

# Bank da controllare: unione di retain (dove scrivono i retain automatici) e
# recall (include il core, dove finiscono i retain via MCP). Dedup preservando ordine.
urls, seen_u = [], set()
for u in [retain_bank_url(cfg, cwd), *recall_bank_urls(cfg, cwd)]:
    if u and u not in seen_u:
        seen_u.add(u)
        urls.append(u)

# Finestra temporale: segnala solo le failed recenti (al primo avvio, con state
# file vuoto, evita di ripescare tutta la storia delle failed del bank).
window_h = float(cfg.get("failcheck_window_hours", 24))
cutoff = datetime.now(timezone.utc) - timedelta(hours=window_h)
timeout = float(cfg.get("failcheck_timeout", 3))


def _parse(ts):
    try:
        return datetime.fromisoformat(ts)
    except Exception:
        return None


# Raccogli le operation failed da ogni bank. Una failed resta failed: per non
# rinotificarla a ogni prompt c'e' il de-dup piu' sotto.
raw = []
for base in urls:
    try:
        req = urllib.request.Request(
            base + "/operations?status=failed&limit=20", method="GET"
        )
        with urllib.request.urlopen(req, timeout=timeout) as res:
            data = json.loads(res.read().decode("utf-8", errors="replace"))
    except Exception:
        continue  # bank giu'/irraggiungibile: best-effort, salta
    bank = base.rsplit("/", 1)[-1]
    for op in data.get("operations") or []:
        when = _parse(op.get("updated_at") or op.get("created_at") or "")
        if when is not None and when < cutoff:
            continue
        raw.append({
            "bank": bank,
            "created": op.get("created_at") or "",
            "task_type": op.get("task_type") or "?",
            "error": (op.get("error_message") or "").strip(),
        })

# Fallimenti LOCALI del retain: il worker non ha raggiunto il server, quindi non
# esiste nessuna operation e il fan-out qui sopra non li vede. Li appende
# hindsight-retain.sh. Da leggere SEMPRE, anche con raw vuoto: il caso peggiore
# (server irraggiungibile) da' raw=[] proprio PERCHE' tutto e' fallito.
local_file = os.path.join(cache_dir(), "hs-retain-failed.log")
local_fails = []
try:
    with open(local_file, encoding="utf-8") as f:
        for line in f:
            ts, _, msg = line.strip().partition("\t")
            if not ts:
                continue
            when = _parse(ts.replace("Z", "+00:00"))
            if when is not None and when < cutoff:
                continue  # fuori finestra: stessa politica delle failed server-side
            local_fails.append((ts, msg))
except FileNotFoundError:
    pass
except Exception:
    pass  # marker illeggibile: best-effort, non deve rompere il prompt

if not raw and not local_fails:
    sys.exit(0)

# Collassa parent/child dello stesso evento: un batch_retain fallito genera 2 entry
# (batch_retain + retain) con stesso created_at. Raggruppa per (bank, created_at) e
# tieni il rappresentante, preferendo il parent batch_retain.
_RANK = {"batch_retain": 0, "retain": 1}
groups = {}
for r in raw:
    key = (r["bank"], r["created"])
    cur = groups.get(key)
    if cur is None or _RANK.get(r["task_type"], 9) < _RANK.get(cur["task_type"], 9):
        groups[key] = r

# De-dup di notifica: state file con le chiavi gia' segnalate. cache_dir() e'
# per-utente e 0700 (su Linux /tmp e' scrivibile da tutti) ed e' stabile cross-drive:
# un literal "/tmp/..." su Python nativo si risolverebbe come <drive-corrente>:\tmp,
# variando col cwd della sessione.
state_file = os.path.join(cache_dir(), "hs-failcheck-seen.json")
try:
    with open(state_file, encoding="utf-8") as f:
        # round-trip JSON: le liste tornano tuple per il confronto con groups
        notified = set(tuple(x) for x in json.load(f))
except Exception:
    notified = set()

fresh = {k: v for k, v in groups.items() if k not in notified}
if not fresh and not local_fails:
    sys.exit(0)

# Gravita' per famiglia di task: retain = perdita di memoria (critico); il resto =
# mantenimento (consolidation/refresh_mental_model/graph_maintenance), di norma si
# auto-recupera al ciclo successivo.
RETAIN = {"retain", "batch_retain"}
crit, maint = [], []
for r in fresh.values():
    hhmm = (r["created"][11:16] if len(r["created"]) >= 16 else r["created"])
    err = r["error"][:160]
    line = f"- {r['task_type']} [bank: {r['bank']}, {hhmm}] — {err}"
    (crit if r["task_type"] in RETAIN else maint).append(line)

# I fallimenti locali sono retain a tutti gli effetti: memoria non salvata. Vanno
# in crit con provenienza esplicita. Il "cosa e' andato storto" lo porta il messaggio,
# non l'etichetta: nel file scrivono due produttori con cause diverse — la POST mai
# partita (hindsight-retain.sh) e l'estrazione non completata prima dello stop del
# server (hindsight-drain-retain.py). In entrambi i casi non c'e' nessuna operation
# failed da ri-controllare lato server.
for ts, msg in local_fails:
    hhmm = ts[11:16] if len(ts) >= 16 else ts
    crit.append(f"- retain [locale, {hhmm}] — {msg[:160]}")

parts = ["## ⚠️ Hindsight — operazioni di memoria fallite\n"]
if crit:
    parts.append(
        "**Retain falliti: memoria NON salvata.** Questi contenuti non sono stati "
        "memorizzati e vanno ri-sottomessi (verifica prima il credito OpenAI se "
        "l'errore e' RateLimitError):\n" + "\n".join(crit)
    )
if maint:
    parts.append(
        "\n**Task di mantenimento falliti** (di norma si auto-recuperano, nessuna "
        "perdita di dati utente):\n" + "\n".join(maint)
    )
context = "\n".join(parts)

# Consegna PRIMA l'avviso, marca lo state DOPO: se il print fallisse, l'evento non
# va perso (lo state non viene aggiornato e il prossimo prompt riprova).
print(json.dumps({
    "hookSpecificOutput": {
        "hookEventName": "UserPromptSubmit",
        "additionalContext": context,
    }
}, ensure_ascii=False))

# Marker locali: il de-dup e' il troncamento del file, DOPO il print (stessa regola
# dello state file sotto). Race teorica: un retain async potrebbe appendere tra la
# lettura e il troncamento e perdere quella riga — finestra di millisecondi tra Stop
# e UserPromptSubmit, che in pratica non si sovrappongono; non vale un lock.
if local_fails:
    try:
        open(local_file, "w").close()
    except Exception:
        pass

# Aggiorna lo state file: aggiungi i notificati ora, poi pota le chiavi fuori
# finestra (created_at < cutoff) per evitare crescita illimitata.
notified |= set(fresh.keys())
pruned = []
for bank, created in notified:
    w = _parse(created)
    if w is None or w >= cutoff:
        pruned.append([bank, created])
try:
    os.makedirs(os.path.dirname(state_file), exist_ok=True)
    with open(state_file, "w", encoding="utf-8") as f:
        json.dump(pruned, f)
except Exception:
    pass
PY
