#!/usr/bin/env bash
#
# auth-refresh-scheduled.sh - Rinnova la sessione notebooklm in modo NON interattivo.
#
# Invocato dal launcher auth-refresh-scheduled.cmd (System Scheduler), gira gia'
# dentro MSYS2 UCRT64. Lancia `notebooklm auth refresh` tramite il launcher exe-free
# (Python di mise + truststore per il proxy Eni + profilo cookie via NOTEBOOKLM_HOME),
# registra l'esito in logs/nb-auth-refresh-scheduled.log e, dopo N fallimenti
# CONSECUTIVI (default 3, ~ cookie SID scaduto), lascia un alert ben visibile che
# spiega come rigenerare i cookie. Un singolo errore transiente (rete) viene solo loggato.
#
# Exit:  0 = sessione rinnovata   |   altro = refresh fallito (rete o cookie scaduti)
#
# Variabili: NB_FAIL_THRESHOLD (default 3), NB_NO_OPEN=1 (non aprire Notepad, per i test).

set -uo pipefail

# Fallback robusto: in bash usa BASH_SOURCE, in zsh (come lo lancia il .cmd via
# `zsh <script>`) BASH_SOURCE e' vuoto, quindi ripiega su $0 = path dello script.
PROJ="${TRINITY_PLUGIN_DIR:-$(cd "$(dirname "${BASH_SOURCE[0]:-$0}")/../.." && pwd)}"
NB="${NB_LAUNCHER:-/e/AI/tools/notebooklm-data/notebooklm}"
THRESHOLD="${NB_FAIL_THRESHOLD:-3}"

cd "$PROJ" || {
	echo "auth-refresh-scheduled: cd $PROJ fallito" >&2
	exit 1
}

# Log/stato accanto allo script, in scheduler/notebooklm/
LOGDIR="$PROJ/scheduler/notebooklm"
mkdir -p "$LOGDIR"
LOG="$LOGDIR/nb-auth-refresh-scheduled.log"
ALERT="$LOGDIR/nb-auth-ALERT.txt"
FAILS="$LOGDIR/nb-auth-refresh-fails.count"
TS="$(date '+%Y-%m-%d %H:%M:%S')"
NOTEPAD_EXE="/c/Windows/System32/notepad.exe"

if [[ ! -f "$NB" ]]; then
	printf '[%s] launcher notebooklm non trovato: %s\n' "$TS" "$NB" | tr -d '\r' >>"$LOG"
	exit 1
fi

# auth refresh: rinnova __Secure-1PSIDTS in place (passa il proxy Eni via truststore).
OUT="$("$NB" auth refresh 2>&1)"
RC=$?

# Log su una riga (tr -d '\r' per il quirk CRLF di MSYS).
printf '[%s] rc=%s %s\n' "$TS" "$RC" "$OUT" | tr -d '\r' >>"$LOG"

if [[ "$RC" -eq 0 ]]; then
	# Successo: azzera il contatore e togli un eventuale alert vecchio.
	rm -f "$ALERT"
	echo 0 >"$FAILS"
	exit 0
fi

# Fallimento: incrementa il contatore dei fallimenti consecutivi.
n="$(tr -dc '0-9' <"$FAILS" 2>/dev/null)"
n="${n:-0}"
n=$((n + 1))
echo "$n" >"$FAILS"

# Sotto soglia: probabile glitch di rete transitorio, riprova al prossimo giro
# senza disturbare l'utente.
if [[ "$n" -lt "$THRESHOLD" ]]; then
	exit "$RC"
fi

# Soglia raggiunta: il cookie di base SID e' probabilmente scaduto (il refresh non
# basta piu'), serve rigenerare i cookie a mano. Alza un alert visibile.
{
	echo "NotebookLM - SESSIONE SCADUTA, RIGENERA I COOKIE"
	echo
	echo "  auth refresh fallito $n volte di fila (ultimo tentativo: $TS)."
	echo "  Probabile causa: il cookie di base SID e' scaduto (auth refresh non basta piu')."
	echo
	echo "Come rigenerare i cookie:"
	echo "  1. In Chrome loggato su https://notebooklm.google.com, premi F12 -> scheda Rete"
	echo "  2. Ricarica la pagina, click destro su una richiesta a notebooklm.google.com"
	echo "     -> Copia -> Copia come cURL (bash)"
	echo "  3. Incolla in:  E:/AI/tools/notebooklm-data/curl.txt"
	echo "  4. Esegui:      ruby E:/AI/tools/notebooklm-data/make_storage_state.rb"
	echo
	echo "Ultimo output di auth refresh:"
	echo "  $OUT"
} >"$ALERT"

WIN_ALERT="$(command -v cygpath >/dev/null 2>&1 && cygpath -aw "$ALERT" || printf '%s' "$ALERT")"

# System Scheduler gira nella sessione utente: apri l'alert in primo piano.
# NB_NO_OPEN=1 disabilita l'apertura (utile per i test).
if [[ "${NB_NO_OPEN:-0}" != "1" && -x "$NOTEPAD_EXE" ]]; then
	"$NOTEPAD_EXE" "$WIN_ALERT" >>"$LOG" 2>&1 &
fi

exit "$RC"
