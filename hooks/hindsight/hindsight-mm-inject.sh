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

HOOKS_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
export HOOKS_DIR

. "$HOOKS_DIR/lib/hs-python.sh"

PYTHONUTF8=1 "$HS_PY" <<'PY' 2>/dev/null
import json, os, sys, time, urllib.request, urllib.error

sys.path.insert(0, os.path.join(os.environ["HOOKS_DIR"], "lib"))
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

    # (url, [ids]) per ogni bank risolto, dedup per NOME. I modelli CORE sono filtrati
    # da mental_models_inject_ids, quelli di PROGETTO da project_mental_models_inject_ids.
    targets = []
    _seen = set()
    for n in names:
        b = resolve_bank(n, cfg)
        if not b or b in _seen:
            continue
        _seen.add(b)
        if b == core:
            _ids = cfg.get("mental_models_inject_ids") or []
        else:
            _ids = cfg.get("project_mental_models_inject_ids") or []
        if _ids:
            targets.append((bank_url(cfg, b), _ids))

# Coppie (url, id) da iniettare, in ordine di bank (progetto poi core).
pairs = []
for url, _ids in targets:
    for mid in _ids:
        pairs.append((url, mid))

if not pairs:
    sys.exit(0)


def http_status(url, timeout=3):
    """Status HTTP, o None se la connessione fallisce (server non ancora su)."""
    try:
        with urllib.request.urlopen(
            urllib.request.Request(url, method="GET"), timeout=timeout
        ) as res:
            return res.status
    except urllib.error.HTTPError as e:
        return e.code  # 404/5xx: il server HA risposto
    except Exception:
        return None  # connessione rifiutata/timeout: non pronto


def wait_ready(url, deadline):
    """Attende che il server risponda con status < 500 entro deadline."""
    while time.monotonic() < deadline:
        st = http_status(url)
        if st is not None and st < 500:
            return True
        time.sleep(1)
    return False


# Gli hook SessionStart girano IN PARALLELO (doc Claude Code): hindsight-ensure-up.sh
# sta avviando il server proprio ora. A freddo le GET sotto arriverebbero prima che sia
# pronto e tornerebbero a mani vuote. Attendi la readiness (budget affine a ensure-up),
# poi procedi; se non e' pronto entro il budget, esci pulito (best-effort invariato).
# Un 404 sul primo id conta come pronto: server e DB su, l'id semplicemente non c'e'.
if not wait_ready(f"{pairs[0][0]}/mental-models/{pairs[0][1]}", time.monotonic() + 20):
    sys.exit(0)

blocks = []
_seen_ids = set()
for url, mid in pairs:
    if mid in _seen_ids:
        continue  # dedup per id: un id di progetto non deve riusare gli id core
    _seen_ids.add(mid)
    try:
        # detail=content: senza, il default e' "full" che trascina anche il
        # reflect_response (provenance, anche centinaia di KB) — qui inutile,
        # servono solo name e content.
        req = urllib.request.Request(f"{url}/mental-models/{mid}?detail=content", method="GET")
        with urllib.request.urlopen(req, timeout=2) as res:
            m = json.loads(res.read().decode("utf-8", errors="replace"))
    except Exception:
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
