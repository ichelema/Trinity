#!/usr/bin/env bash
# Script di setup (NON hook): imposta retain_mission + reflect_mission +
# observations_mission sul bank Hindsight. Idempotente: rieseguibile, sovrascrive
# sempre con i valori del config. Va lanciato una tantum (e di nuovo se il bank
# viene ricreato o se si modificano le mission).
#
# I TESTI DELLE MISSION sono in hindsight.config.json (chiavi retain_mission,
# reflect_mission, observations_mission) — unica source of truth, configurabili da
# lì. Questo script li legge e li applica al bank via PATCH /config.
#
# Config e bank si risolvono dal cwd, come in hindsight-mental-models.sh: dalla root
# di Trinity (o fuori da git) config del plugin e core; dalla directory di un
# progetto la sua hindsight.config.json sopra quella del plugin e il suo bank. I bank
# di progetto creati in automatico nascono senza mission: lancialo dal progetto.
# HINDSIGHT_API_URL forza il bank.
#
# - retain_mission: guida l'LLM estrattore di fatti su COSA salvare da ogni retain.
# - reflect_mission: identita'/persona usata da reflect e dai mental model.
# - observations_mission: guida la CONSOLIDATION (genera gli observation, pipeline
#   separata dall'estrazione). Il prompt di consolidation del server e' in inglese
#   senza direttiva di lingua → senza questa mission gli observation escono in inglese.
#
# Uso: bash hooks/hindsight/ops/hindsight-set-mission.sh
set -euo pipefail

HOOKS_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
export HOOKS_DIR

. "$HOOKS_DIR/../lib/hs-python.sh"

"$HS_PY" <<'PY'
import json, os, sys, urllib.request, urllib.error

sys.path.insert(0, os.path.join(os.environ["HOOKS_DIR"], "..", "lib"))
from hindsight_config import load_config, retain_bank_url

# Lo script gira a mano, senza CLAUDE_PROJECT_DIR: risali dal cwd alla prima dir con
# ".git" (dir o file: nei worktree e' un file), come hindsight-mental-models.sh.
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
api_url = retain_bank_url(cfg, os.getcwd())

missions = {k: cfg.get(k) for k in ("retain_mission", "reflect_mission", "observations_mission")}
missing = [k for k, v in missions.items() if not v]
if missing:
    print(f"[set-mission] ERRORE: mission mancanti nel config: {missing}", file=sys.stderr)
    sys.exit(1)

req = urllib.request.Request(
    api_url + "/config",
    data=json.dumps({"updates": missions}).encode("utf-8"),
    headers={"Content-Type": "application/json"},
    method="PATCH",
)
try:
    with urllib.request.urlopen(req, timeout=15) as res:
        body = json.loads(res.read().decode("utf-8", errors="replace"))
except urllib.error.HTTPError as e:
    print(f"[set-mission] HTTP {e.code}: {e.read().decode('utf-8', 'replace')[:300]}", file=sys.stderr)
    sys.exit(1)
except Exception as exc:
    print(f"[set-mission] FAIL {exc}", file=sys.stderr)
    sys.exit(1)

c = body.get("config", {})
applied = {k: len(c.get(k) or "") for k in missions}
if not all(applied.values()):
    print(f"[set-mission] ERRORE: la config non riporta tutte le mission impostate: {applied}", file=sys.stderr)
    sys.exit(1)
print(f"[set-mission] OK — bank {api_url.rstrip('/').rsplit('/', 1)[-1]}, mission applicate dal config: " + ", ".join(f"{k} ({n} char)" for k, n in applied.items()))
PY
