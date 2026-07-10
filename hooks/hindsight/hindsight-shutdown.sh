#!/usr/bin/env bash
# Hook SessionEnd: alla VERA chiusura della sessione fa il retain finale e poi ferma
# TUTTO ció che start-hindsight lascia attivo (i processi sono detached e sopravvivono
# alla chiusura: vedi memoria msys-background-detach):
#   - server MCP: launcher hindsight-local-mcp.exe + python figlio (porta 8888, ~1.5GB)
#   - Postgres embedded del bank (porta 5432, master + worker)
#
# IMPORTANTE: SessionEnd scatta anche su /clear (reason=clear) — la sessione continua e
# NON dobbiamo spegnere i servizi. Filtriamo sul campo `reason` dello stdin.
#
# Perché detached: all'uscita Claude Code NON aspetta il completamento dell'hook
# SessionEnd; appena il processo termina lo annulla ("Hook cancelled"). Quindi il lavoro
# lento (retain + sleep + stop) gira in un processo staccato con setsid/nohup e l'hook
# ritorna subito. Logica di stop condivisa con `mise run stop-hindsight`.
set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# --- Worker: gira detached, fa il lavoro vero -------------------------------------
if [ "${1:-}" = "--worker" ]; then
	INPUT="$2"
	SESS_DIR="/tmp/hs-sessions"

	# 1) Retain finale forzato: cattura la coda della sessione prima di spegnere il server.
	printf '%s' "$INPUT" | HS_RETAIN_FORCE=1 bash "$SCRIPT_DIR/hindsight-retain.sh" >/dev/null 2>&1 || true

	# 2) Liveness reale: conta i processi launcher di Claude ancora attivi. Robusto ai
	#    crash (un lease orfano non blocca piu' lo stop). Il launcher di QUESTA sessione
	#    sta uscendo: se ne restano >=2 c'e' di sicuro un'altra sessione (esci subito);
	#    se ne resta 1 puo' essere solo la nostra in chiusura -> attendi che sparisca.
	claude_alive() { ps -W 2>/dev/null | grep -icE '/\.local/bin/claude(\.exe)?([[:space:]]|$)'; }
	[ "$(claude_alive)" -ge 2 ] && exit 0
	for _ in $(seq 1 10); do
		[ "$(claude_alive)" -eq 0 ] && break
		sleep 2
	done
	[ "$(claude_alive)" -gt 0 ] && exit 0

	# 3) Nessuna sessione Claude viva: i lease rimasti sono orfani -> ripulisci. Poi dai
	#    al worker async il tempo di estrarre i fatti del retain finale PRIMA di uccidere
	#    il server, e infine ferma server (launcher + python) e Postgres embedded.
	[ -d "$SESS_DIR" ] && find "$SESS_DIR" -type f -delete 2>/dev/null || true
	sleep 7
	# Ultimo check anti-race: durante lo sleep puo' essere partita una NUOVA sessione
	# (riavvio rapido di Claude Code). Spegnerle il server sotto i piedi lascerebbe
	# la sessione senza MCP (il suo ensure-up ha gia' visto la porta occupata e non
	# rilancia). Se c'e' un claude vivo, non toccare i servizi.
	[ "$(claude_alive)" -gt 0 ] && exit 0
	bash "$SCRIPT_DIR/ops/hindsight-stop-services.sh"
	exit 0
fi

# --- Hook: filtra /clear, lancia il worker detached e ritorna subito ---------------
INPUT="$(cat)"
REASON="$(printf '%s' "$INPUT" | jq -r '.reason // "other"' 2>/dev/null | tr -d '\r')"
case "$REASON" in
clear) exit 0 ;;
esac

setsid nohup bash "${BASH_SOURCE[0]}" --worker "$INPUT" </dev/null >/dev/null 2>&1 &
disown 2>/dev/null || true

exit 0
