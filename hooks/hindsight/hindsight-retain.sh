#!/usr/bin/env bash
# Stop hook (async:true in settings.json): salva un riassunto strutturato del turno
# appena completato in Hindsight. Non blocca nulla perche' eseguito in background da
# Claude Code; ha timeout 60s in settings.json. La POST e' async:true sul server,
# quindi anche internamente non aspetta l'estrazione LLM dei fatti.
set -uo pipefail

export HOOK_INPUT="$(cat)"
# API_URL e tutti gli altri parametri sono in hindsight.config.json (li carica il
# worker via hindsight_config.py). HINDSIGHT_API_URL resta come override opzionale.

# Path del worker relativo a questo script (robusto a spostamenti della cartella).
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
python "$SCRIPT_DIR/hindsight-retain-worker.py" >/tmp/hs-retain.log 2>&1
exit 0
