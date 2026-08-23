#!/usr/bin/env bash
# Diagnostica completa setup Hindsight + hook Claude Code.
# Uso: bash hooks/hindsight/tools/hindsight-check.sh
# Restituisce exit 0 se tutto OK, 1 altrimenti. Output con check ✓/✗ per componente.
set -uo pipefail

HOOKS_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
# check.sh vive in tools/: con /.. HOOKS_DIR torna a hooks/hindsight (root del
# sottosistema). lib/ ops/ tools/ sono sotto di qui; la root di progetto e' due livelli sopra.
PROJ="${CLAUDE_PROJECT_DIR:-$(cd "$HOOKS_DIR/../.." && pwd)}"
# Conversione path per il Python nativo: su Windows serve cygpath -w, altrove no-op.
w() { if command -v cygpath >/dev/null 2>&1; then cygpath -w "$1"; else printf '%s' "$1"; fi; }
# API_BASE dalla config centralizzata (hindsight.config.json), con fallback.
API_BASE="$(PYTHONUTF8=1 python "$HOOKS_DIR/lib/hindsight_config.py" --get api_url 2>/dev/null)"
API_BASE="${API_BASE:-http://127.0.0.1:8888/v1/default/banks/trinity-project}"
SERVER_ROOT="${API_BASE%%/v1*}"
PASS=0
FAIL=0
SKIP=0

ok() {
	printf "  [\033[32mOK \033[0m] %s\n" "$1"
	PASS=$((PASS + 1))
}
ko() {
	printf "  [\033[31mKO \033[0m] %s\n" "$1"
	FAIL=$((FAIL + 1))
}
skip() {
	printf "  [\033[33mSKIP\033[0m] %s\n" "$1"
	SKIP=$((SKIP + 1))
}
note() { printf "        %s\n" "$1"; }
sect() { printf "\n\033[1m== %s ==\033[0m\n" "$1"; }

# --- 1. SERVER ---
sect "1. Server hindsight-local-mcp"
HTTP=$(curl -s -m 2 -o /dev/null -w "%{http_code}" "$SERVER_ROOT/" 2>/dev/null || echo "000")
if [ "$HTTP" != "000" ] && [ -n "$HTTP" ]; then
	ok "server risponde su $SERVER_ROOT (HTTP $HTTP, 404 atteso)"
else
	ko "server NON risponde su $SERVER_ROOT"
	note "fix: 'mise run start-hindsight' e ricontrolla tra 20s"
fi

case "$(uname -s)" in
MINGW* | MSYS* | CYGWIN*)
	# netstat.exe nativo: quello MSYS non vede sempre i processi Windows.
	PID=$(/c/Windows/System32/netstat.exe -ano 2>/dev/null | grep ":8888" | grep LISTENING | awk '{print $NF}' | tr -d '\r' | head -1)
	;;
*)
	PID=$(ss -ltnp 2>/dev/null | grep ':8888' | grep -oE 'pid=[0-9]+' | head -1 | cut -d= -f2)
	[ -n "$PID" ] || PID=$(lsof -ti tcp:8888 -sTCP:LISTEN 2>/dev/null | head -1)
	;;
esac
if [ -n "$PID" ]; then
	ok "porta 8888 LISTENING (PID $PID)"
else
	ko "porta 8888 non in LISTENING"
fi

# --- 2. ENDPOINT REST CHIAVE ---
sect "2. Endpoint REST"
for path in "/health" "/v1/default/banks" "/v1/default/banks/trinity-project/tags"; do
	H=$(curl -s -m 3 -o /dev/null -w "%{http_code}" "$SERVER_ROOT$path" 2>/dev/null || echo "000")
	if [ "$H" = "200" ] || [ "$H" = "404" ]; then
		ok "$path → HTTP $H"
	else
		ko "$path → HTTP $H (atteso 200 o 404)"
	fi
done

