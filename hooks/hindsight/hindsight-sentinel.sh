#!/usr/bin/env bash
# Sentinella Hindsight: sostituisce l'hook SessionEnd (che Claude Code cancella
# sempre alla chiusura interattiva con "Hook cancelled", issue #32712 — verificato
# 2026-07-17: cancella perfino un hook `exit 0` istantaneo, la gara non si vince).
# Lanciata detached da hindsight-ensure-up.sh a SessionStart; singleton via pidfile.
# Dorme finche' esiste almeno un processo claude (sessioni CLI e app desktop),
# poi: drain dei retain pendenti -> stop server MCP + Postgres embedded.
#
# NB: il retain finale per-sessione decade consapevolmente: era gia' NO-OP con
# retain_enabled:false; la coda della sessione si salva solo via retain MCP.
# Bonus rispetto all'hook: copre anche kill -9 e chiusura finestra; /clear non
# richiede filtri (il processo claude resta vivo, la sentinella non scatta).
set -uo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PIDFILE="${TMPDIR:-/tmp}/hindsight-sentinel.pid"
POLL=10

case "$(uname -s)" in
MINGW* | MSYS* | CYGWIN*)
	# ps -W è MSYS-only: mostra anche i processi Windows nativi (il launcher claude).
	# Accetta ENTRAMBI i separatori: forma MSYS (/e/.../bin/claude) se il padre e'
	# una shell MSYS, Windows (C:\...\claude.exe) se lanciato da Windows (app
	# desktop, .cmd, scorciatoia).
	claude_alive() { ps -W 2>/dev/null | grep -icE '[/\\]claude(\.exe)?([[:space:]]|$)'; }
	;;
*)
	# pgrep -c stampa il conteggio (0 incluso) ma esce 1 senza match: || true.
	# (^|[/]): lanciando `claude` per nome dal PATH la cmdline inizia con la parola
	# nuda. [/] e non /: il match e' sul separatore prima del nome, cosi'
	# '/.claude/...' (config dir) non viene contato per sbaglio.
	claude_alive() { pgrep -fc '(^|[/])claude([[:space:]]|$)' 2>/dev/null || true; }
	;;
esac

# Singleton: se un'altra sentinella e' viva esci; pidfile stantio -> rimpiazza.
# (Su kill non catturato il trap EXIT non scatta: il pidfile resta, ma kill -0
# lo smaschera come stantio al giro successivo.)
if [ -f "$PIDFILE" ]; then
	pid="$(<"$PIDFILE")"
	kill -0 "$pid" 2>/dev/null && exit 0
	rm -f "$PIDFILE"
fi
(
	set -C
	echo $$ >"$PIDFILE"
) 2>/dev/null || exit 0
trap 'rm -f "$PIDFILE"' EXIT

while :; do
	# Dormi finche' almeno una sessione Claude e' viva (o l'app desktop).
	while [ "$(claude_alive)" -gt 0 ]; do sleep "$POLL"; done
	# Conferma: un singolo campione a 0 puo' essere un hiccup di ps.
	sleep 5
	[ "$(claude_alive)" -gt 0 ] && continue
	# Drain: attendi che il server abbia DAVVERO estratto i fatti dei retain MCP
	# pendenti prima di ucciderlo (l'estrazione LLM e' async server-side, ~32s in
	# mediana). Senza HOOK_INPUT il drain copre tutte le bank del server.
	. "$SCRIPT_DIR/lib/hs-python.sh"
	"$HS_PY" "$SCRIPT_DIR/ops/hindsight-drain-retain.py" >/dev/null 2>&1
	# Anti-race: durante il drain puo' essere partita una nuova sessione.
	# Spegnerle il server sotto i piedi la lascerebbe senza MCP (il suo ensure-up
	# ha gia' visto la porta occupata e non rilancia).
	[ "$(claude_alive)" -gt 0 ] && continue
	bash "$SCRIPT_DIR/ops/hindsight-stop-services.sh"
	exit 0
done
