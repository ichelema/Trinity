#!/usr/bin/env bash
#
# promote-scan-scheduled.sh — Wrapper per esecuzione NON interattiva (System Scheduler).
#
# Job settimanale del funnel di promozione multi-bank: esegue `mise run
# promote-scan` (scan dei bank progetto + triage gpt-4.1-nano, verdetti cachati
# nello state file → le run successive ripagano solo i documenti nuovi).
# Se ci sono candidati lascia un alert ben visibile e lo apre: il move resta
# SEMPRE a /trinity:promote con review umana, qui non si promuove nulla.
#
# Server Hindsight giù: SKIP con log (niente avvio di server+Postgres da cron
# per un job non urgente: i documenti aspettano la prossima run).
#
# Exit:  0 = nessun candidato   |  10 = candidati trovati
#        3 = server giù (skip)  |  altro = errore

set -uo pipefail

# Root del repo: fissa per il job di System Scheduler; fallback relativo a
# questo script per portabilità (scheduler/promote_scan/ → 2 livelli su).
PROJ="/d/AI/Claude/Trinity"
[ -d "$PROJ" ] || PROJ="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
MISE="/c/msys64/home/EN27553/.local/bin/mise.exe"

cd "$PROJ" || {
	echo "promote-scan-scheduled: cd $PROJ fallito" >&2
	exit 1
}

mkdir -p logs
LOG="logs/promote-scan-scheduled.log"
ALERT="logs/promote-candidates-ALERT.txt"
REPORT="logs/promote-candidates.json"
TS="$(date '+%Y-%m-%d %H:%M:%S')"
NOTEPAD_EXE="/c/Windows/System32/notepad.exe"

# Server giù → skip pulito (vedi header).
if ! curl -fsS -m 3 -o /dev/null "http://127.0.0.1:8888/v1/default/banks" 2>/dev/null; then
	printf '[%s] rc=3 skip: server Hindsight giù\n' "$TS" >>"$LOG"
	exit 3
fi

# mise rifiuta un config non "trusted" da un contesto scheduler "nudo":
# ri-fidiamo a ogni run (idempotente, è il nostro config).
"$MISE" trust "$PROJ/mise.toml" >>"$LOG" 2>&1 || true

OUT="$("$MISE" run promote-scan 2>>"$LOG")"
RC=$?
printf '[%s] rc=%s %s\n' "$TS" "$RC" "$OUT" | tr -d '\r' >>"$LOG"

if [[ "$RC" -ne 0 ]]; then
	exit "$RC"
fi

# Conta i candidati dal report (senza jq: quirk CRLF/named-capture su MSYS).
N="$(grep -oE '"count": *[0-9]+' "$REPORT" 2>/dev/null | grep -oE '[0-9]+' | head -1)"
N="${N:-0}"

if [[ "$N" -gt 0 ]]; then
	{
		echo "Hindsight — $N FATTI CANDIDATI ALLA PROMOZIONE sul bank core"
		echo
		echo "  report:      $REPORT"
		echo "  generato il: $TS"
		echo
		echo "Prossimo passo — rivedi e promuovi con la review umana:"
		echo "    /trinity:promote   (in una sessione Claude Code)"
		echo
		echo "Nessun documento è stato spostato: la promozione è sempre curata."
	} >"$ALERT"
	if [[ "${PROMOTE_NO_OPEN:-0}" != "1" ]]; then
		"$NOTEPAD_EXE" "$(cygpath -aw "$ALERT")" >>"$LOG" 2>&1 &
	fi
	exit 10
fi

# Nessun candidato: togli un eventuale alert vecchio per non confondere.
rm -f "$ALERT"
exit 0