# --- 3. RECALL FUNZIONA ---
sect "3. Recall REST"
RECALL=$(curl -s -m 8 -X POST -H "Content-Type: application/json" \
	-d '{"query":"diagnostica setup hindsight check","limit":3}' \
	"$API_BASE/memories/recall" 2>/dev/null)
N=$(printf '%s' "$RECALL" | python -c "import json,sys; print(len(json.load(sys.stdin).get('results',[])))" 2>/dev/null || echo "?")
if [ "$N" != "?" ] && [ "$N" -ge 0 ] 2>/dev/null; then
	ok "recall ritorna risultati ben formati ($N memorie)"
else
	ko "recall fallito o response malformata"
	note "response: ${RECALL:0:200}"
fi

# 3b. min_scores (hindsight-api >=0.8.4): floor impossibile => 0 risultati.
# Guardia sul server installato: se min_scores fosse ignorato (api vecchia)
# tornerebbero le stesse memorie del check precedente.
MS_N=$(curl -s -m 8 -X POST -H "Content-Type: application/json" \
	-d '{"query":"diagnostica setup hindsight check","min_scores":{"final":9.9}}' \
	"$API_BASE/memories/recall" 2>/dev/null |
	python -c "import json,sys; print(len(json.load(sys.stdin).get('results',[])))" 2>/dev/null || echo "?")
if [ "$MS_N" = "0" ]; then
	ok "min_scores onorato dal server (floor impossibile → 0 risultati)"
elif [ "$MS_N" = "?" ]; then
	ko "recall con min_scores fallito o response malformata"
else
	ko "min_scores ignorato dal server ($MS_N risultati con floor 9.9) — serve hindsight-api >=0.8.4"
fi

# --- 4. TAGS PRESENTI ---
sect "4. Tag propagation (verifica retain ha tagato)"
TAGS=$(curl -s -m 3 "$API_BASE/tags?limit=20" 2>/dev/null |
	python -c "import json,sys; d=json.load(sys.stdin); print(' '.join(t.get('tag','') for t in d.get('items',[])))" 2>/dev/null)
for expected in "claude-code"; do
	if echo " $TAGS " | grep -q " $expected "; then
		ok "tag '$expected' presente nel bank"
	else
		ko "tag '$expected' assente — retain non ha mai tagato (nessun turno accodato allo Stop e' mai stato valutato al prompt successivo o nel drain della sentinella?)"
	fi
done
[ -n "$TAGS" ] && note "tutti i tag visti: $TAGS"

# --- 5. HOOK SCRIPT ESEGUIBILI ---
sect "5. Script hook"
for s in hindsight-recall.sh hindsight-retain.sh hindsight-retain-worker.py; do
	if [ -r "$HOOKS_DIR/$s" ]; then
		ok "$s presente e leggibile"
	else
		ko "$s mancante in $HOOKS_DIR/"
	fi
done

# --- 6. RECALL SEMPRE FRESCO ---
sect "6. Recall sempre fresco"
if grep -qE 'recall_cache_(dir|ttl)|HINDSIGHT_CACHE_(DIR|TTL)' "$HOOKS_DIR/hindsight-recall.sh" "$HOOKS_DIR/lib/hindsight_config.py"; then
	ko "cache dei risultati recall ancora presente nel codice di produzione"
else
	ok "nessuna cache dei risultati recall o delle classificazioni"
fi

