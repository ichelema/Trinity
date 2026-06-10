#!/usr/bin/env bash
# Ferma i servizi Hindsight lasciati attivi (detached) da start-hindsight:
#   - server MCP: launcher hindsight-local-mcp.exe + il suo python figlio (porta 8888, ~1.5GB)
#   - Postgres embedded del bank (porta 5432, master + worker)
#
# Punto UNICO della logica di stop, condiviso da:
#   - task `mise run stop-hindsight`
#   - hook SessionEnd (hindsight-shutdown.sh), che prima fa il retain finale
# NON fa retain: è solo lo stop dei processi.
set -uo pipefail

TASKKILL="/c/Windows/System32/taskkill.exe"
PG_CTL="/c/Users/EN27553/.pg0/installation/18.1.0/bin/pg_ctl.exe"
PGDATA="C:/Users/EN27553/.pg0/instances/hindsight-mcp/data"

# Server MCP: //T per portare giù anche il python figlio (senza //T resterebbe orfano).
# Path ASSOLUTO perché nella bash MSYS `taskkill` non è nel PATH.
"$TASKKILL" //F //T //IM hindsight-local-mcp.exe >/dev/null 2>&1 || true

# Postgres embedded: stop PULITO (evita recovery/corruzione al riavvio).
if [ -x "$PG_CTL" ]; then
	"$PG_CTL" -D "$PGDATA" stop -m fast -w -t 15 >/dev/null 2>&1 || true
fi

exit 0
