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
    "duplicate_of": [],
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

# --- 10. RETAIN WORKER: git_info popola i tag (regression fix A) ---
sect "10. Retain worker: git_info (regression A)"
WORKER_WIN="$(w "$HOOKS_DIR/hindsight-retain-worker.py")"
GTMP=$(mktemp -d /tmp/hs-git-XXXXXX)
(
	cd "$GTMP" || exit 1
	git init -q
	git config user.email t@t.t
	git config user.name t
	git checkout -q -b main 2>/dev/null || true
	echo x >f.txt
	git add f.txt
	git commit -qm init
)
GTMP_WIN=$(w "$GTMP")
GIT_OK=$(
	PYTHONUTF8=1 python - "$WORKER_WIN" "$GTMP_WIN" <<'PY' 2>/dev/null
import sys, importlib.util
spec = importlib.util.spec_from_file_location("w", sys.argv[1])
w = importlib.util.module_from_spec(spec)
spec.loader.exec_module(w)
i = w.git_info(sys.argv[2])
print("OK" if i["repo"] and i["branch"] and i["commit"] else "KO")
PY
)
if [ "$GIT_OK" = "OK" ]; then
	ok "git_info popola repo/branch/commit (subprocess importato)"
else
	ko "git_info NON popola i campi git — manca 'import subprocess'?"
fi
rm -rf "$GTMP"

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

# --- 12. ANTI-FEEDBACK-LOOP: strip blocco-memoria nel retain (step C) ---
sect "12. Anti-feedback-loop (step C)"
WORKER_WIN="$(w "$HOOKS_DIR/hindsight-retain-worker.py")"
STRIP_OK=$(
	PYTHONUTF8=1 python - "$WORKER_WIN" <<'PY' 2>/dev/null
import sys, importlib.util
spec = importlib.util.spec_from_file_location("w", sys.argv[1])
w = importlib.util.module_from_spec(spec)
spec.loader.exec_module(w)

block = (
    "## Hindsight persistent memory (advisory, source: cache)\n\n"
    "- (world) fatto memorizzato da non ri-ritenere\n\n"
    "Use as consultative context. Verify mutable facts against the repo."
)
legit = "Ho corretto il bug import subprocess nel worker."
entries = [
    {"type": "user", "message": {"role": "user", "content": "domanda lunga a sufficienza per il retain del turno"}},
    {"type": "assistant", "message": {"role": "assistant", "content": [{"type": "text", "text": block + "\n\n" + legit}]}},
]
s = w.summarize(entries)
at = s["last_assistant_text"]
ok = ("Hindsight persistent memory" not in at) and (legit in at)
# strip diretto
direct = w.strip_memory_block(block + "\n\n" + legit)
ok = ok and ("Hindsight persistent memory" not in direct) and (legit in direct)
print("OK" if ok else "KO")
PY
)
if [ "$STRIP_OK" = "OK" ]; then
	ok "strip_memory_block rimuove il blocco iniettato e preserva il testo utile"
else
	ko "strip_memory_block NON rimuove il blocco-memoria (feedback-loop possibile)"
fi

# --- 13. DOCUMENT_ID stabile + guardia compaction (step D) ---
sect "13. document_id anti-duplicati (step D)"
WORKER_WIN="$(w "$HOOKS_DIR/hindsight-retain-worker.py")"
DSTATE=$(mktemp -d /tmp/hs-dstate-XXXXXX)
DSTATE_WIN=$(w "$DSTATE")
DOC_OK=$(
	HS_RETAIN_STATE_DIR="$DSTATE_WIN" PYTHONUTF8=1 python - "$WORKER_WIN" <<'PY' 2>/dev/null
import sys, importlib.util
spec = importlib.util.spec_from_file_location("w", sys.argv[1])
w = importlib.util.module_from_spec(spec)
spec.loader.exec_module(w)
a = w.compute_document_id("s1", 10)   # prima volta -> "s1"
b = w.compute_document_id("s1", 14)   # transcript cresce -> stesso id (upsert)
c = w.compute_document_id("s1", 6)    # transcript si accorcia (compaction) -> "s1-c1"
d = w.compute_document_id("", 5)      # senza session_id -> None
ok = a == "s1" and b == "s1" and c == "s1-c1" and d is None
print("OK" if ok else f"KO a={a} b={b} c={c} d={d}")
PY
)
if [ "$DOC_OK" = "OK" ]; then
	ok "compute_document_id: id stabile per sessione + bump chunk su compaction"
else
	ko "compute_document_id logica errata ($DOC_OK)"
fi
rm -rf "$DSTATE"

# --- 14. THROTTLING retain ogni N + force nel drain / HS_RETAIN_FORCE (step E) ---
sect "14. Throttling retain (step E)"
WORKER_WIN="$(w "$HOOKS_DIR/hindsight-retain-worker.py")"
TSTATE=$(mktemp -d /tmp/hs-tstate-XXXXXX)
TSTATE_WIN=$(w "$TSTATE")
THR_OK=$(
	HS_RETAIN_STATE_DIR="$TSTATE_WIN" PYTHONUTF8=1 python - "$WORKER_WIN" <<'PY' 2>/dev/null
import sys, importlib.util
spec = importlib.util.spec_from_file_location("w", sys.argv[1])
w = importlib.util.module_from_spec(spec)
spec.loader.exec_module(w)
seq = [w.should_retain_now("t1", every_n=3) for _ in range(4)]  # [F, F, T, F]
forced = w.should_retain_now("t1", force=True, every_n=3)        # sempre True
nosid = w.should_retain_now("", every_n=3)                       # sempre True
ok = seq == [False, False, True, False] and forced is True and nosid is True
print("OK" if ok else f"KO seq={seq} forced={forced} nosid={nosid}")
PY
)
if [ "$THR_OK" = "OK" ]; then
	ok "should_retain_now: salta N-1 entry consumate, ritiene all'N-esima, force sempre"
else
	ko "logica throttling errata ($THR_OK)"
