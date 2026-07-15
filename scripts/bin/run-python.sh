#!/usr/bin/env bash
# Lancia il Python risolto da hs-python.sh (PATH -> mise -> fallback), con
# PYTHONUTF8=1 gia' esportato. Usato dai server MCP in .mcp.json: il loro PATH
# puo' non contenere python, e su Linux spesso esiste solo python3.
set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
. "$SCRIPT_DIR/../../hooks/hindsight/lib/hs-python.sh"

exec "$HS_PY" "$@"
