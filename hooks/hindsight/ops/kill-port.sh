#!/usr/bin/env bash
# Termina il processo (nativo Windows) in ascolto su una porta TCP.
# Usato dai task mise stop-control-plane (:9999) e stop-dashboard (:9292).
#
# Perche' PowerShell e non lsof/netstat: Control Plane (Node) e dashboard (Ruby/Puma)
# sono processi nativi Windows; il netstat di MSYS2 non vede sempre le loro porte,
# mentre Get-NetTCPConnection le risolve in modo affidabile con il PID owner.
#
# Uso: kill-port.sh <porta> [etichetta]
set -euo pipefail

PORT="${1:?Uso: kill-port.sh <porta> [etichetta]}"
LABEL="${2:-porta $PORT}"
# pwsh non è nel PATH MSYS: cercalo, poi ricadi sull'install standard di PowerShell 7.
PWSH="$(command -v pwsh 2>/dev/null || echo "/c/Program Files/PowerShell/7/pwsh.exe")"

# Lista dei PID in ascolto (LISTEN) sulla porta, deduplicati. tr -d '\r' per il CRLF di pwsh.
PIDS=$("$PWSH" -NoProfile -Command \
	"Get-NetTCPConnection -LocalPort $PORT -State Listen -ErrorAction SilentlyContinue | Select-Object -ExpandProperty OwningProcess -Unique" \
	2>/dev/null | tr -d '\r' | tr -d ' ')

if [ -z "$PIDS" ]; then
	echo "[$LABEL] nessun processo in ascolto su :$PORT"
	exit 0
fi

for pid in $PIDS; do
	if "$PWSH" -NoProfile -Command "Stop-Process -Id $pid -Force -ErrorAction Stop" 2>/dev/null; then
		echo "[$LABEL] terminato PID $pid (porta :$PORT)"
	else
		echo "[$LABEL] impossibile terminare PID $pid" >&2
	fi
done