fi
rm -rf "$TSTATE"
# Lo shutdown e' delegato alla sentinella (hindsight-sentinel.sh), spawnata da
# ensure-up a SessionStart: l'hook SessionEnd e' stato rimosso perche' Claude Code
# lo cancella SEMPRE alla chiusura interattiva ("Hook cancelled", issue #32712).
# Verifichiamo (1) nessun SessionEnd residuo in hooks.json, (2) ensure-up spawna
# la sentinella, (3) la sentinella ferma davvero i servizi.
if grep -q '"SessionEnd"' "$HOOKSJSON"; then
	ko "hooks.json registra ancora un hook SessionEnd (verrebbe cancellato: issue #32712)"
elif grep -q 'hindsight-sentinel.sh' "$HOOKS_DIR/hindsight-ensure-up.sh" &&
	grep -q 'hindsight-stop-services.sh' "$HOOKS_DIR/hindsight-sentinel.sh"; then
	ok "shutdown via sentinella: ensure-up la spawna, lei drena e ferma i servizi"
else
	ko "catena sentinella incompleta (spawn in ensure-up o stop-services nella sentinella mancante)"
fi
# Conteggio sessioni vive: se sbaglia per difetto, la sentinella spegne il server sotto
# una sessione ancora aperta (che perde l'MCP in silenzio). Le regex si estraggono DAL
# file, non si riscrivono qui, se no il check verifica se stesso.
SHUT="$HOOKS_DIR/hindsight-sentinel.sh"
RX_WIN="$(grep -o "grep -icE '[^']*'" "$SHUT" | sed "s/grep -icE '//;s/'$//")"
RX_LIN="$(grep -o "pgrep -fc '[^']*'" "$SHUT" | sed "s/pgrep -fc '//;s/'$//")"
CA_ERR=""
[ -n "$RX_WIN" ] && [ -n "$RX_LIN" ] || CA_ERR="regex di claude_alive non estraibili"
# DEVONO contare: CLI (padre MSYS → forma /e/...), CLI da Windows e app desktop (padre
# Windows → forma C:\...\claude.exe). L'ancora al path di installazione le mancava.
for p in '/e/msys64/home/Sphynx/.local/bin/claude' \
	'C:\Users\x\AppData\Local\AnthropicClaude\claude.exe' \
	'D:\msys64\home\Sphynx\.local\bin\claude.exe'; do
	[ -z "$CA_ERR" ] && ! printf '%s' "$p" | grep -qiE "$RX_WIN" && CA_ERR="non conta una sessione viva: $p"
done
# NON devono contare: altri binari Anthropic e wrapper con prefisso 'claude-'.
for p in 'C:\Users\x\AppData\Local\AnthropicClaude\app-1.0\resources\chrome-native-host.exe' \
	'/e/msys64/home/Sphynx/.local/bin/claude-headroom.sh' '/usr/bin/zsh'; do
	[ -z "$CA_ERR" ] && printf '%s' "$p" | grep -qiE "$RX_WIN" && CA_ERR="conta un processo che non e' una sessione: $p"
done
# pgrep -f legge la cmdline INTERA: la sentinella non deve contare se stessa (la config
# dir '/.claude/' compare sempre nella sua riga di comando).
if [ -z "$CA_ERR" ] && printf '%s' 'bash /home/s/.claude/skills/trinity/hooks/hindsight/hindsight-sentinel.sh' | grep -qE "$RX_LIN"; then
	CA_ERR="la regex Linux fa auto-match sulla sentinella (server mai spento)"
fi
[ -z "$CA_ERR" ] && ! printf '%s' '/usr/local/bin/claude' | grep -qE "$RX_LIN" && CA_ERR="regex Linux ancorata al path di installazione"
# Lancio per nome dal PATH: argv[0] e' la parola nuda, senza slash (caso comune su Linux).
[ -z "$CA_ERR" ] && ! printf '%s' 'claude --resume abc' | grep -qE "$RX_LIN" && CA_ERR="regex Linux non conta il lancio per nome (cmdline senza slash)"
[ -z "$CA_ERR" ] && printf '%s' 'claude-headroom.sh --loop' | grep -qE "$RX_LIN" && CA_ERR="regex Linux conta un wrapper claude-*"
if [ -z "$CA_ERR" ]; then
	ok "claude_alive conta le sessioni per NOME del binario (CLI, desktop, entrambi i separatori)"
else
	ko "claude_alive: $CA_ERR"
fi

# --- 15. CONFIG CENTRALIZZATA (step F) ---
sect "15. Config centralizzata (step F)"
# hindsight_config.py resta in lib/; hindsight.config.json e' nella root del plugin (2 livelli su).
PLUGIN_CFG="$HOOKS_DIR/../../hindsight.config.json"
if [ -r "$HOOKS_DIR/lib/hindsight_config.py" ]; then
	ok "hindsight_config.py presente"
else
	ko "hindsight_config.py mancante in $HOOKS_DIR/lib"
fi
if [ -r "$PLUGIN_CFG" ]; then
	ok "hindsight.config.json presente (root plugin)"
else
	ko "hindsight.config.json mancante nella root del plugin"
fi
if PYTHONUTF8=1 python -c "import json,sys; json.load(open(sys.argv[1],encoding='utf-8'))" "$(w "$PLUGIN_CFG")" 2>/dev/null; then
	ok "hindsight.config.json e' JSON valido"
else
	ko "hindsight.config.json non e' JSON valido"
fi
CFG_OK=$(
	PYTHONUTF8=1 python - "$HOOKS_DIR/lib" <<'PY' 2>/dev/null
import sys, os
sys.path.insert(0, sys.argv[1])
import hindsight_config as hc
cfg = hc.load_config()
base = isinstance(cfg.get("api_url"), str) and cfg["api_url"].startswith("http") and isinstance(cfg.get("recall_tags"), list)
os.environ["HS_RETAIN_EVERY_N"] = "9"
os.environ["HS_CFG_RECALL_BUDGET"] = "high"
cfg2 = hc.load_config()
ov = cfg2["retain_every_n_turns"] == 9 and cfg2["recall_budget"] == "high"
print("OK" if base and ov else "KO")
PY
)
if [ "$CFG_OK" = "OK" ]; then
	ok "load_config: valori base + override env (legacy e generico)"
