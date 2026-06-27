#!/usr/bin/env bash
#
# api-check-scheduled.sh — Wrapper per esecuzione NON interattiva (System Scheduler).
#
# Viene invocato dal launcher api-check-scheduled.cmd via login shell, quindi gira
# già dentro MSYS2 UCRT64. Esegue `mise run api-check`, registra l'esito in
# logs/api-check-scheduled.log e, se è uscita una versione di hindsight-api o
# hindsight-api-slim più recente di quella installata, lascia un file di alert ben
# visibile (e lo apre).
#
# Exit:  0  = nessuna novità   |   10 = update disponibile   |   altro = errore

set -uo pipefail

PROJ="${TRINITY_PLUGIN_DIR:-$(cd "$(dirname "${BASH_SOURCE[0]:-$0}")/../.." && pwd)}"
MISE="$(command -v mise 2>/dev/null || echo "/e/msys64/home/Sphynx/.local/bin/mise.exe")"

cd "$PROJ" || {
	echo "api-check-scheduled: cd $PROJ fallito" >&2
	exit 1
}

# Log/alert accanto allo script, in scheduler/check_update_hindsight_api/
LOGDIR="$PROJ/scheduler/check_update_hindsight_api"
mkdir -p "$LOGDIR"
LOG="$LOGDIR/api-check-scheduled.log"
ALERT="$LOGDIR/api-update-ALERT.txt"
TS="$(date '+%Y-%m-%d %H:%M:%S')"
NOTEPAD_EXE="/c/Windows/System32/notepad.exe"

# mise rifiuta un config non "trusted" e non lo parsa: da un terminale/scheduler
# Windows "nudo" il .mise.toml risulta non fidato (il trust è per contesto utente).
# Lo ri-fidiamo a ogni run — è il nostro config, l'operazione è idempotente e
# sopravvive a ogni sua modifica futura (che altrimenti invaliderebbe il trust).
"$MISE" trust "$PROJ/mise.toml" >>"$LOG" 2>&1 || true

# api-check esce con 10 se c'è un aggiornamento; cattura tutto l'output (JSON + righe di mise).
OUT="$("$MISE" run api-check 2>>"$LOG")"
RC=$?

# Log su una riga (tr -d '\r' per il quirk CRLF di MSYS).
printf '[%s] rc=%s %s\n' "$TS" "$RC" "$OUT" | tr -d '\r' >>"$LOG"

if [[ "$RC" -eq 10 || "${API_FORCE_ALERT:-0}" == "1" ]]; then
	{
		echo "hindsight-api / hindsight-api-slim — NUOVA VERSIONE DISPONIBILE"
		echo
		echo "  rilevato il: $TS"
		echo
		echo "Dettaglio (installed vs latest su PyPI):"
		# Stampa le triplette package/installed/latest dal JSON, senza jq (quirk CRLF su MSYS).
		printf '%s\n' "$OUT" | tr -d '\r' |
			grep -oE '"(package|installed|latest)"[^,}]*' |
			sed 's/^/    /'
		echo
		echo "Prossimo passo — aggiorna entrambi i pacchetti:"
		echo "    mise -C \"\$TRINITY_PLUGIN_DIR\" run install-hindsight"
		echo
		echo "(install-hindsight fa: pip install --upgrade hindsight-api. Dalla 0.7.1 il"
		echo " provider ZeroEntropy è nativo: non serve ri-applicare patch dopo l'upgrade.)"
	} >"$ALERT"

	WIN_ALERT="$(cygpath -aw "$ALERT")"

	# System Scheduler gira nella sessione utente: apri l'alert in primo piano.
	# API_NO_OPEN=1 disabilita l'apertura (utile per i test).
	if [[ "${API_NO_OPEN:-0}" != "1" ]]; then
		"$NOTEPAD_EXE" "$WIN_ALERT" >>"$LOG" 2>&1 &
	fi
	exit 10
fi

# Nessun update (o errore): togli un eventuale alert vecchio per non confondere.
if [[ "$RC" -eq 0 ]]; then
	rm -f "$ALERT"
fi

exit "$RC"
