#!/usr/bin/env bash
# Sentinella Hindsight: sostituisce l'hook SessionEnd (che Claude Code cancella
# sempre alla chiusura interattiva con "Hook cancelled", issue #32712 — verificato
# 2026-07-17: cancella perfino un hook `exit 0` istantaneo, la gara non si vince).
# Lanciata detached da hindsight-ensure-up.sh a SessionStart; singleton via pidfile.
# Dorme finche' esiste almeno un processo claude (sessioni CLI e app desktop),
# poi: drain dei retain pendenti -> stop server MCP + Postgres embedded.
#
# Drain in due passi, nell'ordine (ICH-86): PRIMA il nostro
# `hindsight-retain-worker.py --drain` valuta le entry rimaste in
# hs-retain-queue/ (la coda di ogni sessione: lo Stop hook accoda soltanto, e
# l'ultimo turno non ha nessun UserPromptSubmit dopo di se' che lo valuti) e
# crea i retain in volo; POI ops/hindsight-drain-retain.py aspetta che il
# server abbia DAVVERO estratto i fatti (dei retain MCP e di quelli appena
# creati) prima dello stop. Con retain_enabled:false il primo passo e' un
# no-op che svuota solo la coda.
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
	. "$SCRIPT_DIR/lib/hs-python.sh"
	# Passo 1: valuta le code di sessione rimaste (gate + POST, force, senza
	# domande) — vedi header. Log in HS_CACHE_DIR (esportata da hs-python.sh):
	# contiene pezzi di transcript, non va in /tmp (leggibile da tutti su Linux).
	# Sovrascritto a ogni drain (come il vecchio hs-retain.log): niente crescita.
	"$HS_PY" "$SCRIPT_DIR/hindsight-retain-worker.py" --drain >"$HS_CACHE_DIR/hs-retain-drain.log" 2>&1
	# Passo 2: attendi che il server abbia DAVVERO estratto i fatti dei retain
	# pendenti (MCP + quelli del passo 1) prima di ucciderlo (l'estrazione LLM e'
	# async server-side, ~32s in mediana). Senza HOOK_INPUT il drain copre tutte
	# le bank del server.
	"$HS_PY" "$SCRIPT_DIR/ops/hindsight-drain-retain.py" >/dev/null 2>&1
	# Anti-race: durante il drain puo' essere partita una nuova sessione.
	# Spegnerle il server sotto i piedi la lascerebbe senza MCP (il suo ensure-up
	# ha gia' visto la porta occupata e non rilancia).
	[ "$(claude_alive)" -gt 0 ] && continue
	# Secondo livello anti-race: la sessione entrante puo' non essere ancora
	# visibile a claude_alive ma avere gia' lanciato il server (lock di boot) —
	# lo stop esce 1 e noi torniamo a dormire invece di morire, perche' il suo
	# ensure-up ha visto il nostro pidfile vivo e non spawnera' una sentinella.
	bash "$SCRIPT_DIR/ops/hindsight-stop-services.sh" || continue
	exit 0
done
