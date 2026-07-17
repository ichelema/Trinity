#!/usr/bin/env bash
# Shim MCP stdio→HTTP: bank Hindsight per-progetto (registrato a scope user).
#
# Claude Code avvia questo shim in OGNI progetto: è l'unica definizione del
# server "hindsight" (la entry statica nel .mcp.json di Trinity è stata rimossa
# il 2026-07-10 — due scope con lo stesso nome generavano il warning
# "Conflicting scopes"). In Trinity la risoluzione dà comunque il core
# trinity-project, altrove il bank del progetto.
#
# Flusso:
#   1. risolve il bank con la STESSA logica multibank degli hook REST
#      (hindsight_config.resolve_bank: nome = slug dal remote origin, fallback
#      basename; fuori-git o repo con la stessa identità canonica del remote
#      del plugin → core trinity-project), percent-encodato per l'URL. Il cwd
#      di riferimento è CLAUDE_PROJECT_DIR, che Claude Code passa nell'env di
#      ogni server MCP stdio. Se python/resolve falliscono → fallback core
#      (degradazione sicura, mai crash).
#   2. attende che il server Hindsight sia pronto (ad avviarlo ci pensa l'hook
#      SessionStart hindsight-ensure-up.sh; qui solo polling readiness).
#   3. exec del bridge stdio↔streamable-HTTP (mcp-remote sul node di mise)
#      verso http://127.0.0.1:8888/mcp/<bank>/.
set -uo pipefail

# Root del plugin: env esplicita, altrimenti derivata dalla posizione dello
# script (mcp/ -> 3 livelli su), come gli altri hook. Niente fallback E:/.
SHIM_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PLUGIN_DIR="${TRINITY_PLUGIN_DIR:-$(cd "$SHIM_DIR/../../.." && pwd)}"
LIB="$PLUGIN_DIR/hooks/hindsight/lib"

# Node risolto a runtime (niente path versionato cablato): prima il binario
# reale via mise (which), poi il PATH. tr: mise su Windows stampa backslash.
_mise="$(command -v mise 2>/dev/null || echo "$HOME/.local/bin/mise")"
NODE="$("$_mise" which node 2>/dev/null | tr -d '\r' | tr '\\' '/' || true)"
{ [ -n "$NODE" ] && [ -x "$NODE" ]; } || NODE="$(command -v node 2>/dev/null || true)"
if [ -z "$NODE" ]; then
	echo "[hindsight-mcp-shim] node non trovato (mise/PATH): impossibile avviare mcp-remote" >&2
	exit 1
fi

# mcp-remote (npm install -g): il layout dei global module differisce per OS —
# Windows: <prefix>/node_modules/...   Linux/mac: <prefix>/lib/node_modules/...
NODE_DIR="$(dirname "$NODE")"
PROXY=""
for _cand in \
	"$NODE_DIR/node_modules/mcp-remote/dist/proxy.js" \
	"$NODE_DIR/../node_modules/mcp-remote/dist/proxy.js" \
	"$NODE_DIR/../lib/node_modules/mcp-remote/dist/proxy.js"; do
	if [ -f "$_cand" ]; then
		PROXY="$_cand"
		break
	fi
done
if [ -z "$PROXY" ]; then
	echo "[hindsight-mcp-shim] mcp-remote non trovato accanto a $NODE: esegui 'npm install -g mcp-remote'" >&2
	exit 1
fi

# 1) bank per-progetto — riusa resolve_bank() degli hook (unica fonte di verità)
# Interprete via hs-python.sh (su molte distro esiste solo python3: il comando
# nudo `python` degraderebbe in silenzio al bank core).
[ -f "$LIB/hs-python.sh" ] && . "$LIB/hs-python.sh"
: "${HS_PY:=python}"
BANK="$(PYTHONUTF8=1 "$HS_PY" -c "
import sys, urllib.parse
sys.path.insert(0, r'$LIB')
from hindsight_config import load_config, resolve_bank
cfg = load_config()
# percent-encode: lo slug finisce in un path URL (spazi/accenti/'?' lo romperebbero)
print(urllib.parse.quote(resolve_bank((cfg.get('bank') or {}).get('retain_bank', 'core'), cfg), safe=''))
" 2>/dev/null | tr -d '\r')"
[ -n "$BANK" ] || BANK="trinity-project"

MCP_URL="http://127.0.0.1:8888/mcp/${BANK}/"

# 2) readiness: initialize accettato (stesso probe di hindsight-ensure-up.sh).
#    Dopo il deadline prosegui comunque: mcp-remote ritenta da sé.
mcp_ready() {
	curl -s -m 3 -X POST "$MCP_URL" \
		-H "Content-Type: application/json" \
		-H "Accept: application/json, text/event-stream" \
		-d '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2024-11-05","capabilities":{},"clientInfo":{"name":"shim-readiness","version":"0"}}}' \
		2>/dev/null | grep -q '"serverInfo"'
}
elapsed=0
until mcp_ready; do
	[ "$elapsed" -ge 20 ] && break
	sleep 1
	elapsed=$((elapsed + 1))
done

# 3) bridge stdio↔HTTP (--allow-http: endpoint locale non-TLS)
exec "$NODE" "$PROXY" "$MCP_URL" --allow-http