# --- 7. HOOKS.JSON DEL PLUGIN ---
# Gli hook sono registrati in hooks/hooks.json del plugin (stesso formato della
# sezione "hooks" di settings.json), risolto relativo a questo script.
sect "7. Config hooks/hooks.json (plugin)"
HOOKSJSON="$HOOKS_DIR/../hooks.json"
if [ -r "$HOOKSJSON" ]; then
	if python -c "import json; json.load(open(r'$(w $HOOKSJSON)'))" 2>/dev/null; then
		ok "hooks.json valido"
		for hook in "hindsight-recall.sh" "hindsight-retain.sh"; do
			if grep -q "$hook" "$HOOKSJSON"; then
				ok "$hook registrato in hooks.json"
			else
				ko "$hook NON registrato in hooks.json"
			fi
		done
		# Da ICH-86 lo Stop hook non valuta piu' nulla: accoda il payload in
		# hs-retain-queue/ e risponde '{}'. Deve restare SINCRONO comunque:
		# l'enqueue deve essere completato prima che parta il prompt successivo,
		# altrimenti il gate differito dell'hook recall (retain_at_prompt ->
		# evaluate_queued) non troverebbe l'entry
		# (nessun decision:block da proteggere: conta solo l'ordine Stop -> UPS).
		RETAIN_ASYNC=$(python -c "
import json, sys
h = json.load(open(sys.argv[1], encoding='utf-8'))
flags = [hk.get('async', False)
         for grp in h['hooks'].get('Stop', [])
         for hk in grp.get('hooks', [])
         if 'hindsight-retain.sh' in hk.get('command', '')]
print(flags[0] if flags else 'missing')
" "$(w "$HOOKSJSON")" 2>/dev/null)
		if [ "$RETAIN_ASYNC" = "False" ]; then
			ok "retain hook sincrono (niente async — l'enqueue termina prima del prompt successivo)"
		else
			ko "retain hook con 'async: true' o entry assente ($RETAIN_ASYNC) — l'entry di coda potrebbe non esserci al prompt successivo"
		fi
	else
		ko "hooks.json non e' JSON valido"
	fi
else
	ko "hooks.json non leggibile"
fi

# --- 8. END-TO-END RECALL HOOK ---
sect "8. End-to-end: invoca recall hook"
# Col recall off l'hook esce senza hookSpecificOutput: e' l'interruttore master,
# non un guasto -> skip, come fa il 9b col retain.
RECALL_ON=$(PYTHONUTF8=1 python "$HOOKS_DIR/lib/hindsight_config.py" --get recall_enabled 2>/dev/null)
if [ "$RECALL_ON" = "False" ]; then
	skip "recall disabilitato (recall_enabled:false) — e2e recall hook non applicabile"
else
	PROBE='{"prompt":"diagnostica setup hindsight check end to end","cwd":"'"$PROJ"'","session_id":"check-test"}'
	START=$(date +%s%N)
	RESP=$(echo "$PROBE" | "$HOOKS_DIR/hindsight-recall.sh" 2>/dev/null)
	EL=$((($(date +%s%N) - START) / 1000000))
	if echo "$RESP" | python -c "import json,sys; d=json.load(sys.stdin); assert 'hookSpecificOutput' in d" 2>/dev/null; then
		ok "recall hook produce JSON valido in ${EL}ms"
	else
		ko "recall hook non produce JSON valido (response vuota o malformata)"
		note "primi 200 char: ${RESP:0:200}"
	fi
fi

# --- 9. END-TO-END RETAIN: Stop hook accoda, worker valuta (ICH-86) ---
sect "9. End-to-end: Stop hook (enqueue) + retain worker"
# 9a. Lo Stop hook e' puro enqueue: con un HOOK_INPUT deve scrivere ESATTAMENTE un
# file in $XDG_CACHE_HOME/trinity/hs-retain-queue/ (contenuto = payload verbatim)
# e stampare '{}'. XDG_CACHE_HOME temporanea: non si sporca la coda reale (una
# entry finta con session_id 'check-…' verrebbe valutata al drain della sentinella).
QTMP=$(mktemp -d /tmp/hs-queue-XXXXXX)
QPAYLOAD='{"session_id":"check-queue","transcript_path":"/nonexistent.jsonl","cwd":"/tmp","hook_event_name":"Stop"}'
QOUT=$(printf '%s' "$QPAYLOAD" | XDG_CACHE_HOME="$QTMP" bash "$HOOKS_DIR/hindsight-retain.sh" 2>/dev/null)
QFILES=$(ls "$QTMP/trinity/hs-retain-queue"/*.json 2>/dev/null | wc -l | tr -d ' ')
QBODY=$(cat "$QTMP"/trinity/hs-retain-queue/*.json 2>/dev/null)
if [ "$QOUT" = "{}" ] && [ "$QFILES" = "1" ] && [ "$QBODY" = "$QPAYLOAD" ]; then
	ok "Stop hook accoda un solo file (payload verbatim) e risponde '{}'"
else
	ko "Stop hook: output '${QOUT:0:40}', file in coda: $QFILES, payload verbatim: $([ "$QBODY" = "$QPAYLOAD" ] && echo si || echo no)"
fi
rm -rf "$QTMP"

# 9b. Il worker in modalita' script (senza flag) valuta $HOOK_INPUT in "deferred"
# esattamente come il gate differito lanciato da retain_at_prompt() nell'hook
# recall a UserPromptSubmit (evaluate_queued). I log '[retain]' vanno su stderr,
# HSGATE su stdout: il file di log raccoglie entrambi (2>&1).
# HS_RETAIN_FORCE bypassa il throttling ma NON l'interruttore master retain_enabled:
# col retain off il worker esce prima del POST, quindi l'e2e non e' applicabile -> skip.
RETAIN_ON=$(PYTHONUTF8=1 python "$HOOKS_DIR/lib/hindsight_config.py" --get retain_enabled 2>/dev/null)
if [ "$RETAIN_ON" = "False" ]; then
	skip "retain disabilitato (retain_enabled:false) — e2e retain worker non applicabile"
else
	FAKE=$(mktemp /tmp/hs-check-XXXXXX.jsonl)
	FAKE_WIN=$(w "$FAKE")
	WORKER_WIN_E2E="$(w "$HOOKS_DIR/hindsight-retain-worker.py")"
	cat >"$FAKE" <<EOF
{"type":"user","message":{"role":"user","content":"diagnostica check end-to-end del retain hook con prompt sufficientemente lungo"}}
{"type":"assistant","message":{"role":"assistant","content":[{"type":"text","text":"check OK"},{"type":"tool_use","name":"Bash","input":{"command":"git status"}}]}}
EOF
	RETAIN_PAYLOAD=$(python -c "import json; print(json.dumps({'session_id':'check-1234','transcript_path':r'$FAKE_WIN','cwd':r'$PROJ','hook_event_name':'UserPromptSubmit'}))")
	# Log della valutazione (stdout+stderr del worker), sotto HS_CACHE_DIR come gli
	# altri artefatti degli hook; il worker gira in foreground, niente sleep.
	RETAIN_LOG="${XDG_CACHE_HOME:-$HOME/.cache}/trinity/hs-retain.log"
	mkdir -p "$(dirname "$RETAIN_LOG")" 2>/dev/null
	>"$RETAIN_LOG"
	# HS_RETAIN_FORCE bypassa il throttling (step E) per testare il POST in modo
	# deterministico. Il gate semantico (ICH-67) e' FAIL-CLOSED da ICH-73: un
	# errore tecnico (es. OPENAI_API_KEY vuota) NON salva piu' nulla, quindi il
	# vecchio trucco della chiave svuotata darebbe check KO. Al suo posto uno stub
	# OpenAI locale (http.server su porta effimera, agganciato via HS_OPENAI_URL)
	# risponde a qualunque POST un verdetto "retain" con context valorizzato ->
	# la POST parte sempre. Con l'LLM vero l'esito dipenderebbe dal giudizio sul
	# contenuto sintetico (es. "skip: duplicate" ai run successivi) e il check
	# diventerebbe non deterministico. La porta la sceglie il kernel (bind su 0)
	# e lo stub la pubblica su file: si aspetta quel file (max ~5s) prima di
	# lanciare il worker; kill dello stub in ogni caso, anche su fallimento.
	STUB_PY=$(mktemp /tmp/hs-stub-XXXXXX.py)
	PORT_FILE=$(mktemp /tmp/hs-stub-port-XXXXXX)
	cat >"$STUB_PY" <<'PY'
import json, sys
from http.server import BaseHTTPRequestHandler, HTTPServer

VERDICT = json.dumps({
    "action": "retain", "reason": "durable_decision", "preview": "check e2e",
    "durable_claims": [], "covered_by": [],
    "context": "diagnostica end-to-end del retain hook nel plugin Trinity",
})
BODY = json.dumps({"choices": [{"message": {"content": VERDICT}}]}).encode("utf-8")


class Handler(BaseHTTPRequestHandler):
    def do_POST(self):
        self.rfile.read(int(self.headers.get("Content-Length") or 0))
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(BODY)))
        self.end_headers()
        self.wfile.write(BODY)

    def log_message(self, *args):
        pass


srv = HTTPServer(("127.0.0.1", 0), Handler)
with open(sys.argv[1], "w") as f:
    f.write(str(srv.server_address[1]))
srv.serve_forever()
PY
	python "$(w "$STUB_PY")" "$(w "$PORT_FILE")" >/dev/null 2>&1 &
	STUB_PID=$!
	for _ in $(seq 1 50); do [ -s "$PORT_FILE" ] && break; sleep 0.1; done
	STUB_PORT=$(tr -d '\r\n' <"$PORT_FILE" 2>/dev/null)
	if [ -z "$STUB_PORT" ]; then
		ko "stub OpenAI locale non partito (porta non pubblicata in 5s) — e2e retain saltato"
	else
		# HS_PY dal resolver condiviso (lo stesso interprete usato dagli hook); fallback
		# al python del PATH se il resolver non e' disponibile.
		HS_PY_E2E=$( (. "$HOOKS_DIR/lib/hs-python.sh" >/dev/null 2>&1 && printf '%s' "$HS_PY") 2>/dev/null)
		[ -n "$HS_PY_E2E" ] || HS_PY_E2E=python
		HOOK_INPUT="$RETAIN_PAYLOAD" HS_RETAIN_FORCE=1 OPENAI_API_KEY=check-stub \
			HS_OPENAI_URL="http://127.0.0.1:$STUB_PORT/v1/chat/completions" PYTHONUTF8=1 \
			"$HS_PY_E2E" "$WORKER_WIN_E2E" >"$RETAIN_LOG" 2>&1
		if grep -q "\[retain\] OK 200" "$RETAIN_LOG" 2>/dev/null; then
			ok "retain worker (deferred) OK (log: $(grep -m1 'OK 200' "$RETAIN_LOG" | head -c 120))"
		else
			ko "retain worker non ha scritto OK 200 in $RETAIN_LOG"
			note "log: $(cat "$RETAIN_LOG" 2>/dev/null | head -3)"
		fi
	fi
	kill "$STUB_PID" 2>/dev/null
	wait "$STUB_PID" 2>/dev/null
	rm -f "$FAKE" "$STUB_PY" "$PORT_FILE"
fi

# --- 11. BANK MISSION (retain_mission + reflect_mission impostate) ---
sect "11. Bank mission (step B)"
MISSION_JSON=$(curl -s -m 5 "$API_BASE/config" 2>/dev/null)
for field in retain_mission reflect_mission; do
	LEN=$(printf '%s' "$MISSION_JSON" | FIELD="$field" python -c "import json,os,sys; c=json.load(sys.stdin).get('config',{}); v=c.get(os.environ['FIELD']) or ''; print(len(v))" 2>/dev/null || echo 0)
	if [ "$LEN" -gt 0 ] 2>/dev/null; then
		ok "$field impostata sul bank ($LEN char)"
	else
		ko "$field NON impostata — esegui: bash hooks/hindsight/ops/hindsight-set-mission.sh"
	fi
done

# --- 16. MENTAL MODELS / KNOWLEDGE PAGES (step G) ---
sect "16. Mental models — knowledge pages (step G)"

MM_HTTP=$(curl -s -m 3 -o /dev/null -w "%{http_code}" "$API_BASE/mental-models" 2>/dev/null || echo "000")
if [ "$MM_HTTP" = "200" ]; then
	ok "endpoint /mental-models risponde (HTTP 200)"
else
	ko "endpoint /mental-models → HTTP $MM_HTTP (atteso 200)"
fi

MM_CFG=$(
	PYTHONUTF8=1 python - "$HOOKS_DIR/lib" <<'PY' 2>/dev/null
import sys
sys.path.insert(0, sys.argv[1])
import hindsight_config as hc
mm = hc.load_config().get("mental_models") or []
ids = {m.get("id") for m in mm}
want = {"user-profile", "project-conventions", "recurring-learnings"}
print("OK" if want <= ids else "KO")
PY
)
if [ "$MM_CFG" = "OK" ]; then
	ok "load_config carica le 3 definizioni knowledge page"
else
	ko "definizioni mental_models mancanti in config ($MM_CFG)"
fi

# Multi-bank (ICH-77): mental_model_inject_banks deve avere la FORMA attesa
# (lista non vuota di stringhe): e' ancora letta da hindsight-mm-inject.sh.
MM_BANKS=$(
	PYTHONUTF8=1 python - "$HOOKS_DIR/lib" <<'PY' 2>/dev/null
import sys
sys.path.insert(0, sys.argv[1])
import hindsight_config as hc
banks = hc.load_config().get("mental_model_inject_banks")
print("OK" if isinstance(banks, list) and banks and all(isinstance(b, str) for b in banks) else "KO")
PY
)
if [ "$MM_BANKS" = "OK" ]; then
	ok "mental_model_inject_banks ha la forma attesa"
else
	ko "mental_model_inject_banks malformata ($MM_BANKS)"
fi

MM_LIVE=$(curl -s -m 5 "$API_BASE/mental-models" 2>/dev/null | python -c "
import json,sys
ids={i.get('id') for i in json.load(sys.stdin).get('items',[])}
want={'user-profile','project-conventions','recurring-learnings'}
print('OK' if want<=ids else 'KO')
" 2>/dev/null || echo "KO")
if [ "$MM_LIVE" = "OK" ]; then
	ok "le 3 knowledge page esistono sul bank (seed ok)"
else
	ko "knowledge page mancanti — esegui: bash hooks/hindsight/ops/hindsight-mental-models.sh seed"
fi

# Pin del cwd al root del plugin: lo script ops risolve il bank dal cwd, e se il
# check gira dal cwd di un progetto NON deve seminare/leggere il SUO bank (side
# effect indesiderato di una verifica) ma sempre quello core del plugin.
RESEED=$(cd "$HOOKS_DIR/../.." && bash hooks/hindsight/ops/hindsight-mental-models.sh seed 2>/dev/null | grep -c "^+ creato" || true)
if [ "$RESEED" = "0" ]; then
	ok "seed idempotente (nessuna pagina ri-creata)"
else
	ko "seed NON idempotente ($RESEED pagine ri-create)"
fi

SHOW_LEN=$(cd "$HOOKS_DIR/../.." && bash hooks/hindsight/ops/hindsight-mental-models.sh show user-profile 2>/dev/null | wc -c)
if [ "$SHOW_LEN" -gt 200 ] 2>/dev/null; then
	ok "show user-profile ritorna contenuto generato ($SHOW_LEN char)"
else
	ko "show user-profile vuoto/troppo corto ($SHOW_LEN char)"
fi

# Gating deterministico: forziamo il flag OFF via env (simmetrico allo step ON
# sotto, che lo forza a 1), cosi' il test valida il MECCANISMO di gating a
# prescindere dal valore in config.json — che l'utente puo' legittimamente avere
# a true per iniettare i mental model a SessionStart.
INJ_OFF=$(echo '{"hook_event_name":"SessionStart"}' | HS_CFG_MENTAL_MODELS_INJECT_ON_START=0 bash "$HOOKS_DIR/hindsight-mm-inject.sh" 2>/dev/null)
if [ -z "$INJ_OFF" ]; then
	ok "inject hook silente con flag OFF (gating deterministico via env)"
else
	ko "inject hook produce output con flag OFF (dovrebbe essere gated)"
fi

INJ_ON=$(echo '{"hook_event_name":"SessionStart"}' | HS_CFG_MENTAL_MODELS_INJECT_ON_START=1 bash "$HOOKS_DIR/hindsight-mm-inject.sh" 2>/dev/null | python -c "
import json,sys
d=json.load(sys.stdin)['hookSpecificOutput']
c=d['additionalContext']
print('OK' if d['hookEventName']=='SessionStart' and c.startswith('## Hindsight knowledge pages') else 'KO')
" 2>/dev/null || echo "KO")
if [ "$INJ_ON" = "OK" ]; then
	ok "inject hook con flag ON produce additionalContext valido"
else
	ko "inject hook con flag ON malformato ($INJ_ON)"
fi

# Budget del blocco iniettato: Claude Code tronca l'output hook oltre 10.000 char
# (inline resta solo un preview ~2KB), quindi mm-inject deve cappare il blocco a
# mental_models_inject_max_chars SENZA mai tagliare il trailer anti-feedback-loop
# (e' l'ancora con cui strip_memory_block scarta il blocco nel retain). Budget
# forzato basso via env cosi' il taglio scatta a prescindere dai contenuti reali.
INJ_CAP=$(echo '{"hook_event_name":"SessionStart"}' |
	HS_CFG_MENTAL_MODELS_INJECT_ON_START=1 HS_CFG_MENTAL_MODELS_INJECT_MAX_CHARS=3000 \
		bash "$HOOKS_DIR/hindsight-mm-inject.sh" 2>/dev/null | python -c "
import json,sys
c=json.load(sys.stdin)['hookSpecificOutput']['additionalContext']
cap_ok = len(c) <= 3000
trailer_ok = c.endswith('Use as consultative context. Verify mutable facts against the repo.')
header_ok = c.startswith('## Hindsight knowledge pages')
print('OK' if cap_ok and trailer_ok and header_ok
      else f'KO len={len(c)} cap={cap_ok} trailer={trailer_ok} header={header_ok}')
" 2>/dev/null || echo "KO")
if [ "$INJ_CAP" = "OK" ]; then
	ok "inject hook rispetta il budget char e preserva header+trailer (anti-loop)"
else
	ko "inject hook non cappa il blocco o taglia il trailer ($INJ_CAP)"
fi

WORKER_WIN="$(w "$HOOKS_DIR/hindsight-retain-worker.py")"
KP_STRIP=$(
	PYTHONUTF8=1 python - "$WORKER_WIN" <<'PY' 2>/dev/null
import sys, importlib.util
spec = importlib.util.spec_from_file_location("w2", sys.argv[1])
w = importlib.util.module_from_spec(spec)
spec.loader.exec_module(w)
block = (
    "## Hindsight knowledge pages (advisory, auto-maintained)\n\n"
    "### User Profile\n\nSphynx usa MSYS2.\n\n"
    "Use as consultative context. Verify mutable facts against the repo."
)
debug_block = (
    "## Hindsight recall debug\n\nModel: gpt-5.6-luna\n\n"
    "Memorie effettivamente iniettate:\n- [bypass] fatto\n\n"
    "Use as consultative context. Verify mutable facts against the repo."
)
legit = "Ho aggiunto le knowledge page al sistema."
out = w.strip_memory_block(block + "\n\n" + debug_block + "\n\n" + legit)
print("OK" if ("knowledge pages" not in out) and ("recall debug" not in out) and (legit in out) else "KO")
PY
)
if [ "$KP_STRIP" = "OK" ]; then
	ok "strip_memory_block rimuove anche il blocco knowledge pages (anti-loop)"
else
	ko "blocco knowledge pages NON rimosso dal retain (feedback-loop possibile)"
fi

if python -c "
import json,sys
h=json.load(open(sys.argv[1]))['hooks'].get('SessionStart',[])
cmds=[c.get('command','') for g in h for c in g.get('hooks',[])]
sys.exit(0 if any('hindsight-mm-inject.sh' in c for c in cmds) else 1)
" "$(w "$HOOKSJSON")" 2>/dev/null; then
	ok "SessionStart registra hindsight-mm-inject.sh"
else
	ko "hindsight-mm-inject.sh assente da SessionStart in hooks.json"
fi

# --- 17. DEBUG LOG (modalita debug opzionale) ---
sect "17. Debug log — modalita debug opzionale"

# Verifica il default SPEDITO (DEFAULTS), non la scelta runtime in config.json:
# il codice non deve loggare a meno che l'utente non lo accenda esplicitamente.
DBG_DEFAULT=$(
	PYTHONUTF8=1 python - "$HOOKS_DIR/lib" <<'PY' 2>/dev/null
import sys

sys.path.insert(0, sys.argv[1])
import hindsight_config as hc

print(hc.DEFAULTS["debug_log_enabled"])
PY
)
if [ "$DBG_DEFAULT" = "False" ]; then
	ok "debug_log_enabled e' OFF nei DEFAULTS spediti"
else
	ko "debug_log_enabled NON e' OFF nei DEFAULTS ($DBG_DEFAULT) — il codice non deve loggare di default"
fi

DBG_PATH=$(
	PYTHONUTF8=1 python - "$HOOKS_DIR/lib" <<'PY' 2>/dev/null
import sys

sys.path.insert(0, sys.argv[1])
import hindsight_debug as d

print(d._log_path({}))
PY
)
# Normalizza i backslash: col python nativo Windows nel PATH os.path.join
# produce separatori '\' e il pattern a forward slash non matcherebbe mai.
case "${DBG_PATH//\\//}" in
*/logs/hindsight-debug.log) ok "path default del log → $DBG_PATH" ;;
*) ko "path default del log inatteso ($DBG_PATH)" ;;
esac