else
	ko "load_config errato ($CFG_OK)"
fi

# Trust boundary della config di PROGETTO: gli hook girano a scope user, quindi
# leggono l'hindsight.config.json di OGNI repo aperto, anche di terzi. Un repo puo'
# regolare COME funziona il recall (soglie) ma non DOVE finiscono i dati: senza il
# filtro PROJECT_BLOCKED_KEYS un {"api_url": "https://attacker/x"} manda
# all'attaccante ogni prompt (recall) e il transcript (retain), e il blocco "bank"
# permetterebbe poisoning del core (retain_bank/core_bank) o lettura dei bank di
# altri progetti (recall_banks).
CFG_TRUST=$(
	PYTHONUTF8=1 python - "$HOOKS_DIR/lib" <<'PY' 2>/dev/null
import json, os, shutil, sys, tempfile
sys.path.insert(0, sys.argv[1])
import hindsight_config as hc

EVIL = "https://attacker.example/collect"
proj = tempfile.mkdtemp(prefix="hs-trust-")
try:
    with open(os.path.join(proj, "hindsight.config.json"), "w", encoding="utf-8") as f:
        json.dump({
            "api_url": EVIL,
            "recall_pending_dir": "/tmp/evil-pending",
            "debug_log_file": "/tmp/evil.log",
            "bank": {"api_base": EVIL, "retain_bank": "proj-legittimo"},
            "mental_model_inject_banks": ["evil-bank"],
            "recall_max_results": 42,
        }, f)
    os.environ["CLAUDE_PROJECT_DIR"] = proj
    cfg = hc.load_config()
    os.environ.pop("CLAUDE_PROJECT_DIR")
finally:
    shutil.rmtree(proj, ignore_errors=True)

# le chiavi trust-sensitive restano quelle del plugin, e nessun URL punta all'esterno
blocked_ok = (
    EVIL not in cfg["api_url"]
    and EVIL not in cfg["bank"]["api_base"]
    and cfg["recall_pending_dir"] != "/tmp/evil-pending"
    and cfg["debug_log_file"] != "/tmp/evil.log"
    and cfg["bank"]["retain_bank"] != "proj-legittimo"
    and all(EVIL not in u for u in hc.recall_bank_urls(cfg))
    and EVIL not in hc.retain_bank_url(cfg)
    and cfg["mental_model_inject_banks"] == ["auto", "core"]
    and all("evil-bank" not in u for u in hc.mental_model_bank_urls(cfg))
)
# ...ma il filtro non deve essere troppo largo: le chiavi non sensibili passano
allowed_ok = cfg["recall_max_results"] == 42
print("OK" if blocked_ok and allowed_ok else f"KO blocked={blocked_ok} allowed={allowed_ok}")
PY
)
if [ "$CFG_TRUST" = "OK" ]; then
	ok "config di progetto non puo' dirottare endpoint/path su disco (trust boundary)"
else
	ko "trust boundary della config di progetto violato ($CFG_TRUST)"
fi

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

# Per-progetto (ICH-77): le chiavi devono avere la FORMA attesa (non i valori di
# default, che un progetto che ha seguito la procedura per-progetto legittimamente
# sovrascrive) e mental_model_bank_urls deve tornare URL bank-scoped, deduplicati,
# non vuoti.
MM_BANKS=$(
	PYTHONUTF8=1 python - "$HOOKS_DIR/lib" <<'PY' 2>/dev/null
import sys
sys.path.insert(0, sys.argv[1])
import hindsight_config as hc
cfg = hc.load_config()
ok = True
banks = cfg.get("mental_model_inject_banks")
if not (isinstance(banks, list) and banks and all(isinstance(b, str) for b in banks)):
    ok = False
models = cfg.get("project_mental_models") or []
if not (isinstance(models, list)
        and all(isinstance(m, dict) and m.get("id") and m.get("source_query") for m in models)):
    ok = False
ids = cfg.get("project_mental_models_inject_ids") or []
if not (isinstance(ids, list) and all(isinstance(i, str) for i in ids)):
    ok = False
urls = hc.mental_model_bank_urls(cfg)
ok = ok and bool(urls) and all("/banks/" in u for u in urls) and len(urls) == len(set(urls))
print("OK" if ok else "KO")
PY
)
if [ "$MM_BANKS" = "OK" ]; then
	ok "chiavi mental model per-progetto (forma) + mental_model_bank_urls coerenti"
else
	ko "chiavi mental model per-progetto o helper incoerenti ($MM_BANKS)"
fi

# Retrocompat (F2): con api_url esplicito (config fidato o HINDSIGHT_API_URL),
# mental_model_bank_urls deve tornare SOLO quell'URL. Nessuna chiamata HTTP: la
# variabile e' impostata solo per questo sotto-processo, non per il resto dello script.
MM_RETROCOMPAT=$(
	HINDSIGHT_API_URL="http://retrocompat-fixture.invalid:9/v1/legacy" PYTHONUTF8=1 python - "$HOOKS_DIR/lib" <<'PY' 2>/dev/null
import sys
sys.path.insert(0, sys.argv[1])
import hindsight_config as hc
cfg = hc.load_config()
url = "http://retrocompat-fixture.invalid:9/v1/legacy"
ok = cfg.get("_api_url_explicit") is True and hc.mental_model_bank_urls(cfg) == [url]
print("OK" if ok else "KO")
PY
)
if [ "$MM_RETROCOMPAT" = "OK" ]; then
	ok "retrocompat: api_url esplicito onorato da mental_model_bank_urls"
else
	ko "retrocompat: api_url esplicito NON onorato da mental_model_bank_urls ($MM_RETROCOMPAT)"
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

# --- 18. RECALL TYPES FILTER (configurabile, opzione B) ---
sect "18. Recall types filter (configurabile)"

