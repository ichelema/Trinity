#!/usr/bin/env bash
# Hook SessionEnd: alla VERA chiusura della sessione Claude Code fa il retain finale
# e poi ferma TUTTO ció che start-hindsight lascia attivo (per design i processi sono
# detached e sopravvivono alla chiusura: vedi memoria msys-background-detach):
#   - server MCP: launcher hindsight-local-mcp.exe + il suo python figlio (porta 8888, ~1.5GB)
#   - Postgres embedded del bank (porta 5432, master + worker)
#
# IMPORTANTE: SessionEnd scatta anche su /clear (reason=clear) — in quel caso la sessione
# continua e NON dobbiamo spegnere i servizi. Filtriamo sul campo `reason` dello stdin.
#
# Nota: `mise run stop-hindsight` da solo è insufficiente (taskkill //IM senza //T lascia
# orfano il python figlio e non tocca Postgres); qui usiamo //T + pg_ctl stop pulito.
set -uo pipefail

INPUT="$(cat)"
REASON="$(printf '%s' "$INPUT" | jq -r '.reason // "other"' 2>/dev/null | tr -d '\r')"

# /clear (e affini non-terminali): la sessione prosegue → non spegnere nulla.
case "$REASON" in
clear) exit 0 ;;
esac

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SESS_DIR="/tmp/hs-sessions"
SESSION_ID="$(printf '%s' "$INPUT" | jq -r '.session_id // empty' 2>/dev/null | tr -d '\r')"
SESSION_ID="${SESSION_ID//\//_}"

# 1) Retain finale forzato: cattura la coda della sessione prima di spegnere il server.
printf '%s' "$INPUT" | HS_RETAIN_FORCE=1 bash "$SCRIPT_DIR/hindsight-retain.sh" >/dev/null 2>&1 || true

# 2) Reference counting: rimuovi il lease di QUESTA sessione, poi garbage-collect dei
#    lease orfani (sessioni crashate senza SessionEnd) piu' vecchi di 12h (720 min).
[ -n "$SESSION_ID" ] && rm -f "$SESS_DIR/$SESSION_ID" 2>/dev/null
[ -d "$SESS_DIR" ] && find "$SESS_DIR" -type f -mmin +720 -delete 2>/dev/null || true

# 3) Se restano altre sessioni Claude Code attive, NON spegnere: il server e' condiviso.
#    Esci subito (niente sleep) cosi' la chiusura di questa sessione e' immediata.
REMAINING=0
[ -d "$SESS_DIR" ] && REMAINING="$(find "$SESS_DIR" -type f 2>/dev/null | wc -l | tr -d ' ')"
if [ "${REMAINING:-0}" -gt 0 ]; then
	exit 0
fi

# 4) Ultima sessione attiva: dai al worker async il tempo di estrarre i fatti del retain
#    finale (gpt-4.1-nano ~4.5s; margine prudenziale) PRIMA di uccidere il server, poi
#    ferma server (launcher + python figlio) e Postgres embedded. Logica condivisa con
#    il task `mise run stop-hindsight` → punto unico di manutenzione.
sleep 7
bash "$SCRIPT_DIR/ops/hindsight-stop-services.sh"

exit 0
