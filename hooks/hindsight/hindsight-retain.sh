#!/usr/bin/env bash
# Stop hook (async:true in hooks/hooks.json): salva un riassunto strutturato del turno
# appena completato in Hindsight. Non blocca nulla perche' eseguito in background da
# Claude Code; ha timeout 60s in hooks/hooks.json. La POST e' async:true sul server,
# quindi anche internamente non aspetta l'estrazione LLM dei fatti.
set -uo pipefail

# $(cat) forka /usr/bin/cat (~400ms su Windows/MSYS); `read` e' un builtin e non forka.
# NON usare $(</dev/stdin): con stdin da claude.exe (processo Windows nativo) il bash
# MSYS2 non lo risolve -> variabile vuota. Vedi hindsight-recall.sh per il dettaglio.
IFS= read -r -d '' HOOK_INPUT || true
export HOOK_INPUT
# API_URL e tutti gli altri parametri sono in hindsight.config.json (li carica il
# worker via hindsight_config.py). HINDSIGHT_API_URL resta come override opzionale.

# Path del worker relativo a questo script (robusto a spostamenti della cartella).
# `dirname` e la subshell $(cd && pwd) sono 2 fork (~600ms su MSYS); l'espansione
# %/* e' interna a bash. Guardia: senza `/` nel path, %/* non taglia nulla -> ".".
SCRIPT_DIR="${BASH_SOURCE[0]%/*}"; [ "$SCRIPT_DIR" = "${BASH_SOURCE[0]}" ] && SCRIPT_DIR="."
. "$SCRIPT_DIR/lib/hs-python.sh"
# Log in HS_CACHE_DIR (esportata da hs-python.sh) e non in /tmp: contiene l'output
# del worker, cioe' pezzi di transcript e memorie — su Linux /tmp e' leggibile da tutti.
"$HS_PY" "$SCRIPT_DIR/hindsight-retain-worker.py" >"$HS_CACHE_DIR/hs-retain.log" 2>&1
rc=$?

# Il worker torna !=0 quando la POST non arriva al server (server giu', rete, bank
# irraggiungibile): in quel caso NON esiste nessuna async operation da interrogare,
# quindi hindsight-failcheck.sh — che fa GET operations?status=failed — e' cieco
# proprio qui. Lascia una traccia DUREVOLE che il failcheck raccoglie al prossimo
# prompt: il log qui sopra non basta, viene azzerato dal retain successivo ('>').
# File separato e append: una riga per fallimento, tab-separated (ts \t messaggio).
# Il messaggio dice da se' cosa e' successo: nello stesso file scrive anche
# hindsight-drain-retain.py (retain arrivato al server ma non estratto in tempo),
# quindi l'etichetta non puo' stare cablata nel failcheck.
if [ "$rc" -ne 0 ]; then
	printf '%s\t%s\n' \
		"$(date -u +%Y-%m-%dT%H:%M:%SZ)" \
		"non arrivato al server — $(tail -2 "$HS_CACHE_DIR/hs-retain.log" 2>/dev/null | tr '\n\t' '  ')" \
		>> "$HS_CACHE_DIR/hs-retain-failed.log"
fi

# exit "$rc" e non "exit 0": l'hook e' async, quindi per Claude Code il codice
# finisce solo nel debug log (non blocca e non risveglia nessuno — servirebbe
# asyncRewake, che qui NON vogliamo: il retain gira a ogni Stop e con il server giu'
# sveglierebbe Claude in loop). La visibilita' vera la da' il failcheck sopra; questo
# exit onesto serve a chi legge il debug log e a chi invoca lo script a mano.
exit "$rc"
