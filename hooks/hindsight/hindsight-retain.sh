#!/usr/bin/env bash
# Stop hook (SINCRONO in hooks/hooks.json, timeout 10s): NON valuta e NON salva
# nulla — accoda il payload del hook e risponde subito '{}' (ICH-86).
#
# Perche': lo Stop deve restare istantaneo e non puo' ne' bloccare ne' chiamare
# un LLM (il gate semantico costa fino a 15s e un decision:block qui
# interromperebbe il turno). La valutazione e' DIFFERITA:
#   - al prossimo UserPromptSubmit, hindsight-recall.sh chiama
#     hindsight-retain-worker.py:evaluate_queued(session_id) -> prende l'entry
#     piu' recente di questa sessione, la valuta col gate e fa la POST (o mette
#     in pending + domanda in coda alla risposta successiva);
#   - a chiusura, hindsight-sentinel.sh lancia il worker con `--drain` e valuta
#     le entry rimaste (la coda della sessione, senza domande).
# Coda: $HS_CACHE_DIR/hs-retain-queue/<EPOCHREALTIME senza punto>-<pid>.json,
# HOOK_INPUT verbatim; il nome ordina per istante di scrittura. Percorso caldo
# a ZERO fork: solo builtin ed espansioni bash (mkdir/chmod solo alla prima
# creazione della dir, come lib/hs-python.sh). Non si sourcia hs-python.sh:
# qui non serve nessun Python.
set -uo pipefail

# $(cat) forka /usr/bin/cat (~400ms su Windows/MSYS); `read` e' un builtin e non forka.
# NON usare $(</dev/stdin): con stdin da claude.exe (processo Windows nativo) il bash
# MSYS2 non lo risolve -> variabile vuota. Vedi hindsight-recall.sh per il dettaglio.
IFS= read -r -d '' HOOK_INPUT || true

# Stesso path e stessa guardia di lib/hs-python.sh (per-utente, 0700: le entry
# contengono cwd e path del transcript). `[ -d ]` e' un builtin (~0ms); mkdir e
# chmod sono fork da ~400ms l'uno su MSYS, pagati solo alla creazione.
HS_CACHE_DIR="${XDG_CACHE_HOME:-$HOME/.cache}/trinity"
[ -d "$HS_CACHE_DIR" ] || {
	mkdir -p "$HS_CACHE_DIR" 2>/dev/null && chmod 700 "$HS_CACHE_DIR" 2>/dev/null
}
QUEUE_DIR="$HS_CACHE_DIR/hs-retain-queue"
[ -d "$QUEUE_DIR" ] || mkdir -p "$QUEUE_DIR" 2>/dev/null

# HOOK_INPUT vuoto (stdin non arrivato) => niente da accodare: il worker non
# saprebbe comunque quale transcript leggere.
if [ -n "$HOOK_INPUT" ]; then
	printf '%s' "$HOOK_INPUT" >"$QUEUE_DIR/${EPOCHREALTIME/./}-$$.json" 2>/dev/null
fi

# exit 0 sempre e '{}' su stdout: nessuna decisione da comunicare qui; l'esito
# della valutazione arrivera' col prossimo prompt (o nel drain di chiusura).
echo '{}'
exit 0
