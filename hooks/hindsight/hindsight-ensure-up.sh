#!/usr/bin/env bash
# SessionStart hook — aspetta che il server MCP Hindsight sia PRONTO prima che il
# client MCP di Claude Code tenti la connessione (niente race "tool non registrati").
# Il server gira SOLO sulla VPS (systemd --user). Sui PC HINDSIGHT_SSH_TUNNEL=<host ssh>
# apre il tunnel verso la VPS; sulla VPS la variabile non c'e' e si attende solo la
# readiness. Nessun avvio locale, per scelta: le memorie non devono dividersi tra macchine.
# Esce SEMPRE 0: non deve mai bloccare/fallire la sessione.
set -uo pipefail

# 127.0.0.1 e non localhost: su Windows localhost prova prima IPv6 (~0,2s a richiesta).
MCP_URL="http://127.0.0.1:8888/mcp/trinity-project/"
# Scadenza ben sotto il timeout 50 di hooks.json: ogni probe dura al massimo 2s.
DEADLINE_SECS=40

# Esito 0 se l'endpoint MCP accetta un initialize e restituisce serverInfo.
mcp_ready() {
    curl -s -m 2 -X POST "$MCP_URL" \
        -H "Content-Type: application/json" \
        -H "Accept: application/json, text/event-stream" \
        -d '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2024-11-05","capabilities":{},"clientInfo":{"name":"readiness","version":"0"}}}' \
        2> /dev/null | grep -q '"serverInfo"'
}

mcp_ready && exit 0

if [ -n "${HINDSIGHT_SSH_TUNNEL:-}" ]; then
    # Sempre, senza guardare se la porta e' occupata: se lo e' (tunnel stantio o
    # altro processo) ExitOnForwardFailure fa uscire ssh e sotto scatta l'avviso.
    # Bind espliciti su 127.0.0.1: senza, GatewayPorts=yes in ssh_config
    # esporrebbe le porte in LAN (il Control Plane non ha autenticazione).
    # setsid nohup e non ssh -f: su MSYS il figlio verrebbe reaped all'uscita dell'hook.
    setsid nohup ssh -N -o BatchMode=yes -o ExitOnForwardFailure=yes \
        -o ConnectTimeout=10 -o ServerAliveInterval=30 -o ServerAliveCountMax=3 \
        -L 127.0.0.1:8888:127.0.0.1:8888 -L 127.0.0.1:9999:localhost:9999 \
        "$HINDSIGHT_SSH_TUNNEL" < /dev/null > /dev/null 2>&1 &
    disown 2> /dev/null || true
fi

while [ "$SECONDS" -lt "$DEADLINE_SECS" ]; do
    sleep 1
    mcp_ready && exit 0
done

echo "Hindsight non raggiungibile (tunnel: ${HINDSIGHT_SSH_TUNNEL:-nessuno}): tool hindsight/* non disponibili in questa sessione. Se la porta 8888 e' occupata da un altro processo, chiudilo."
exit 0
