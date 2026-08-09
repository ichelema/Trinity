#!/usr/bin/env bash
#
# cp-check-scheduled.sh — Wrapper per esecuzione NON interattiva (System Scheduler).
#
# Viene invocato dal launcher cp-check-scheduled.cmd via `bash -lc`, quindi gira
# già dentro MSYS2 UCRT64. Esegue `mise run cp-check`, registra l'esito in
# logs/cp-check-scheduled.log e, se su npm è uscita una release nuova del
# Control Plane, lascia un file di alert ben visibile (e lo apre).
#
# Exit:  0  = nessuna novità   |   10 = update disponibile   |   altro = errore

set -uo pipefail

PROJ="${TRINITY_PLUGIN_DIR:-$(cd "$(dirname "${BASH_SOURCE[0]:-$0}")/../.." && pwd)}"
MISE="$(command -v mise 2>/dev/null || echo "$HOME/.local/bin/mise")"

cd "$PROJ" || {
	echo "cp-check-scheduled: cd $PROJ fallito" >&2
	exit 1
}

# Log/alert accanto allo script, in scheduler/check_update_hindsight_control_plane/
LOGDIR="$PROJ/scheduler/check_update_hindsight_control_plane"
mkdir -p "$LOGDIR"
LOG="$LOGDIR/cp-check-scheduled.log"
ALERT="$LOGDIR/cp-update-ALERT.txt"
TS="$(date '+%Y-%m-%d %H:%M:%S')"
CMD_EXE="/c/Windows/System32/cmd.exe"
NOTEPAD_EXE="/c/Windows/System32/notepad.exe"

# mise rifiuta un config non "trusted" e non lo parsa: da un terminale/scheduler
# Windows "nudo" il .mise.toml risulta non fidato (il trust è per contesto utente).
# Lo ri-fidiamo a ogni run — è il nostro config, l'operazione è idempotente e
# sopravvive a ogni sua modifica futura (che altrimenti invaliderebbe il trust).
"$MISE" trust "$PROJ/mise.toml" >>"$LOG" 2>&1 || true

# cp-check esce con 10 se c'è un aggiornamento; cattura tutto l'output (JSON + righe di mise).
OUT="$("$MISE" run cp-check 2>>"$LOG")"
RC=$?

# Log su una riga (tr -d '\r' per il quirk CRLF di MSYS).
printf '[%s] rc=%s %s\n' "$TS" "$RC" "$OUT" | tr -d '\r' >>"$LOG"

if [[ "$RC" -eq 10 ]]; then
	# Estrai le versioni dal JSON senza jq (evita il quirk named-capture/CRLF su MSYS).
	latest="$(printf '%s' "$OUT" | grep -oE '"latest"[^,]*' | grep -oE '[0-9]+\.[0-9]+\.[0-9]+' | head -1)"
	last_seen="$(printf '%s' "$OUT" | grep -oE '"last_seen"[^,]*' | grep -oE '[0-9]+\.[0-9]+\.[0-9]+' | head -1)"
	{
		echo "Control Plane Hindsight — NUOVA RELEASE SU NPM"
		echo
		echo "  ultima vista:  ${last_seen:-?}"
		echo "  ultima su npm: ${latest:-?}"
		echo "  rilevato il:   $TS"
		echo
		echo "Il task control-plane è sempre-latest via npx: al prossimo avvio userà"
		echo "da solo la ${latest:-nuova versione}. Prossimi passi consigliati:"
		echo "  1. leggi i breaking changes della release su GitHub (vectorize-io/hindsight)"
		echo "  2. valuta 'mise run install-hindsight' per allineare hindsight-api-slim"
	} >"$ALERT"

    WIN_ALERT="$(command -v cygpath >/dev/null 2>&1 && cygpath -aw "$ALERT" || printf '%s' "$ALERT")"

    # System Scheduler gira nella sessione utente: apri l'alert in primo piano.
    # CP_NO_OPEN=1 disabilita l'apertura (utile per i test).
	if [[ "${CP_NO_OPEN:-0}" != "1" && -x "$NOTEPAD_EXE" ]]; then
        "$NOTEPAD_EXE" "$WIN_ALERT" >>"$LOG" 2>&1 &
	fi
	exit 10

fi

# Nessun update (o errore): togli un eventuale alert vecchio per non confondere.
if [[ "$RC" -eq 0 ]]; then
	rm -f "$ALERT"
fi

exit "$RC"
