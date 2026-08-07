#!/usr/bin/env bash
# Ferma i servizi Hindsight lasciati attivi (detached) da start-hindsight:
#   - server MCP: launcher hindsight-local-mcp.exe + il suo python figlio (porta 8888, ~1.5GB)
#   - Postgres embedded del bank (porta 5432, master + worker)
#
# Punto UNICO della logica di stop, condiviso da:
#   - task `mise run stop-hindsight`
#   - sentinella hindsight-sentinel.sh, che prima drena i retain pendenti
# NON fa retain: è solo lo stop dei processi.
set -uo pipefail

# Guardia anti-race col boot: sotto si uccide per NOME PROCESSO (taskkill //IM su
# Windows, pkill -f su Linux), quindi si colpirebbe anche un server ancora in boot
# — nessun bind su :8888, invisibile a un check per porta — appena lanciato da una
# sessione nuova. hindsight-ensure-up.sh scrive questo lock prima di lanciarlo e lo
# rimuove a readiness. Exit 1 = stop abortito: la sentinella lo legge e torna a
# dormire invece di terminare, restando a sorvegliare la sessione entrante.
START_LOCK="${TMPDIR:-/tmp}/hindsight-starting.lock"
if [ -f "$START_LOCK" ]; then
	_ts="$(<"$START_LOCK")"
	_ts="${_ts//[!0-9]/}"
	_age=$(($(date +%s) - ${_ts:-0}))
	if [ "$_age" -lt 60 ]; then
		echo "[hindsight-stop] avvio in corso da ${_age}s: stop abortito (rm $START_LOCK per forzare)" >&2
		exit 1
	fi
	rm -f "$START_LOCK" # lock stantio: l'avvio e' fallito, procedi
fi

case "$(uname -s)" in
MINGW* | MSYS* | CYGWIN*)
	TASKKILL="/c/Windows/System32/taskkill.exe"
	# Postgres embedded sotto il profilo LOCALE (.pg0). pg0.exe usa LOCALAPPDATA come
	# base (C:\Users\<user>\AppData\Local → risaliamo di 2 livelli per la home).
	# HOMEDRIVE/HOMEPATH punta al drive di rete (V:\) su PC aziendali ENINET e NON
	# contiene .pg0 → pg_ctl non veniva trovato e Postgres era ucciso dal taskkill
	# senza arresto pulito, causando WAL recovery lento (o crash pg0) al riavvio.
	if [ -n "${LOCALAPPDATA:-}" ]; then
		_local="$(cygpath -u "$LOCALAPPDATA")"
		WINHOME_U="$(cd "$_local/../.." && pwd)"
		WINHOME_M="$(cygpath -m "$WINHOME_U")"
	else
		WINHOME_U="$(cygpath -u "$HOMEDRIVE$HOMEPATH")"
		WINHOME_M="$(cygpath -m "$HOMEDRIVE$HOMEPATH")"
	fi
	PG_CTL="$(ls "$WINHOME_U"/.pg0/installation/*/bin/pg_ctl.exe 2>/dev/null | sort -V | tail -1)"
	PGDATA="$WINHOME_M/.pg0/instances/hindsight-mcp/data"

	# Server MCP: //T per portare giù anche il python figlio (senza //T resterebbe orfano).
	# Path ASSOLUTO perché nella bash MSYS `taskkill` non è nel PATH.
	"$TASKKILL" //F //T //IM hindsight-local-mcp.exe >/dev/null 2>&1 || true

	# Postgres embedded: stop PULITO (evita recovery/corruzione al riavvio).
	if [ -x "$PG_CTL" ]; then
		"$PG_CTL" -D "$PGDATA" stop -m fast -w -t 15 >/dev/null 2>&1 || true
	fi
	;;
*)
	# Linux/macOS: launcher + python figlio condividono il nome nel cmdline;
	# il cluster pg0 sta sotto $HOME su filesystem nativo (niente junction).
	# HS_PGDATA permette di puntare a un datadir alternativo.
	pkill -TERM -f hindsight-local-mcp >/dev/null 2>&1 || true
	PG_CTL="$(ls "$HOME"/.pg0/installation/*/bin/pg_ctl 2>/dev/null | sort -V | tail -1)"
	PGDATA="${HS_PGDATA:-$HOME/.pg0/instances/hindsight-mcp/data}"

	# Postgres embedded: stop PULITO (evita recovery/corruzione al riavvio).
	if [ -x "$PG_CTL" ] && [ -d "$PGDATA" ]; then
		"$PG_CTL" -D "$PGDATA" stop -m fast -w -t 15 >/dev/null 2>&1 || true
	fi
	;;
esac

exit 0
