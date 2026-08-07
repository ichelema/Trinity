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

# 127.0.0.1 e non localhost: su Windows localhost prova prima IPv6 e costa
# ~0,2s a richiesta (misurato 2026-07-15) — questo probe polla ogni secondo.
MCP_URL="http://127.0.0.1:8888/mcp/trinity-project/"
ROOT_URL="http://127.0.0.1:8888/"
# Root del plugin derivata dalla posizione dello script (hooks/hindsight/ -> 2 livelli su):
# e' il punto -C per mise, che li' trova il mise.toml con env e task del servizio.
PLUGIN_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
# mise non è nel PATH ristretto degli hook → cercalo nel PATH, poi ricadi sul
# launcher standard ~/.local/bin/mise (su MSYS2 risolve da solo il .exe).
MISE="$(command -v mise 2>/dev/null || echo "$HOME/.local/bin/mise")"
# Budget readiness; l'hook ha timeout 50 in hooks.json. Alzato da 25 il 2026-08-07:
# un boot da FREDDO (Postgres embedded incluso) misura ~33s e sforava, lasciando la
# sessione senza MCP anche senza race. Costo: con server irrecuperabile si aspettano
# 45s a vuoto a ogni SessionStart, invece di 25.
DEADLINE_SECS=45
POLL_INTERVAL=1
# Lock anti-race con la sentinella (vedi la guardia in ops/hindsight-stop-services.sh):
# segnala "server in boot" a chi spegne, che uccide per nome processo e colpirebbe
# anche un server non ancora in bind. Scritto da start_server, rimosso a readiness.
START_LOCK="${TMPDIR:-/tmp}/hindsight-starting.lock"

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

start_server() {
    date +%s > "$START_LOCK"
    # Trust idempotente: ogni update del plugin cambia il path della copia installata
    # (cache versionata ~/.claude/plugins/cache/...) e mise rifiuterebbe il config.
    "$MISE" trust "$PLUGIN_ROOT/mise.toml" > /dev/null 2>&1 || true
    "$MISE" -C "$PLUGIN_ROOT" run start-hindsight > /dev/null 2>&1 &
    disown 2> /dev/null || true
}

# 0. sentinella shutdown: guarda il conteggio dei processi claude e spegne i
# servizi quando arriva a 0. Sostituisce l'hook SessionEnd, che Claude Code
# cancella SEMPRE alla chiusura interattiva (issue #32712). Prima del check di
# readiness: deve girare anche sul percorso caldo. Zero fork se e' gia' viva
# (builtin + kill -0); spawn detached altrimenti (pattern msys-background-detach).
SENTINEL_PIDFILE="${TMPDIR:-/tmp}/hindsight-sentinel.pid"
spid=""
[ -f "$SENTINEL_PIDFILE" ] && spid="$(<"$SENTINEL_PIDFILE")"
if [ -z "$spid" ] || ! kill -0 "$spid" 2> /dev/null; then
    setsid nohup bash "$PLUGIN_ROOT/hooks/hindsight/hindsight-sentinel.sh" < /dev/null > /dev/null 2>&1 &
    disown 2> /dev/null || true
fi

# 1. gia' pronto: esci subito (nessun costo di avvio)
if mcp_ready; then
    rm -f "$START_LOCK"
    exit 0
fi

# 2/3. avvia il server SOLO se la porta e' libera (se occupata, e' gia' in boot)
launched=0
if ! port_listening; then
    start_server
    launched=1
fi

# 4. polling readiness fino al deadline, poi esci comunque 0
elapsed=0
while [ "$elapsed" -lt "$DEADLINE_SECS" ]; do
    if mcp_ready; then
        rm -f "$START_LOCK"
        exit 0
    fi
    # Anti-race con lo shutdown detached della sessione precedente: la porta era
    # occupata da un server MORENTE (lo shutdown lo stava per uccidere) e ora e'
    # libera -> il boot che aspettavamo non arrivera' mai: rilancia noi, una sola
    # volta. Il flag launched evita il doppio avvio quando il server l'abbiamo
    # lanciato noi (in boot la porta resta libera qualche secondo e start-hindsight
    # non e' idempotente: un 2o lancio fallirebbe il bind sporcando il log).
    if [ "$launched" -eq 0 ] && ! port_listening; then
        start_server
        launched=1
    fi
    sleep "$POLL_INTERVAL"
    elapsed=$((elapsed + POLL_INTERVAL))
done

exit 0
