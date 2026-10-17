#!/usr/bin/env bash
# SessionStart hook: inietta le "knowledge page" (mental model) come additionalContext
# all'inizio della sessione, cosi' l'agente parte con il profilo utente e le convenzioni
# di progetto gia' in contesto.
#
# GATED: attivo solo se mental_models_inject_on_start=true in hindsight.config.json
# (default false). BEST-EFFORT: se il server e' giu' o le pagine non hanno ancora
# contenuto, esce in silenzio senza disturbare l'avvio. Il blocco usa lo stesso trailer
# del recall ("Verify mutable facts...") cosi' il retain worker lo scarta (anti-loop).
set -uo pipefail

# Parameter expansion e non $(cd "$(dirname ...)" && pwd): subshell + dirname
# costano 200-650ms su MSYS. Stesso schema di hindsight-recall.sh.
HOOKS_DIR="${BASH_SOURCE[0]%/*}"; [ "$HOOKS_DIR" = "${BASH_SOURCE[0]}" ] && HOOKS_DIR="."
case "$HOOKS_DIR" in
[A-Za-z]:/*) _hs_drive="${HOOKS_DIR%%:*}"; HOOKS_DIR="/${_hs_drive,,}${HOOKS_DIR#?:}" ;;
esac
export HOOKS_DIR

. "$HOOKS_DIR/lib/hs-python.sh"

# stderr su file (sovrascritto a ogni run) e NON /dev/null: vedi hindsight-recall.sh.
PYTHONUTF8=1 "$HS_PY" <<'PY' 2>"$HS_CACHE_DIR/hs-mm-inject-stderr.log"
import json, os, sys, time, urllib.request, urllib.error

sys.path.insert(0, os.path.join(os.environ["HOOKS_DIR"], "lib"))
if os.environ.get("HINDSIGHT_RECORD") == "1":  # recorder dei golden (ICH-173)
    import hindsight_recorder
    hindsight_recorder.start("hindsight-mm-inject")
from hindsight_config import load_config, resolve_bank, bank_url

cfg = load_config()

# Gate: disattivato di default. Si abilita con mental_models_inject_on_start=true
# nel config, oppure HS_CFG_MENTAL_MODELS_INJECT_ON_START=1.
if not cfg.get("mental_models_inject_on_start"):
    sys.exit(0)

# Retrocompat api_url (vedi hindsight_config.py, load_config): se impostato
# esplicitamente (config fidato o HINDSIGHT_API_URL), vince su tutto il blocco
# bank -> single-bank legacy, solo gli id CORE (comportamento pre-PR).
if cfg.get("_api_url_explicit"):
    targets = [(cfg["api_url"], cfg.get("mental_models_inject_ids") or [])]
else:
    core = (cfg.get("bank") or {}).get("core_bank", "trinity-project")
    names = cfg.get("mental_model_inject_banks") or ["auto", "core"]

    # Solo il core definisce mental model (ICH-104): inietta gli id CORE se uno
    # dei bank configurati risolve al core, altrimenti niente.
    _ids = cfg.get("mental_models_inject_ids") or []
    if _ids and any(resolve_bank(n, cfg) == core for n in names):
        targets = [(bank_url(cfg, core), _ids)]
    else:
        targets = []

# Coppie (url, id) da iniettare.
pairs = []
for url, _ids in targets:
    for mid in _ids:
        pairs.append((url, mid))

if not pairs:
    sys.exit(0)


def fetch(url, mid, timeout=2):
    """(status, mental model). status None se la connessione fallisce (server
    non ancora su); model None se la pagina manca o il JSON non e' valido.
    detail=content: senza, il default e' "full" che trascina anche il
    reflect_response (provenance, anche centinaia di KB) — qui inutile,
    servono solo name e content."""
    req = urllib.request.Request(f"{url}/mental-models/{mid}?detail=content", method="GET")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as res:
            status, body = res.status, res.read()
    except urllib.error.HTTPError as e:
        return e.code, None  # 404/5xx: il server HA risposto
    except Exception:
        return None, None  # connessione rifiutata/timeout: non pronto
    try:
        return status, json.loads(body.decode("utf-8", errors="replace"))
    except ValueError:
        return status, None


# Gli hook SessionStart girano IN PARALLELO (doc Claude Code): hindsight-ensure-up.sh
# sta aprendo il tunnel verso la VPS proprio ora. Le GET arriverebbero prima che sia
# pronto e tornerebbero a mani vuote. Ritenta la PRIMA pagina finche' il server non
# risponde (budget affine a ensure-up); se non e' pronto entro il budget, esci pulito
# (best-effort invariato). Un 404 conta come pronto: server e DB su, l'id non c'e'.
# La prima GET fa da readiness e il suo risultato si riusa: niente richiesta in piu'.
deadline = time.monotonic() + 20
while True:
    status, first = fetch(*pairs[0], timeout=3)
    if status is not None and status < 500:
        break
    if time.monotonic() >= deadline:
        sys.exit(0)
    time.sleep(1)

blocks = []
_seen_ids = set()
for url, mid in pairs:
    if mid in _seen_ids:
        continue  # dedup per id: un id di progetto non deve riusare gli id core
    _seen_ids.add(mid)
    m = first if (url, mid) == pairs[0] else fetch(url, mid)[1]
    if not isinstance(m, dict):
        continue  # server giu' o pagina assente: best-effort, salta
    content = (m.get("content") or "").strip()
    if not content:
        continue
    blocks.append(f"### {m.get('name', mid)}\n\n{content}")

if not blocks:
    sys.exit(0)

HEADER = "## Hindsight knowledge pages (advisory, auto-maintained)\n\n"
TRAILER = "\n\nUse as consultative context. Verify mutable facts against the repo."
SEP = "\n\n"

# Claude Code tronca l'output degli hook oltre 10.000 char (e per un bug noto il
# preview inline si ferma a ~2.000: issue #44086): meglio cedere la coda delle
# pagine che perdere l'80% del blocco. Taglio EQUO: ogni pagina cede in
# proporzione alla propria lunghezza, a fine riga, con marcatore visibile.
# Il TRAILER non si tocca mai: e' l'ancora anti-feedback-loop che il retain
# worker usa per scartare il blocco (strip_memory_block).
max_chars = int(cfg.get("mental_models_inject_max_chars") or 9500)
budget = max_chars - len(HEADER) - len(TRAILER) - len(SEP) * (len(blocks) - 1)
total = sum(len(b) for b in blocks)
if total > budget:
    marker = "\n[...troncato: budget contesto]"
    ratio = (budget - len(marker) * len(blocks)) / total
    cut = []
    for b in blocks:
        target = int(len(b) * ratio)
        if 0 < target < len(b):
            head = b[:target]
            head = head[:head.rfind("\n")] if "\n" in head else head
            cut.append(head.rstrip() + marker)
        else:
            cut.append(b)
    blocks = cut

context = HEADER + SEP.join(blocks) + TRAILER

print(json.dumps({
    "hookSpecificOutput": {
        "hookEventName": "SessionStart",
        "additionalContext": context,
    }
}, ensure_ascii=False))
PY