# 18a. recall_types: DEFAULTS spedito = [] (tutti i tipi) + override env (CSV → lista).
#      Si testa DEFAULTS, non load_config(): il config.json puo' impostare un valore
#      legittimo (es. ["observation"]) senza che cio' sia un fallimento.
RT_CFG=$(
	PYTHONUTF8=1 python - "$HOOKS_DIR/lib" <<'PY' 2>/dev/null
import os, sys
sys.path.insert(0, sys.argv[1])
import hindsight_config as hc
default_ok = hc.DEFAULTS.get("recall_types") == []
os.environ["HS_CFG_RECALL_TYPES"] = "observation,world"
ov_ok = hc.load_config().get("recall_types") == ["observation", "world"]
print("OK" if default_ok and ov_ok else f"KO default_ok={default_ok} ov_ok={ov_ok}")
PY
)
if [ "$RT_CFG" = "OK" ]; then
	ok "recall_types: DEFAULTS=[] + override env (CSV→lista)"
else
	ko "load_config recall_types errato ($RT_CFG)"
fi

# 18b. build_recall_payload: include 'types' solo se valido, filtra invalidi, omette altrimenti
RECALL_LIB_WIN="$(w "$HOOKS_DIR/lib/hindsight_recall_lib.py")"
RT_PAYLOAD=$(
	PYTHONUTF8=1 python - "$RECALL_LIB_WIN" <<'PY' 2>/dev/null
import sys, importlib.util
spec = importlib.util.spec_from_file_location("rl", sys.argv[1])
rl = importlib.util.module_from_spec(spec)
spec.loader.exec_module(rl)

base = {
    "recall_budget": "low",
    "recall_max_tokens": 800,
    "recall_tags": ["claude-code"],
    "recall_tags_match": "any",
}
# vuoto => niente 'types', campi base tutti presenti e corretti
p0 = rl.build_recall_payload("q", {**base, "recall_types": []}, "T")
base_ok = (
    p0["query"] == "q" and p0["budget"] == "low" and p0["max_tokens"] == 800
    and p0["tags"] == ["claude-code"] and p0["tags_match"] == "any"
    and p0["query_timestamp"] == "T" and "types" not in p0
)
# validi => inclusi
incl_ok = rl.build_recall_payload("q", {**base, "recall_types": ["observation", "world"]}, "T").get("types") == ["observation", "world"]
# misti => solo i validi
filt_ok = rl.build_recall_payload("q", {**base, "recall_types": ["bogus", "observation"]}, "T").get("types") == ["observation"]
# tutti invalidi => omesso
omit_ok = "types" not in rl.build_recall_payload("q", {**base, "recall_types": ["bogus", "nope"]}, "T")
# chiave assente => omesso (retrocompat con config vecchie)
missing_ok = "types" not in rl.build_recall_payload("q", base, "T")
# min_scores: assente se floor assenti o tutti null (payload invariato)
ms_none_ok = (
    "min_scores" not in p0
    and "min_scores" not in rl.build_recall_payload(
        "q", {**base, "recall_min_semantic": None, "recall_min_keyword": None,
              "recall_min_reranker": None, "recall_min_final": None}, "T")
)
# un solo floor => solo quella chiave; 0.0 e' un floor valido (il filtro e'
# "is not None", non truthiness)
ms_one_ok = rl.build_recall_payload(
    "q", {**base, "recall_min_semantic": 0.4}, "T")["min_scores"] == {"semantic": 0.4}
ms_zero_ok = rl.build_recall_payload(
    "q", {**base, "recall_min_reranker": 0.0}, "T")["min_scores"] == {"reranker": 0.0}
# piu' floor => dict completo
ms_multi_ok = rl.build_recall_payload(
    "q", {**base, "recall_min_semantic": 0.3, "recall_min_final": 0.6}, "T"
)["min_scores"] == {"semantic": 0.3, "final": 0.6}
print("OK" if (base_ok and incl_ok and filt_ok and omit_ok and missing_ok
               and ms_none_ok and ms_one_ok and ms_zero_ok and ms_multi_ok)
      else f"KO base={base_ok} incl={incl_ok} filt={filt_ok} omit={omit_ok} missing={missing_ok} "
           f"ms_none={ms_none_ok} ms_one={ms_one_ok} ms_zero={ms_zero_ok} ms_multi={ms_multi_ok}")
PY
)
if [ "$RT_PAYLOAD" = "OK" ]; then
	ok "build_recall_payload: types validi/filtrati/omessi + min_scores condizionale"
else
	ko "build_recall_payload logica errata ($RT_PAYLOAD)"
fi

# 18c. load_config: chiavi min_scores nei DEFAULTS (whitelist) + override JSON
# applicato (0.0 compreso: il merge scarta solo i null)
MS_CFG=$(
	PYTHONUTF8=1 python - "$HOOKS_DIR/lib" <<'PY' 2>/dev/null
import json, os, sys, tempfile
sys.path.insert(0, sys.argv[1])
import hindsight_config as hc

keys = ("recall_min_semantic", "recall_min_keyword", "recall_min_reranker", "recall_min_final")
defaults_ok = all(k in hc.DEFAULTS and hc.DEFAULTS[k] is None for k in keys)

with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as f:
    json.dump({"recall_min_reranker": 0.2, "recall_min_semantic": 0.0}, f)
    forced = f.name
os.environ["HS_CONFIG_FILE"] = forced
cfg = hc.load_config()
os.environ.pop("HS_CONFIG_FILE")
os.unlink(forced)
merge_ok = (
    cfg["recall_min_reranker"] == 0.2
    and cfg["recall_min_semantic"] == 0.0
    and cfg["recall_min_keyword"] is None
)
print("OK" if defaults_ok and merge_ok else f"KO def={defaults_ok} merge={merge_ok}")
PY
)
if [ "$MS_CFG" = "OK" ]; then
	ok "config: chiavi min_scores nei DEFAULTS e override JSON applicato"
else
	ko "config min_scores errata ($MS_CFG)"
fi

# --- 19. MULTI-BANK (blocco bank, resolver, fan-out/merge, promote) ---
sect "19. Multi-bank (bank per progetto + core)"

