#!/usr/bin/env bash
#
# nb-check-scheduled.sh — Wrapper per esecuzione NON interattiva (System Scheduler).
#
# Viene invocato dal launcher nb-check-scheduled.cmd via login shell, quindi gira
# già dentro MSYS2 UCRT64. Esegue `mise run nb-check`, registra l'esito in
# nb-check-scheduled.log e, se è uscita una versione di notebooklm-py più
# recente di quella installata in E:/AI/tools/notebooklm, lascia un file di
# alert visibile (e lo apre in Notepad).
#
# Exit:  0  = nessuna novità   |   10 = update disponibile   |   altro = errore

set -uo pipefail

PROJ="${TRINITY_PLUGIN_DIR:-$(cd "$(dirname "${BASH_SOURCE[0]:-$0}")/../.." && pwd)}"
MISE="$(command -v mise 2>/dev/null || echo "/e/msys64/home/Sphynx/.local/bin/mise.exe")"

cd "$PROJ" || {
	echo "nb-check-scheduled: cd $PROJ fallito" >&2
	exit 1
}

LOGDIR="$PROJ/scheduler/check_update_notebooklm"
mkdir -p "$LOGDIR"
LOG="$LOGDIR/nb-check-scheduled.log"
ALERT="$LOGDIR/nb-update-ALERT.txt"
TS="$(date '+%Y-%m-%d %H:%M:%S')"
NOTEPAD_EXE="/c/Windows/System32/notepad.exe"

# Re-fida il .mise.toml (idempotente, sopravvive alle sue modifiche future).
"$MISE" trust "$PROJ/mise.toml" >>"$LOG" 2>&1 || true

OUT="$("$MISE" run nb-check 2>>"$LOG")"
RC=$?

printf '[%s] rc=%s %s\n' "$TS" "$RC" "$OUT" | tr -d '\r' >>"$LOG"

if [[ "$RC" -eq 10 || "${NB_FORCE_ALERT:-0}" == "1" ]]; then
	{
		echo "notebooklm-py — NUOVA VERSIONE DISPONIBILE SU PYPI"
		echo
		echo "  rilevato il: $TS"
		echo
		echo "Dettaglio (installed vs latest su PyPI):"
		printf '%s\n' "$OUT" | tr -d '\r' |
			grep -oE '"(package|installed|latest_pypi)"[^,}]*' |
			sed 's/^/    /'
		echo
		echo "ATTENZIONE: notebooklm-py è installato in modalità exe-free (flat-extract)."
		echo "Non usare pip install — seguire la procedura manuale:"
		echo
		echo "  1. Backup:  cp -r E:/AI/tools/notebooklm E:/AI/tools/notebooklm.bak-\$(date +%Y%m%d)"
		echo "  2. Download wheel da PyPI oppure sorgente GitHub (teng-lin/notebooklm-py)"
		echo "  3. Estrai solo il package notebooklm/ e il dist-info in E:/AI/tools/notebooklm"
		echo "  4. Verifica: find /e/AI/tools/notebooklm -iname '*.exe' -o -iname '*.dll' (deve essere vuoto)"
		echo "  5. Smoke test: PYTHONPATH=E:/AI/tools/notebooklm python -m notebooklm.mcp --help"
		echo
		echo "Vedi Hindsight (recall 'notebooklm aggiornamento exe-free') per i dettagli completi."
	} >"$ALERT"

	WIN_ALERT="$(cygpath -aw "$ALERT")"

	if [[ "${NB_NO_OPEN:-0}" != "1" ]]; then
		"$NOTEPAD_EXE" "$WIN_ALERT" >>"$LOG" 2>&1 &
	fi
	exit 10
fi

if [[ "$RC" -eq 0 ]]; then
	rm -f "$ALERT"
fi

exit "$RC"
