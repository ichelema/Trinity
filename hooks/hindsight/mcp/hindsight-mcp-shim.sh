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
#      (hindsight_config.resolve_bank: slug dal remote origin, fallback
#      basename; repo Trinity o fuori-git → core trinity-project). Il cwd di
#      riferimento è CLAUDE_PROJECT_DIR, che Claude Code passa nell'env di
#      ogni server MCP stdio. Se python/resolve falliscono → fallback core
#      (degradazione sicura, mai crash).
#   2. attende che il server Hindsight sia pronto (ad avviarlo ci pensa l'hook
#      SessionStart hindsight-ensure-up.sh; qui solo polling readiness).
#   3. exec del bridge stdio↔streamable-HTTP (mcp-remote sul node di mise)
#      verso http://127.0.0.1:8888/mcp/<bank>/.
set -uo pipefail

PLUGIN_DIR="${TRINITY_PLUGIN_DIR:-E:/AI/Claude/Trinity}"
LIB="$PLUGIN_DIR/hooks/hindsight/lib"
# Node di mise: stessa convenzione (path versionato cablato) del .mcp.json
# di progetto (playwright/excalidraw). Se aggiorni node in mise, aggiorna qui.
NODE="${HOME:-E:/msys64/home/Sphynx}/.local/share/mise/installs/node/24.16.0/node.exe"
PROXY="${HOME:-E:/msys64/home/Sphynx}/.local/share/mise/installs/node/24.16.0/node_modules/mcp-remote/dist/proxy.js"

# 1) bank per-progetto — riusa resolve_bank() degli hook (unica fonte di verità)
BANK="$(PYTHONUTF8=1 python -c "
import sys
sys.path.insert(0, r'$LIB')
from hindsight_config import load_config, resolve_bank
cfg = load_config()
print(resolve_bank((cfg.get('bank') or {}).get('retain_bank', 'core'), cfg))
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
