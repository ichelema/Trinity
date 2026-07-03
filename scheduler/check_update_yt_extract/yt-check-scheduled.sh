#!/usr/bin/env bash
#
# yt-check-scheduled.sh — Wrapper per esecuzione NON interattiva (System Scheduler).
#
# Viene invocato dal launcher yt-check-scheduled.cmd via login shell, quindi gira
# già dentro MSYS2 UCRT64. Esegue `mise run yt-check`, registra l'esito in
# yt-check-scheduled.log e, se è uscita una versione del plugin yt-extract
# più recente di quella clonata in E:/AI/tools/claude-code-youtube-extract,
# lascia un file di alert visibile (e lo apre in Notepad).
#
# Exit:  0  = nessuna novità   |   10 = update disponibile   |   altro = errore

set -uo pipefail

PROJ="${TRINITY_PLUGIN_DIR:-$(cd "$(dirname "${BASH_SOURCE[0]:-$0}")/../.." && pwd)}"
MISE="$(command -v mise 2>/dev/null || echo "/e/msys64/home/Sphynx/.local/bin/mise.exe")"

cd "$PROJ" || {
	echo "yt-check-scheduled: cd $PROJ fallito" >&2
	exit 1
}

LOGDIR="$PROJ/scheduler/check_update_yt_extract"
mkdir -p "$LOGDIR"
LOG="$LOGDIR/yt-check-scheduled.log"
ALERT="$LOGDIR/yt-update-ALERT.txt"
TS="$(date '+%Y-%m-%d %H:%M:%S')"
NOTEPAD_EXE="/c/Windows/System32/notepad.exe"

# Re-fida il .mise.toml (idempotente, sopravvive alle sue modifiche future).
"$MISE" trust "$PROJ/mise.toml" >>"$LOG" 2>&1 || true

OUT="$("$MISE" run yt-check 2>>"$LOG")"
RC=$?

printf '[%s] rc=%s %s\n' "$TS" "$RC" "$OUT" | tr -d '\r' >>"$LOG"

if [[ "$RC" -eq 10 || "${YT_FORCE_ALERT:-0}" == "1" ]]; then
	{
		echo "yt-extract — NUOVA VERSIONE DISPONIBILE SU GITHUB"
		echo
		echo "  rilevato il: $TS"
		echo
		echo "Dettaglio (installed vs latest su GitHub):"
		printf '%s\n' "$OUT" | tr -d '\r' |
			grep -oE '"(repo|installed|latest_github)"[^,}]*' |
			sed 's/^/    /'
		echo
		echo "Per aggiornare il plugin:"
		echo
		echo "  git -C E:/AI/tools/claude-code-youtube-extract pull"
		echo
		echo "IMPORTANTE: dopo il pull riapplicare la patch exe-free a run_ytdlp():"
		echo "  in scripts/yt-extract.py, la funzione run_ytdlp() deve invocare"
		echo "  python -m yt_dlp con PYTHONPATH=E:/AI/tools/yt-dlp invece del"
		echo "  comando esterno 'yt-dlp'."
		echo
		echo "Vedi Hindsight (recall 'yt-extract patch exe-free') per il diff completo."
		echo
		echo "PASSO 3 (yt-extract e' incorporato in Trinity): risincronizzare la copia:"
		echo "  SRC=E:/AI/tools/claude-code-youtube-extract; DST=E:/AI/Claude/Trinity"
		echo "  cp -r \$SRC/skills/yt-extract/. \$DST/skills/yt-extract/"
		echo "  cp \$SRC/agents/extract-worker.md \$DST/agents/extract-worker.md"
		echo "  cp \$SRC/scripts/yt-extract.py    \$DST/scripts/yt-extract.py"
		echo "  poi in \$DST/skills/yt-extract/SKILL.md ripatchare il namespace"
		echo "  yt-extract:extract-worker -> trinity:extract-worker, e riavviare Claude Code."
	} >"$ALERT"

	WIN_ALERT="$(cygpath -aw "$ALERT")"

	if [[ "${YT_NO_OPEN:-0}" != "1" ]]; then
		"$NOTEPAD_EXE" "$WIN_ALERT" >>"$LOG" 2>&1 &
	fi
	exit 10
fi

if [[ "$RC" -eq 0 ]]; then
	rm -f "$ALERT"
fi

exit "$RC"