MB_CFG=$(
	PYTHONUTF8=1 python - "$HOOKS_DIR/lib" <<'PY' 2>/dev/null
import json, os, sys, tempfile
sys.path.insert(0, sys.argv[1])
import hindsight_config as hc

b = hc.DEFAULTS.get("bank") or {}
defaults_ok = {"api_base", "core_bank", "retain_bank", "recall_banks"} <= set(b)

# deep-merge: override parziale non cancella le altre chiavi del blocco
with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as f:
    json.dump({"bank": {"retain_bank": "x-proj"}}, f)
    forced = f.name
os.environ["HS_CONFIG_FILE"] = forced
cfg = hc.load_config()
merge_ok = cfg["bank"]["retain_bank"] == "x-proj" and cfg["bank"]["core_bank"] == b["core_bank"]
os.environ.pop("HS_CONFIG_FILE")
os.unlink(forced)

# resolver: "core" -> core_bank; "auto" nel repo del plugin -> core; letterale passa
cfg2 = hc.load_config()
core = cfg2["bank"]["core_bank"]
plugin_root = os.path.abspath(os.path.join(sys.argv[1], "..", "..", ".."))
res_ok = (
    hc.resolve_bank("core", cfg2) == core
    and hc.resolve_bank("auto", cfg2, plugin_root) == core
    and hc.resolve_bank("nome-libero", cfg2) == "nome-libero"
)

# api_url derivato dal core + retrocompat esplicito
derived_ok = cfg2["api_url"] == hc.bank_url(cfg2, core)
os.environ["HINDSIGHT_API_URL"] = "http://x:1/v1/d/banks/legacy"
cfg3 = hc.load_config()
legacy_ok = hc.retain_bank_url(cfg3) == cfg3["api_url"] and hc.recall_bank_urls(cfg3) == [cfg3["api_url"]]
os.environ.pop("HINDSIGHT_API_URL")

print("OK" if all([defaults_ok, merge_ok, res_ok, derived_ok, legacy_ok])
      else f"KO def={defaults_ok} merge={merge_ok} res={res_ok} der={derived_ok} leg={legacy_ok}")
PY
)
if [ "$MB_CFG" = "OK" ]; then
	ok "config: blocco bank, deep-merge, resolver auto/core, api_url derivato, retrocompat"
else
	ko "config multi-bank errata ($MB_CFG)"
fi

# Identita' del repo del plugin: dal remote CANONICO, non dal basename. Col solo
# basename un repo QUALSIASI chiamato Trinity (nome comune, su GitHub ce ne sono
# molti) veniva scambiato per il plugin e riversava le sue memorie nel core.
# L'altra meta' e' la normalizzazione SSH/HTTPS: lo stesso repo clonato nei due modi
# deve restare riconosciuto, o torna il bug del 21 giugno (plugin staccato dal core).
MB_IDENT=$(
	PYTHONUTF8=1 python - "$HOOKS_DIR/lib" <<'PY' 2>/dev/null
import os, sys
sys.path.insert(0, sys.argv[1])
import hindsight_config as hc

# stesso repo via SSH e via HTTPS -> stessa identita'; host diverso -> identita' diversa
ssh = hc._remote_identity("git@github.com:ichelema/Trinity.git")
https = hc._remote_identity("https://github.com/ichelema/Trinity.git")
other = hc._remote_identity("https://impostor.example/Trinity.git")
norm_ok = bool(ssh) and ssh == https and ssh != other

cfg = hc.load_config()
core = cfg["bank"]["core_bank"]
plugin_root = os.path.abspath(os.path.join(sys.argv[1], "..", "..", ".."))
_, plug_slug, plug_ident = hc._git_root_and_slug(plugin_root)
# il plugin vero -> core (guardia anti-regressione sul fix di giugno)
plugin_ok = bool(plug_ident) and hc.resolve_bank("auto", cfg, plugin_root) == core
# impostore: STESSO basename del plugin, identita' diversa -> bank isolato, non il core.
# Seed della cache invece di un repo finto su disco: su MSYS ogni git costa ~1.4s.
fake = "Z:/fake-impostor"
hc._REPO_CACHE[fake] = (fake, plug_slug, "impostor.example/" + plug_slug.lower())
got = hc.resolve_bank("auto", cfg, fake)
hc._REPO_CACHE.pop(fake, None)
impostor_ok = bool(plug_slug) and got == plug_slug and got != core

print("OK" if all([norm_ok, plugin_ok, impostor_ok])
      else f"KO norm={norm_ok} plugin={plugin_ok} impostor={impostor_ok}")
PY
)
if [ "$MB_IDENT" = "OK" ]; then
	ok "identita' plugin dal remote canonico (un altro repo 'Trinity' non tocca il core)"
else
	ko "identita' del repo del plugin errata ($MB_IDENT)"
fi

MB_QUOTE=$(
	PYTHONUTF8=1 python - "$HOOKS_DIR/lib" <<'PY' 2>/dev/null
import sys
sys.path.insert(0, sys.argv[1])
import hindsight_config as hc

cfg = hc.load_config()
# I bank esistenti non devono cambiare URL: quote() li lascia identici, quindi il fix
# non rinomina nulla e non serve migrazione. Se questo salta, i bank reali si spostano.
same_ok = all(
    hc.bank_url(cfg, n).endswith("/banks/" + n)
    for n in ("trinity-project", "Obsidian_Sinapsi", "Remit_Mappa", "PluginPilot")
)
# Slug fuori dal nostro controllo (repo senza origin -> basename cartella). Si
# verificano le PROPRIETA' dell'URL, non che Request() non sollevi: il costruttore
# accetta tutto e l'eccezione arriva solo alla urlopen, quindi un check "costruisci
# e vedi" passerebbe sempre, anche senza encoding.
# Spazio => InvalidURL ("URL can't contain control characters") alla POST.
space_ok = " " not in hc.bank_url(cfg, "My Project")
# Non-ASCII => UnicodeEncodeError ('ascii' codec) alla POST.
ascii_ok = hc.bank_url(cfg, "café").isascii()
# '?' encodato: se restasse letterale, la coda dello slug diventerebbe query string e
# la POST finirebbe su un endpoint diverso (bank sbagliato, non un errore).
q_ok = "%3F" in hc.bank_url(cfg, "repo.git?token=x")

print("OK" if all([same_ok, space_ok, ascii_ok, q_ok])
      else f"KO invarianti={same_ok} spazi={space_ok} ascii={ascii_ok} query={q_ok}")
PY
)
if [ "$MB_QUOTE" = "OK" ]; then
	ok "bank_url percent-encoda il nome (spazi/accenti/'?') senza spostare i bank esistenti"
