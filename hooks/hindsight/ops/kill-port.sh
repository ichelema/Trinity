#!/usr/bin/env bash
# Termina il processo (nativo Windows) in ascolto su una porta TCP.
# Usato dal task mise stop-control-plane (:9999).
#
# Perche' PowerShell e non lsof/netstat: il Control Plane (Node) e' un processo
# nativo Windows; il netstat di MSYS2 non vede sempre la sua porta, mentre
# Get-NetTCPConnection la risolve in modo affidabile con il PID owner.
#
# Uso: kill-port.sh <porta> [etichetta]
set -euo pipefail

PORT="${1:?Uso: kill-port.sh <porta> [etichetta]}"
LABEL="${2:-porta $PORT}"

# Linux/macOS: lsof (fallback fuser) al posto di pwsh; poi esce.
case "$(uname -s)" in
MINGW* | MSYS* | CYGWIN*) ;; # ramo Windows sotto
*)
	PIDS="$(lsof -ti tcp:"$PORT" -sTCP:LISTEN 2>/dev/null || true)"
	if [ -z "$PIDS" ] && command -v fuser >/dev/null 2>&1; then
		PIDS="$(fuser -n tcp "$PORT" 2>/dev/null | tr -s ' ' '\n' || true)"
	fi
	if [ -z "$PIDS" ]; then
		echo "[$LABEL] nessun processo in ascolto su :$PORT"
		exit 0
	fi
	for pid in $PIDS; do
		if kill "$pid" 2>/dev/null; then
			echo "[$LABEL] terminato PID $pid (porta :$PORT)"
		else
			echo "[$LABEL] impossibile terminare PID $pid" >&2
		fi
	done
	exit 0
	;;
esac

# pwsh non è nel PATH MSYS: cercalo, poi ricadi sull'install standard di PowerShell 7.
PWSH="$(command -v pwsh 2>/dev/null || echo "/c/Program Files/PowerShell/7/pwsh.exe")"

# Lista dei PID in ascolto (LISTEN) sulla porta, deduplicati. tr -d '\r' per il CRLF di pwsh.
# || true: Get-NetTCPConnection esce 1 quando la porta è libera (nessuna connessione),
# e con set -euo pipefail abortirebbe prima del guard "porta vuota" qui sotto.
PIDS=$("$PWSH" -NoProfile -Command \
	"Get-NetTCPConnection -LocalPort $PORT -State Listen -ErrorAction SilentlyContinue | Select-Object -ExpandProperty OwningProcess -Unique" \
	2>/dev/null | tr -d '\r' | tr -d ' ' || true)

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
