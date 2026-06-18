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

PYTHONUTF8=1 python <<'PY' 2>/dev/null
import json, os, sys, urllib.request, urllib.error

sys.path.insert(0, os.path.join(os.environ["HOOKS_DIR"], "lib"))
from hindsight_config import load_config

cfg = load_config()

# Gate: disattivato di default. Si abilita con mental_models_inject_on_start=true
# nel config, oppure HS_CFG_MENTAL_MODELS_INJECT_ON_START=1.
if not cfg.get("mental_models_inject_on_start"):
    sys.exit(0)

base = cfg["api_url"]
ids = cfg.get("mental_models_inject_ids") or []
if not ids:
    sys.exit(0)

blocks = []
for mid in ids:
    try:
        req = urllib.request.Request(f"{base}/mental-models/{mid}", method="GET")
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

context = (
    "## Hindsight knowledge pages (advisory, auto-maintained)\n\n"
    + "\n\n".join(blocks)
    + "\n\nUse as consultative context. Verify mutable facts against the repo."
)

print(json.dumps({
    "hookSpecificOutput": {
        "hookEventName": "SessionStart",
        "additionalContext": context,
    }
}, ensure_ascii=False))
PY