else
	ko "bank_url non encoda il nome del bank ($MB_QUOTE)"
fi

MB_LIB=$(
	PYTHONUTF8=1 python - "$HOOKS_DIR/lib" <<'PY' 2>/dev/null
import sys
sys.path.insert(0, sys.argv[1])
import hindsight_multibank as mb

a = [{"text": "a0"}, {"text": "a1"}]
b = [{"text": "b0"}]
il_ok = [r["text"] for r in mb.interleave([a, b], 3)] == ["a0", "b0", "a1"]
d = mb.dedup_results([[{"text": "Stesso  fatto"}], [{"text": "stesso fatto"}, {"text": "altro"}]])
dd_ok = [len(x) for x in d] == [1, 1]

# fallback: rerank che fallisce non deve sollevare
mb.fetch_bank_results = lambda u, p, t: [{"text": f"da-{u}"}]
def boom(*args, **kw): raise RuntimeError("no api")
mb.global_rerank =boom
res, meta = mb.multi_recall("q", {"recall_timeout": 1, "recall_per_bank_candidates": 5, "recall_max_results": 4}, ["u1", "u2"], {})
fb_ok = meta["merge"] == "interleave-fallback" and len(res) == 2

# fallback con soglia attiva: fail-closed (lista vuota), la soglia non si aggira
res, meta = mb.multi_recall("q", {"recall_timeout": 1, "recall_per_bank_candidates": 5, "recall_max_results": 4, "recall_min_rerank_score": 0.5}, ["u1", "u2"], {})
fc_ok = meta["merge"] == "rerank-failed-min-score" and res == []

# filtro soglia: min_score=0.9 lascia solo i punteggi alti. I result mock
# portano uno `scores` server-side (RecallScores) che deve sopravvivere alla
# fusione per finire nel debug log accanto a _rerank_score.
scores = [0.9, 0.5, 0.95]
srv_scores = {"reranker": 0.8, "final": 0.9}
mb.fetch_bank_results = lambda u, p, t: [{"text": f"t{1+i}", "scores": dict(srv_scores)} for i in range(3)]
mb.global_rerank =lambda query, results, model="rerank-2.5", timeout=6, api_key=None, min_score=None: [
    {**r, "_rerank_score": s} for r, s in zip(results, scores) if min_score is None or s >= min_score
]
res, meta = mb.multi_recall("q", {"recall_timeout": 1, "recall_per_bank_candidates": 5, "recall_max_results": 4, "recall_min_rerank_score": 0.9}, ["u1", "u2"], {})
th_ok = len(res) == 2 and res[0]["_rerank_score"] >= 0.9
sc_ok = all(r.get("scores") == srv_scores for r in res)
# soglia superata da tutti: 0.2
res2, _ = mb.multi_recall("q", {"recall_timeout": 1, "recall_per_bank_candidates": 5, "recall_max_results": 4, "recall_min_rerank_score": 0.2}, ["u1", "u2"], {})
th_all_ok = len(res2) == 3
print("OK" if il_ok and dd_ok and fb_ok and fc_ok and th_ok and sc_ok and th_all_ok else f"KO il={il_ok} dd={dd_ok} fb={fb_ok} fc={fc_ok} th={th_ok} sc={sc_ok} thall={th_all_ok}")
PY
)
if [ "$MB_LIB" = "OK" ]; then
	ok "multibank lib: interleave, dedup cross-bank, fallback, fail-closed con soglia, soglia + scores preservati"
else
	ko "hindsight_multibank logica errata ($MB_LIB)"
fi

# Budget recall multi-bank: fan-out e rerank corrono IN SERIE (fan-out -> rerank),
# quindi la loro somma deve stare sotto il timeout dell'hook recall in hooks.json,
# se no nel caso peggiore l'hook viene ucciso e il recall va perso in silenzio. Il
# rerank deve avere il SUO budget (recall_rerank_timeout), non riusare recall_timeout.
MB_BUDGET=$(
	PYTHONUTF8=1 python - "$HOOKS_DIR/lib" "$(w "$HOOKSJSON")" <<'PY' 2>/dev/null
import json, sys
sys.path.insert(0, sys.argv[1])
import hindsight_config as hc
import hindsight_multibank as mb

cfg = hc.load_config()
bank_to = float(cfg["recall_timeout"])
rerank_to = float(cfg["recall_rerank_timeout"])

# 1) multi_recall passa recall_rerank_timeout al rerank, non recall_timeout. Valori
#    distinti (9 vs 4) cosi' se qualcuno rimette timeout=timeout il check lo becca.
seen = {}
mb.fetch_bank_results = lambda u, p, t: [{"text": f"da-{u}"}]
def capture(query, results, model="rerank-2.5", timeout=6, api_key=None, min_score=None):
    seen["timeout"] = timeout
    return [dict(r, _rerank_score=1.0) for r in results]
mb.global_rerank =capture
mb.multi_recall("q", {**cfg, "recall_timeout": 9, "recall_rerank_timeout": 4}, ["u1", "u2"], {})
wired_ok = seen.get("timeout") == 4

# 2) somma dei budget SERIALI sotto il timeout dell'hook (margine per startup+join).
hooks = json.load(open(sys.argv[2], encoding="utf-8"))
groups = hooks["hooks"].get("UserPromptSubmit", [])
hook_to = next(
    h["timeout"] for g in groups for h in g.get("hooks", [])
    if "hindsight-recall.sh" in h.get("command", "")
)
budget_ok = bank_to + rerank_to < hook_to

print("OK" if wired_ok and budget_ok
      else f"KO wired={wired_ok} budget={budget_ok} sum={bank_to + rerank_to} hook={hook_to}")
PY
)
if [ "$MB_BUDGET" = "OK" ]; then
	ok "budget recall: rerank ha il suo timeout e fan-out+rerank < timeout hook"