DBG_TMP="$PROJ/test/hs-debug-check.log"
DBG_TMP_WIN="$(w "$DBG_TMP")"
rm -f "$DBG_TMP"
# Prompt corto = path recall_skip: niente chiamata al server, test veloce.
# Forziamo OFF via env per testare il no-op a prescindere dal flag in config.json.
echo '{"prompt":"ok"}' | HS_CFG_DEBUG_LOG_ENABLED=0 HS_CFG_DEBUG_LOG_FILE="$DBG_TMP_WIN" bash "$HOOKS_DIR/hindsight-recall.sh" >/dev/null 2>&1
if [ -f "$DBG_TMP" ]; then
	ko "debug OFF ma il log e' stato scritto"
else
	ok "debug OFF: nessun log scritto (no-op)"
fi

echo '{"prompt":"ok"}' | HS_CFG_DEBUG_LOG_ENABLED=1 HS_CFG_DEBUG_LOG_FILE="$DBG_TMP_WIN" bash "$HOOKS_DIR/hindsight-recall.sh" >/dev/null 2>&1
if [ -s "$DBG_TMP" ] && grep -q '"event": "recall_skip"' "$DBG_TMP"; then
	ok "debug ON: evento JSONL scritto su file"
else
	ko "debug ON: log mancante o senza evento atteso"
fi
rm -f "$DBG_TMP"

# --- SUMMARY ---
sect "Riepilogo"
TOT=$((PASS + FAIL))
printf "  %d/%d check passati" "$PASS" "$TOT"
[ "$SKIP" -gt 0 ] && printf " (%d saltati)" "$SKIP"
printf "\n"
if [ "$FAIL" -eq 0 ]; then
	printf "  \033[32m✓ Tutto OK — al prossimo riavvio funzionera' tutto\033[0m\n"
	exit 0
else
	printf "  \033[31m✗ %d problemi da risolvere\033[0m\n" "$FAIL"
	exit 1
fi
