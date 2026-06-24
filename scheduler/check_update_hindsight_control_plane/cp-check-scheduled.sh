#!/usr/bin/env bash
#
# cp-check-scheduled.sh — Wrapper per esecuzione NON interattiva (System Scheduler).
#
# Viene invocato dal launcher cp-check-scheduled.cmd via `bash -lc`, quindi gira
# già dentro MSYS2 UCRT64. Esegue `mise run cp-check`, registra l'esito in
# logs/cp-check-scheduled.log e, se è uscita una versione del Control Plane più
# recente di quella pinnata, lascia un file di alert ben visibile (e lo apre).
#
# Exit:  0  = nessuna novità   |   10 = update disponibile   |   altro = errore

set -uo pipefail

PROJ="${TRINITY_PLUGIN_DIR:-$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)}"
MISE="$(command -v mise 2>/dev/null || echo "/e/msys64/home/Sphynx/.local/bin/mise.exe")"

cd "$PROJ" || {
	echo "cp-check-scheduled: cd $PROJ fallito" >&2
	exit 1
}

mkdir -p logs
LOG="logs/cp-check-scheduled.log"
ALERT="logs/cp-update-ALERT.txt"
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
	pinned="$(printf '%s' "$OUT" | grep -oE '"pinned"[^,]*' | grep -oE '[0-9]+\.[0-9]+\.[0-9]+' | head -1)"
	{
		echo "Control Plane Hindsight — NUOVA VERSIONE DISPONIBILE"
		echo
		echo "  pinnata (in .mise.toml): ${pinned:-?}"
		echo "  ultima su npm:           ${latest:-?}"
		echo "  rilevato il:             $TS"
		echo
		echo "Prossimo passo — verifica se ha ancora il bug del redirect-loop:"
		echo "    VERSION=${latest:-X.Y.Z} mise run cp-redirect-test"
		echo
		echo "Se il verdetto è OK, aggiorna il pin nel task control-plane di .mise.toml"
		echo "(riga con hindsight-control-plane@... e il commento sopra)."
	} >"$ALERT"

    WIN_ALERT="$(cygpath -aw "$ALERT")"

    # System Scheduler gira nella sessione utente: apri l'alert in primo piano.
    # CP_NO_OPEN=1 disabilita l'apertura (utile per i test).
	if [[ "${CP_NO_OPEN:-0}" != "1" ]]; then
        "$NOTEPAD_EXE" "$WIN_ALERT" >>"$LOG" 2>&1 &
	fi
	exit 10

fi

# Nessun update (o errore): togli un eventuale alert vecchio per non confondere.
if [[ "$RC" -eq 0 ]]; then
	rm -f "$ALERT"
fi

exit "$RC"