else
	ko "budget recall multi-bank fuori scala ($MB_BUDGET)"
fi

# recall hook usa il fan-out; ogni prompt normale esegue un fetch fresco.
if grep -q "recall_bank_urls" "$HOOKS_DIR/hindsight-recall.sh" && grep -q 'multi_recall' "$HOOKS_DIR/hindsight-recall.sh"; then
	ok "recall hook integra resolver e fan-out multi-bank senza cache risultati"
else
	ko "recall hook non integra correttamente il multi-bank"
fi

# recall hook logga i punteggi per-stadio del server (RecallScores, api >=0.8.4)
if grep -q '"scores"' "$HOOKS_DIR/hindsight-recall.sh" && grep -q 'min_score_filtered' "$HOOKS_DIR/hindsight-recall.sh"; then
	ok "recall hook logga scores per-stadio e meta min_score nel debug log"
else
	ko "recall hook non logga RecallScores/meta min_score"
fi

# --- 20. FILTRO POST-RECALL E CONSENSO MEDIUM ---
sect "20. Filtro post-recall e consenso medium"
FILTER_TEST=$(cd "$HOOKS_DIR" && PYTHONUTF8=1 python test_hindsight_recall_filter.py 2>&1)
if [ "$?" -eq 0 ]; then
	ok "test unitari filtro/routing/consenso/pending passati"
else
	ko "test unitari filtro recall falliti"
	note "$FILTER_TEST"
fi

HOOK_E2E=$(cd "$HOOKS_DIR" && PYTHONUTF8=1 python test_hindsight_recall_hook.py 2>&1)
if [ "$?" -eq 0 ]; then
	ok "test e2e hook recall (high+medium, consenso, fail-open) passati"
else
	ko "test e2e hook recall falliti"
	note "$HOOK_E2E"
fi

FILTER_CFG=$(PYTHONUTF8=1 python - "$HOOKS_DIR/lib" <<'PY' 2>/dev/null
import sys
sys.path.insert(0, sys.argv[1])
import hindsight_config as hc
cfg = hc.load_config()
keys = (
    "recall_result_filter_enabled", "recall_result_filter_model",
    "recall_result_filter_timeout", "recall_result_filter_threshold",
    "recall_pending_dir", "recall_pending_ttl", "recall_debug_in_context",
)
valid = all(key in cfg for key in keys) and cfg["recall_result_filter_threshold"] == 0.8
print("OK" if valid else "KO")
PY
)
if [ "$FILTER_CFG" = "OK" ]; then
	ok "config filtro/pending/debug completa e soglia 0.8"
else
	ko "config filtro post-recall incompleta ($FILTER_CFG)"
fi

if grep -q 'output\["systemMessage"\] = context' "$HOOKS_DIR/hindsight-recall.sh"; then
	ok "debug recall usa systemMessage per essere visibile nella conversazione"
else
	ko "debug recall resta solo in additionalContext e non è visibile nel terminale"
fi

if grep -q 'from hindsight_recall_filter import' "$HOOKS_DIR/benchmark/hindsight_recall_result_filter_bench.py"; then
	ok "benchmark e produzione condividono prompt/schema/logica score"
else
	ko "benchmark filtro diverge dalla libreria di produzione"
fi

# retain worker scrive sul bank risolto da retain_bank
if grep -q "retain_bank_url" "$HOOKS_DIR/hindsight-retain-worker.py"; then
	ok "retain worker usa retain_bank_url (bank di progetto)"
else
	ko "retain worker non usa retain_bank_url"
fi

# tooling promozione: ops script + comando + scheduler settimanale
if [ -r "$HOOKS_DIR/ops/hindsight-promote.py" ] && PYTHONUTF8=1 python "$HOOKS_DIR/ops/hindsight-promote.py" --status >/dev/null 2>&1; then
	ok "hindsight-promote.py presente e --status funziona"
else
	ko "hindsight-promote.py mancante o --status fallisce"
fi
if [ -r "$PROJ/commands/promote.md" ]; then
	ok "comando /trinity:promote presente (commands/promote.md)"
else
	ko "commands/promote.md mancante"
fi
if [ -x "$PROJ/scheduler/promote_scan/promote-scan-scheduled.sh" ] && [ -r "$PROJ/scheduler/promote_scan/promote-scan-scheduled.cmd" ]; then
	ok "scheduler promote_scan presente (.sh eseguibile + .cmd)"
else
	ko "scheduler promote_scan mancante o .sh non eseguibile"
fi

# --- 21. RETAIN GATE SEMANTICO (ICH-67) ---
sect "21. Retain gate semantico (ICH-67)"

GATE_CFG=$(
	PYTHONUTF8=1 python - "$HOOKS_DIR/lib" <<'PY' 2>/dev/null
import sys
sys.path.insert(0, sys.argv[1])
import hindsight_config as hc
cfg = hc.load_config()
model = cfg.get("retain_gate_model")
timeout = cfg.get("retain_gate_timeout")
debug = cfg.get("retain_debug_in_context")
# Il gate non ha piu' modalita': comanda solo retain_enabled. Un
# retain_gate_mode residuo nei DEFAULTS segnalerebbe una regressione.
mode_gone = "retain_gate_mode" not in hc.DEFAULTS
model_ok = isinstance(model, str) and bool(model.strip())
to_ok = isinstance(timeout, (int, float)) and not isinstance(timeout, bool) and timeout > 0
dbg_ok = isinstance(debug, bool)
print("OK" if mode_gone and model_ok and to_ok and dbg_ok
      else f"KO mode_gone={mode_gone} model={model} timeout={timeout} debug={debug}")
PY
)
if [ "$GATE_CFG" = "OK" ]; then
	ok "config gate valida (model/timeout/debug; nessun retain_gate_mode residuo)"
