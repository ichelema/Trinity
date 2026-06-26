#!/usr/bin/env bash
# SessionStart hook — garantisce che il server MCP Hindsight sia avviato E PRONTO
# prima che il client MCP di Claude Code tenti la connessione. Elimina la race
# "tool hindsight/* non registrati perche' il server era ancora in boot".
#
# Flusso:
#   1. se l'endpoint MCP risponde gia' a un initialize valido -> esci subito (caldo)
#   2. se la porta 8888 e' gia' in ascolto (server in boot) -> NON rilanciare, polla
#   3. altrimenti lancia il server (mise run start-hindsight) e polla
#   4. esci SEMPRE 0 entro il budget: l'hook non deve mai bloccare/fallire la sessione
#
# start-hindsight NON e' idempotente (setsid nohup ... senza guardia): percio' il
# rilancio avviene SOLO quando la porta e' libera, per non spawnare un 2o server
# che fallirebbe il bind su :8888 sporcando il log.
set -uo pipefail

MCP_URL="http://localhost:8888/mcp/trinity-project/"
ROOT_URL="http://localhost:8888/"
# Root del plugin derivata dalla posizione dello script (hooks/hindsight/ -> 2 livelli su):
# e' il punto -C per mise, che li' trova il mise.toml con env e task del servizio.
PLUGIN_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
# mise non è nel PATH della bash MSYS → cercalo nel PATH, poi ricadi sul launcher
# sotto la home MSYS dell'utente corrente (il plugin è pensato per Windows+MSYS2).
MISE="$(command -v mise 2>/dev/null || echo "/c/msys64/home/${USERNAME:-}/.local/bin/mise.exe")"
DEADLINE_SECS=25 # budget readiness; l'hook ha timeout 30 in settings.json
POLL_INTERVAL=1

# Esito 0 se l'endpoint MCP accetta un initialize e restituisce serverInfo
# (= il client Claude Code potra' registrare i tool). E' la readiness "vera",
# indipendente dal boot di Postgres che e' piu' lento.
mcp_ready() {
    curl -s -m 3 -X POST "$MCP_URL" \
        -H "Content-Type: application/json" \
        -H "Accept: application/json, text/event-stream" \
        -d '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2024-11-05","capabilities":{},"clientInfo":{"name":"readiness","version":"0"}}}' \
        2> /dev/null | grep -q '"serverInfo"'
}

# Esito 0 se qualcosa e' in ascolto sulla porta (root risponde con http code != 000).
port_listening() {
    local code
    code="$(curl -s -m 1 -o /dev/null -w '%{http_code}' "$ROOT_URL" 2> /dev/null)"
    [ -n "$code" ] && [ "$code" != "000" ]
}

# 1. gia' pronto: esci subito (nessun costo di avvio)
if mcp_ready; then
    exit 0
fi

# 2/3. avvia il server SOLO se la porta e' libera (se occupata, e' gia' in boot)
if ! port_listening; then
    # Trust idempotente: ogni update del plugin cambia il path della copia installata
    # (cache versionata ~/.claude/plugins/cache/...) e mise rifiuterebbe il config.
    "$MISE" trust "$PLUGIN_ROOT/mise.toml" > /dev/null 2>&1 || true
    "$MISE" -C "$PLUGIN_ROOT" run start-hindsight > /dev/null 2>&1 &
    disown 2> /dev/null || true
fi

# 4. polling readiness fino al deadline, poi esci comunque 0
elapsed=0
while [ "$elapsed" -lt "$DEADLINE_SECS" ]; do
    if mcp_ready; then
        exit 0
    fi
    sleep "$POLL_INTERVAL"
    elapsed=$((elapsed + POLL_INTERVAL))
done

exit 0
