#!/usr/bin/env bash
# Verifica: /trinity:ponytail:ponytail senza argomento riattiva la modalità dopo un off.
set -euo pipefail
dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
tmp="$(mktemp -d)"; trap 'rm -rf "$tmp"' EXIT
# lua nativo su Windows non capisce i path /tmp/...: convertili se c'è cygpath
export CLAUDE_CONFIG_DIR="$(cygpath -m "$tmp" 2>/dev/null || echo "$tmp")" PONYTAIL_DEFAULT_MODE=full
run() { printf '{"prompt":"%s"}' "$1" | lua "$dir/ponytail-mode-tracker.lua" >/dev/null; }
run "/trinity:ponytail:ponytail off"
[ ! -f "$tmp/.ponytail-active" ] || { echo "FAIL: off non ha spento"; exit 1; }
run "/trinity:ponytail:ponytail"
[ "$(cat "$tmp/.ponytail-active")" = full ] || { echo "FAIL: senza argomento non riattiva"; exit 1; }
echo PASS
