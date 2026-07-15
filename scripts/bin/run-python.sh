#!/usr/bin/env bash
# Lancia il Python DI MISE (risolto a runtime), con PYTHONUTF8=1. Usato dai
# server MCP in .mcp.json: serve proprio il python di mise — e' li' che sono
# pip-installati i pacchetti dei server (es. truststore per notebooklm) — non
# un python qualsiasi del PATH (il python MSYS ne e' privo).
set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

_mise="$(command -v mise 2>/dev/null || echo "$HOME/.local/bin/mise")"
PY="$("$_mise" which python 2>/dev/null | tr -d '\r' | tr '\\' '/' || true)"
if [ -z "$PY" ] || [ ! -x "$PY" ]; then
	# Fallback: la catena generica di hs-python.sh (PATH -> ucrt64 -> "python").
	. "$SCRIPT_DIR/../../hooks/hindsight/lib/hs-python.sh"
	PY="$HS_PY"
fi

export PYTHONUTF8=1
exec "$PY" "$@"
