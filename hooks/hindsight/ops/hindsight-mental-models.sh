#!/usr/bin/env bash
# Utility (NON hook): gestione delle "knowledge page" Hindsight (mental model).
# Un mental model e' una reflection pinnata: documento vivo rigenerato eseguendo
# una source_query via reflect. Le definizioni stanno in hindsight.config.json
# (chiave "mental_models" per i modelli CORE, "project_mental_models" per quelli
# del progetto); qui si fanno seed/list/show/refresh via REST sul bank risolto dal cwd.
#
# Uso:
#   bash hindsight-mental-models.sh seed                # crea le pagine mancanti (idempotente)
#   bash hindsight-mental-models.sh list                # elenco con stato staleness
#   bash hindsight-mental-models.sh show <id>           # stampa il contenuto di una pagina
#   bash hindsight-mental-models.sh refresh [<id>|--all|--stale]
set -euo pipefail

# Config centralizzata in hindsight.config.json (vedi hindsight_config.py).
HOOKS_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
export HOOKS_DIR

. "$HOOKS_DIR/../lib/hs-python.sh"

"$HS_PY" - "$@" <<'PY'
import json, os, sys, urllib.request, urllib.error

sys.path.insert(0, os.path.join(os.environ["HOOKS_DIR"], "..", "lib"))
from hindsight_config import load_config, resolve_bank, retain_bank_url

# Config per-progetto: gli hook ricevono CLAUDE_PROJECT_DIR da Claude Code, ma
# questo script gira a mano. Risali dal cwd fino alla prima dir con ".git"
# (dir o file: nei worktree e' un file). Niente `git rev-parse`: su MSYS2
# restituirebbe un path POSIX che il Python Windows non sa aprire.
_d = os.getcwd()
while True:
    if os.path.exists(os.path.join(_d, ".git")):
        os.environ["CLAUDE_PROJECT_DIR"] = _d
        break
    _p = os.path.dirname(_d)
    if _p == _d:
        break
    _d = _p

cfg = load_config()
cwd = os.getcwd()
_core = (cfg.get("bank") or {}).get("core_bank", "")
# _bank resta calcolato (anche con api_url esplicito) per la scelta delle specs
# nel ramo non-esplicito del seed, sotto.
_bank = resolve_bank((cfg.get("bank") or {}).get("retain_bank", "auto"), cfg, cwd)
# retain_bank_url onora la retrocompat api_url esplicito (vedi hindsight_config.py):
# con HINDSIGHT_API_URL o api_url nel config fidato, vince su tutto il blocco bank.
BASE = retain_bank_url(cfg, cwd)


def req(method, path, body=None, timeout=90):
    url = BASE + path
    data = json.dumps(body).encode("utf-8") if body is not None else None
    headers = {"Content-Type": "application/json"} if data is not None else {}
    r = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(r, timeout=timeout) as res:
            raw = res.read().decode("utf-8", errors="replace")
            return json.loads(raw) if raw.strip() else {}
    except urllib.error.HTTPError as e:
        detail = e.read().decode("utf-8", errors="replace")
        print(f"[errore HTTP {e.code}] {method} {path}: {detail}", file=sys.stderr)
        sys.exit(2)
    except urllib.error.URLError as e:
        print(f"[errore rete] {method} {path}: {e.reason} (server up?)", file=sys.stderr)
        sys.exit(3)


def list_models():
    return req("GET", "/mental-models").get("items") or []


cmd = sys.argv[1] if len(sys.argv) > 1 else "list"
args = sys.argv[2:]

if cmd == "list":
    items = list_models()
    if not items:
        print("(nessun mental model — esegui: seed)")
        sys.exit(0)
    for m in items:
        stale = " [STALE]" if m.get("is_stale") else ""
        lr = m.get("last_refreshed_at") or "mai"
        print(f"- {m.get('id')}: {m.get('name', '')}{stale}  (refresh: {lr})")

elif cmd == "show":
    if not args:
        print("uso: show <id>", file=sys.stderr)
        sys.exit(1)
    m = req("GET", f"/mental-models/{args[0]}")
    print(f"# {m.get('name')} ({m.get('id')})")
    print(f"source_query: {m.get('source_query')}")
    print(f"is_stale: {m.get('is_stale')}  |  last_refreshed: {m.get('last_refreshed_at') or 'mai'}")
    print()
    print(m.get("content") or "(contenuto non ancora generato — refresh in corso?)")

elif cmd == "seed":
    existing = {m.get("id") for m in list_models()}
    created = skipped = 0
    # Quali modelli? I modelli CORE vivono nel core; quelli del PROGETTO
    # (project_mental_models) nel bank del progetto. La scelta segue il bank
    # risolto per il cwd (speculare a dove scrivono i fatti via retain_bank).
    # Con api_url esplicito (retrocompat single-bank) i modelli sono sempre i CORE.
    if cfg.get("_api_url_explicit"):
        specs = cfg.get("mental_models", [])
    else:
        specs = cfg.get("mental_models", []) if _bank == _core else cfg.get("project_mental_models", [])
    for spec in specs:
        mid = spec.get("id")
        if not mid or not spec.get("source_query"):
            print(f"! definizione incompleta, salto: {spec}", file=sys.stderr)
            continue
        if mid in existing:
            print(f"= esiste: {mid}")
            skipped += 1
            continue
        body = {
            "id": mid,
            "name": spec.get("name") or mid,
            "source_query": spec["source_query"],
            "tags": spec.get("tags") or [],
            "max_tokens": int(cfg.get("mental_model_max_tokens", 1024)),
            # exclude_mental_models: i mental model NON si nutrono a vicenda (evita il
            # feedback loop in cui un model vuoto/errato ne contamina altri). Leggono
            # solo i fatti reali del bank. Vedi memory mental-model-tag-filter.
            "trigger": {"refresh_after_consolidation": True, "exclude_mental_models": True},
        }
        resp = req("POST", "/mental-models", body)
        op = resp.get("operation_id") or resp.get("id") or "?"
        print(f"+ creato: {mid}  (op/id: {op})")
        created += 1
    print(f"seed: {created} creati, {skipped} gia' presenti")

elif cmd == "refresh":
    target = args[0] if args else "--all"
    if target == "--all":
        ids = [m.get("id") for m in list_models()]
    elif target == "--stale":
        ids = [m.get("id") for m in list_models() if m.get("is_stale")]
    else:
        ids = [target]
    ids = [i for i in ids if i]
    if not ids:
        print("(niente da rinfrescare)")
        sys.exit(0)
    for mid in ids:
        resp = req("POST", f"/mental-models/{mid}/refresh", {})
        op = resp.get("operation_id") or "accepted"
        print(f"~ refresh {mid}: {op}")

else:
    print(f"comando sconosciuto: {cmd}", file=sys.stderr)
    print("uso: seed | list | show <id> | refresh [<id>|--all|--stale]", file=sys.stderr)
    sys.exit(1)
PY
