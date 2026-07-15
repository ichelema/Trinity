#!/usr/bin/env bash
# Lancia il Node di mise risolvendolo A RUNTIME (niente path versionati cablati).
# Usato dai server MCP in .mcp.json: il loro PATH puo' non contenere node.
#
# Uso: run-node.sh [npm:<modulo/percorso.js>] [args...]
#   npm:X = risolve X dentro i node_modules GLOBALI del node trovato, gestendo
#   i layout diversi per OS (Windows: <prefix>/node_modules; Linux/mac:
#   <prefix>/lib/node_modules) — es. npm:@playwright/mcp/cli.js
set -uo pipefail

_mise="$(command -v mise 2>/dev/null || echo "$HOME/.local/bin/mise")"
NODE="$("$_mise" which node 2>/dev/null | tr -d '\r' | tr '\\' '/' || true)"
{ [ -n "$NODE" ] && [ -x "$NODE" ]; } || NODE="$(command -v node 2>/dev/null || true)"
if [ -z "$NODE" ]; then
	echo "[run-node] node non trovato (mise/PATH)" >&2
	exit 1
fi

if [ "${1#npm:}" != "${1:-}" ]; then
	_mod="${1#npm:}"
	shift
	NODE_DIR="$(dirname "$NODE")"
	_resolved=""
	for _cand in \
		"$NODE_DIR/node_modules/$_mod" \
		"$NODE_DIR/../node_modules/$_mod" \
		"$NODE_DIR/../lib/node_modules/$_mod"; do
		if [ -f "$_cand" ]; then
			_resolved="$_cand"
			break
		fi
	done
	if [ -z "$_resolved" ]; then
		echo "[run-node] modulo globale non trovato: $_mod (npm install -g?)" >&2
		exit 1
	fi
	set -- "$_resolved" "$@"
fi

exec "$NODE" "$@"