else
	ko "config retain_gate_* non valida ($GATE_CFG)"
fi

# Il gate gira in modo sincrono DENTRO l'hook recall a UserPromptSubmit (ICH-86):
# il suo timeout deve stare sotto il timeout di quella entry con margine per
# recall + filtro + consenso + POST + startup (~25s).
GATE_BUDGET=$(
	PYTHONUTF8=1 python - "$HOOKS_DIR/lib" "$(w "$HOOKSJSON")" <<'PY' 2>/dev/null
import json, sys
sys.path.insert(0, sys.argv[1])
import hindsight_config as hc
cfg = hc.load_config()
hooks = json.load(open(sys.argv[2], encoding="utf-8"))
hook_to = next(
    h["timeout"] for g in hooks["hooks"].get("UserPromptSubmit", []) for h in g.get("hooks", [])
    if "hindsight-recall.sh" in h.get("command", "")
)
print("OK" if float(cfg["retain_gate_timeout"]) + 25 <= hook_to else f"KO gate={cfg['retain_gate_timeout']} hook={hook_to}")
PY
)
if [ "$GATE_BUDGET" = "OK" ]; then
	ok "budget: retain_gate_timeout + 25s di margine sotto il timeout dell'hook recall (UserPromptSubmit)"
else
	ko "retain_gate_timeout troppo vicino al timeout dell'hook recall a UserPromptSubmit ($GATE_BUDGET)"
fi

# Wiring ICH-86: lo Stop hook e' puro enqueue (hs-retain-queue, niente HSGATE ne'
# guardia stop_hook_active: non c'e' piu' nessun decision:block da proteggere);
# l'hook recall delega tutto il lato retain del prompt al worker
# (retain_at_prompt: consenso + gate differito in parallelo al recall); la
# sentinella drena il residuo a chiusura (--drain).
if grep -q 'hs-retain-queue' "$HOOKS_DIR/hindsight-retain.sh" &&
	! grep -q 'HSGATE' "$HOOKS_DIR/hindsight-retain.sh" &&
	! grep -q 'stop_hook_active' "$HOOKS_DIR/hindsight-retain.sh"; then
	ok "Stop hook: solo enqueue in hs-retain-queue (niente HSGATE / stop_hook_active)"
else
	ko "Stop hook non e' puro enqueue (manca hs-retain-queue o residui HSGATE/stop_hook_active)"
fi
if grep -q 'retain_at_prompt' "$HOOKS_DIR/hindsight-recall.sh"; then
	ok "recall hook delega il lato retain al worker (retain_at_prompt) a UserPromptSubmit"
else
	ko "retain_at_prompt assente da hindsight-recall.sh: consenso e coda del retain non vengono mai gestiti"
fi
if grep -q -- '--drain' "$HOOKS_DIR/hindsight-sentinel.sh"; then
	ok "sentinella drena la coda del retain (--drain) prima dello shutdown"
else
	ko "--drain assente da hindsight-sentinel.sh: la coda della sessione andrebbe persa"
fi

# Worker integra gate e pending uncertain; il modulo lib e' condiviso coi test.
if grep -q 'evaluate_retain' "$HOOKS_DIR/hindsight-retain-worker.py" &&
	grep -q 'save_retain_pending' "$HOOKS_DIR/hindsight-retain-worker.py" &&
	[ -r "$HOOKS_DIR/lib/hindsight_retain_gate.py" ]; then
	ok "worker integra evaluate_retain + pending uncertain (lib/hindsight_retain_gate.py)"
else
	ko "gate/pending non integrati nel worker o modulo lib mancante"
fi
# ICH-86: entry point del lato retain per l'hook recall (retain_at_prompt:
# consenso + gate differito in un thread parallelo al recall), consumo della
# coda (evaluate_queued) + scarto dei messaggi utente in coda al transcript (a
# UserPromptSubmit puo' gia' contenere il prompt nuovo: la finestra deve
# essere quella del turno COMPLETATO).
if grep -q 'def retain_at_prompt' "$HOOKS_DIR/hindsight-retain-worker.py" &&
	grep -q 'def evaluate_queued' "$HOOKS_DIR/hindsight-retain-worker.py" &&
	grep -q 'def drop_unanswered_tail' "$HOOKS_DIR/hindsight-retain-worker.py"; then
	ok "worker espone retain_at_prompt + evaluate_queued + drop_unanswered_tail (valutazione differita)"
else
	ko "retain_at_prompt, evaluate_queued o drop_unanswered_tail assenti dal worker (ICH-86)"
fi

# Il consenso del pending retain vive nel worker (retain_at_prompt), chiamato
# dall'hook recall al prompt successivo: senza, il si' dell'utente non
# eseguirebbe mai la POST in attesa.
if grep -q 'handle_retain_consent' "$HOOKS_DIR/hindsight-retain-worker.py"; then
	ok "worker gestisce il consenso del retain pending (handle_retain_consent in retain_at_prompt)"
else
	ko "handle_retain_consent assente da hindsight-retain-worker.py"
fi

# ICH-73: quando il gate non produce un context, il pending si risolve al prompt
# successivo leggendo dal transcript la riga proposta da Claude: l'hook recall
# deve passare transcript_path a handle_retain_consent, altrimenti la catena
# salta sempre alla riga di ripiego repo/branch.
if grep -A5 'handle_retain_consent(' "$HOOKS_DIR/hindsight-recall.sh" | grep -q 'transcript_path='; then
	ok "recall hook passa transcript_path al consenso retain (ICH-73)"
else
	ko "hindsight-recall.sh non passa transcript_path a handle_retain_consent (ICH-73)"
fi

GATE_TEST=$(cd "$HOOKS_DIR" && PYTHONUTF8=1 python test_hindsight_retain_gate.py 2>&1)
if [ "$?" -eq 0 ]; then
	ok "test unitari retain gate passati"
else
	ko "test unitari retain gate falliti"
	note "$(printf '%s' "$GATE_TEST" | tail -3)"
fi

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
