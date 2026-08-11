#!/usr/bin/env bash
# Stop hook (SINCRONO in hooks/hooks.json, timeout 60s): salva un riassunto
# strutturato del turno appena completato in Hindsight. Dispatch (ICH-67):
#   - retain_gate_mode off/shadow -> worker in BACKGROUND e risposta immediata
#     '{}': per Claude Code e' identico al vecchio "async": true (zero attesa).
#   - retain_gate_mode enforce    -> worker in foreground; se il gate decide
#     "retain" il worker scrive una riga 'HSGATE {json}' nel log e questo
#     wrapper la inoltra su stdout (decision:block -> Claude mostra la notifica
#     e chiama il retain MCP prima di fermarsi).
# La POST del worker resta async:true lato server, quindi anche in foreground
# non si aspetta l'estrazione LLM dei fatti.
set -uo pipefail

# $(cat) forka /usr/bin/cat (~400ms su Windows/MSYS); `read` e' un builtin e non forka.
# NON usare $(</dev/stdin): con stdin da claude.exe (processo Windows nativo) il bash
# MSYS2 non lo risolve -> variabile vuota. Vedi hindsight-recall.sh per il dettaglio.
IFS= read -r -d '' HOOK_INPUT || true
export HOOK_INPUT

# Guardia anti-loop: al Stop successivo a un decision:block Claude Code manda
# stop_hook_active=true; senza uscita immediata il gate ribloccherebbe in loop.
# Match testuale puro (zero fork), copre JSON compatto e con spazio dopo i due punti.
case "$HOOK_INPUT" in
*'"stop_hook_active":true'* | *'"stop_hook_active": true'*)
	echo '{}'
	exit 0
	;;
esac

# Path del worker relativo a questo script (robusto a spostamenti della cartella).
# `dirname` e la subshell $(cd && pwd) sono 2 fork (~600ms su MSYS); l'espansione
# %/* e' interna a bash. Guardia: senza `/` nel path, %/* non taglia nulla -> ".".
SCRIPT_DIR="${BASH_SOURCE[0]%/*}"; [ "$SCRIPT_DIR" = "${BASH_SOURCE[0]}" ] && SCRIPT_DIR="."
# Claude Code (claude.exe nativo) invoca l'hook con path stile Windows (E:/...):
# bash lo digerisce, ma il python MSYS tratta "E:/..." come RELATIVO (lo concatena
# al cwd) e il worker non parte -> retain perso a ogni Stop. Normalizza
# drive-letter -> POSIX (/e/...) con sola espansione bash, zero fork (niente
# cygpath). Su Linux/macOS il pattern non matcha mai.
case "$SCRIPT_DIR" in
[A-Za-z]:/*) _hs_drive="${SCRIPT_DIR%%:*}"; SCRIPT_DIR="/${_hs_drive,,}${SCRIPT_DIR#?:}" ;;
esac
. "$SCRIPT_DIR/lib/hs-python.sh"

# run_worker: log in HS_CACHE_DIR (esportata da hs-python.sh) e non in /tmp:
# contiene l'output del worker, cioe' pezzi di transcript e memorie — su Linux
# /tmp e' leggibile da tutti. Il worker torna !=0 quando la POST non arriva al
# server (server giu', rete, bank irraggiungibile): in quel caso NON esiste
# nessuna async operation da interrogare, quindi hindsight-failcheck.sh — che fa
# GET operations?status=failed — e' cieco proprio qui. Lascia una traccia
# DUREVOLE che il failcheck raccoglie al prossimo prompt: il log qui sopra non
# basta, viene azzerato dal retain successivo ('>'). File separato e append:
# una riga per fallimento, tab-separated (ts \t messaggio). Il messaggio dice
# da se' cosa e' successo: nello stesso file scrive anche
# hindsight-drain-retain.py (retain arrivato al server ma non estratto in
# tempo), quindi l'etichetta non puo' stare cablata nel failcheck.
run_worker() {
	"$HS_PY" "$SCRIPT_DIR/hindsight-retain-worker.py" >"$HS_CACHE_DIR/hs-retain.log" 2>&1
	local rc=$?
	if [ "$rc" -ne 0 ]; then
		printf '%s\t%s\n' \
			"$(date -u +%Y-%m-%dT%H:%M:%SZ)" \
			"non arrivato al server — $(tail -2 "$HS_CACHE_DIR/hs-retain.log" 2>/dev/null | tr '\n\t' '  ')" \
			>>"$HS_CACHE_DIR/hs-retain-failed.log"
	fi
	return "$rc"
}

# Modalita' del gate dalla config centralizzata: e' l'unico costo sincrono del
# percorso comune (un avvio Python). Il worker vero resta fuori dal percorso
# critico salvo enforce.
GATE_MODE="$("$HS_PY" "$SCRIPT_DIR/lib/hindsight_config.py" --get retain_gate_mode 2>/dev/null)"

if [ "$GATE_MODE" = "enforce" ]; then
	run_worker
	# In enforce+retain il worker non fa la POST: emette la riga HSGATE col JSON
	# gia' pronto per Claude Code. Riga assente => nessun blocco: '{}'.
	GATE_LINE=$(grep '^HSGATE ' "$HS_CACHE_DIR/hs-retain.log" 2>/dev/null | tail -1)
	if [ -n "$GATE_LINE" ]; then
		printf '%s\n' "${GATE_LINE#HSGATE }"
	else
		echo '{}'
	fi
	# exit 0 sempre: l'esito vero e' nel JSON su stdout; su un hook sincrono un
	# exit!=0 mostrerebbe un warning a ogni problema di rete, mentre la
	# visibilita' dei fallimenti e' gia' garantita da hs-retain-failed.log +
	# failcheck.
	exit 0
fi

# off/shadow: worker in background e risposta immediata — comportamento
# equivalente al vecchio hook async. </dev/null stacca stdin; stdout/stderr del
# figlio vanno nel log, quindi nessun fd tiene in vita l'hook per Claude Code.
run_worker </dev/null &
echo '{}'
exit 0
