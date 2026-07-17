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
# SessionEnd; lo annulla subito ("Hook cancelled"), su Ctrl+C anche ignorando il
# `timeout` configurato (issue anthropics/claude-code#32712). Quindi il lavoro lento
# (retain + sleep + stop) gira in un processo staccato con setsid/nohup e l'hook
# ritorna subito. Anche il percorso foreground deve restare minimo: su MSYS2 ogni
# processo extra costa ~850ms di fork emulato e se l'annullamento arriva prima dello
# spawn del worker, retain finale e stop dei servizi vanno persi (verificato: kill a
# 0.5s con jq in foreground -> worker mai partito; senza jq sopravvive a kill a 0.15s).
# Logica di stop condivisa con `mise run stop-hindsight`.
set -uo pipefail

# --- Worker: gira detached, fa il lavoro vero -------------------------------------
if [ "${1:-}" = "--worker" ]; then
	# SCRIPT_DIR solo qui: il $(cd ... && pwd) è un fork (~300ms su MSYS2) che il
	# percorso foreground non può permettersi (usa solo BASH_SOURCE).
	SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
	INPUT="$2"

	# Ri-verifica autorevole del reason con jq (in foreground costava ~850ms, qui il
	# tempo non manca). Il filtro bash dell'hook resta la prima difesa.
	REASON="$(printf '%s' "$INPUT" | jq -r '.reason // "other"' 2>/dev/null | tr -d '\r')"
	[ "$REASON" = "clear" ] && exit 0

	# 1) Retain finale forzato: cattura la coda della sessione prima di spegnere il server.
	#    NB: con retain_enabled:false (config attuale) questo passo e' un NO-OP consapevole:
	#    il worker esce prima di valutare HS_RETAIN_FORCE (scelta di 6e21acf, "vale per
	#    quando verra' riacceso"). La coda della sessione si salva solo via retain MCP.
	printf '%s' "$INPUT" | HS_RETAIN_FORCE=1 bash "$SCRIPT_DIR/hindsight-retain.sh" >/dev/null 2>&1 || true

	# 2) Liveness reale: conta i processi launcher di Claude ancora attivi. Robusto ai
	#    crash (un lease orfano non blocca piu' lo stop). Il launcher di QUESTA sessione
	#    sta uscendo: se ne restano >=2 c'e' di sicuro un'altra sessione (esci subito);
	#    se ne resta 1 puo' essere solo la nostra in chiusura -> attendi che sparisca.
	# Si conta il NOME del binario, non il path di installazione: ancorarlo a
	# '.local/bin' mancava le sessioni avviate da claude_code_desktop.cmd, che girano
	# come C:\...\AnthropicClaude\claude.exe -> conteggio 0 -> server spento sotto una
	# sessione desktop viva. Costo accettato: l'app desktop e' lo stesso binario della
	# chat, quindi con l'app aperta il server resta su finche' non fai stop-hindsight.
	# Contare di troppo spreca RAM; contare di meno uccide la memoria di una sessione.
	case "$(uname -s)" in
	MINGW* | MSYS* | CYGWIN*)
		# ps -W è MSYS-only: mostra anche i processi Windows nativi (il launcher claude).
		# Serve accettare ENTRAMBI i separatori: ps -W stampa la forma MSYS
		# (/e/.../bin/claude) se il padre e' una shell MSYS, quella Windows
		# (C:\...\claude.exe) se lo ha lanciato Windows (app desktop, .cmd, scorciatoia).
		# Verificato con notepad: da bash -> /c/Windows/System32/notepad, da
		# `cmd //c start` -> C:\Windows\System32\notepad.exe.
		claude_alive() { ps -W 2>/dev/null | grep -icE '[/\\]claude(\.exe)?([[:space:]]|$)'; }
		;;
	*)
		# pgrep -c stampa il conteggio (0 incluso) ma esce 1 senza match: || true.
		# (^|[/]): lanciando `claude` per nome dal PATH (il caso comune) la cmdline
		# inizia con la parola nuda, senza slash: argv[0] e' quello che hai digitato.
		# [/] e non /: il match e' sul separatore prima del nome, cosi' '/.claude/...'
		# (config dir, presente nella cmdline dell'hook) non viene contato per sbaglio.
		claude_alive() { pgrep -fc '(^|[/])claude([[:space:]]|$)' 2>/dev/null || true; }
		;;
	esac
	[ "$(claude_alive)" -ge 2 ] && exit 0
	for _ in $(seq 1 10); do
		[ "$(claude_alive)" -eq 0 ] && break
		sleep 2
	done
	[ "$(claude_alive)" -gt 0 ] && exit 0

	# 3) Nessuna sessione Claude viva: attendi che il server abbia DAVVERO estratto i
	#    fatti del retain finale prima di ucciderlo — la POST e' async, l'estrazione LLM
	#    prosegue server-side e dura ~32s in mediana. Il vecchio `sleep 7` fisso la
	#    troncava nell'89% dei casi e la memoria di fine sessione spariva senza errori
	#    (vedi hindsight-drain-retain.py). Infine ferma server (launcher + python) e
	#    Postgres embedded.
	. "$SCRIPT_DIR/lib/hs-python.sh"
	HOOK_INPUT="$INPUT" "$HS_PY" "$SCRIPT_DIR/ops/hindsight-drain-retain.py" >/dev/null 2>&1
	# Ultimo check anti-race: durante lo sleep puo' essere partita una NUOVA sessione
	# (riavvio rapido di Claude Code). Spegnerle il server sotto i piedi lascerebbe
	# la sessione senza MCP (il suo ensure-up ha gia' visto la porta occupata e non
	# rilancia). Se c'e' un claude vivo, non toccare i servizi.
	[ "$(claude_alive)" -gt 0 ] && exit 0
	bash "$SCRIPT_DIR/ops/hindsight-stop-services.sh"
	exit 0
fi

# --- Hook: lancia il worker detached SUBITO e ritorna -------------------------------
# Niente jq né subshell qui (vedi header): stdin letto col builtin `read` (zero fork)
# e filtro /clear con match bash istantaneo, sicuro perché l'input di SessionEnd è un
# JSON piccolo e piatto, senza contenuto utente annidato.
INPUT=""
IFS= read -r -d '' INPUT || true
[[ "$INPUT" =~ \"reason\"[[:space:]]*:[[:space:]]*\"clear\" ]] && exit 0

setsid nohup bash "${BASH_SOURCE[0]}" --worker "$INPUT" </dev/null >/dev/null 2>&1 &
disown 2>/dev/null || true

exit 0
