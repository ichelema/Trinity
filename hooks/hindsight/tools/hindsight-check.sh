#!/usr/bin/env bash
# Diagnostica completa setup Hindsight + hook Claude Code.
# Uso: bash hooks/hindsight/tools/hindsight-check.sh
# Restituisce exit 0 se tutto OK, 1 altrimenti. Output con check ✓/✗ per componente.
set -uo pipefail

HOOKS_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
# check.sh vive in tools/: con /.. HOOKS_DIR torna a hooks/hindsight (root del
# sottosistema). lib/ ops/ tools/ sono sotto di qui; la root di progetto e' tre livelli sopra.
PROJ="${CLAUDE_PROJECT_DIR:-$(cd "$HOOKS_DIR/../../.." && pwd)}"
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

PID=$(/c/Windows/System32/netstat.exe -ano 2>/dev/null | grep ":8888" | grep LISTENING | awk '{print $NF}' | tr -d '\r' | head -1)
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

# --- 4. TAGS PRESENTI ---
sect "4. Tag propagation (verifica retain ha tagato)"
TAGS=$(curl -s -m 3 "$API_BASE/tags?limit=20" 2>/dev/null |
	python -c "import json,sys; d=json.load(sys.stdin); print(' '.join(t.get('tag','') for t in d.get('items',[])))" 2>/dev/null)
for expected in "claude-code"; do
	if echo " $TAGS " | grep -q " $expected "; then
		ok "tag '$expected' presente nel bank"
	else
		ko "tag '$expected' assente — retain non ha mai tagato (sessione mai chiusa con Stop hook?)"
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

# --- 6. CACHE RECALL ---
sect "6. Cache client-side"
CACHE_DIR="${HINDSIGHT_CACHE_DIR:-/tmp/hs-recall-cache}"
if [ -d "$CACHE_DIR" ]; then
	N_CACHE=$(ls -1 "$CACHE_DIR"/*.json 2>/dev/null | wc -l)
	ok "cache dir esiste ($CACHE_DIR, $N_CACHE entries)"
else
	note "cache dir non ancora creata (verra' creata al primo recall)"
fi

# --- 7. SETTINGS.JSON CONFIG ---
sect "7. Config settings.json"
SETT="$PROJ/.claude/settings.json"
if [ -r "$SETT" ]; then
	if python -c "import json; json.load(open(r'$(cygpath -w $SETT)'))" 2>/dev/null; then
		ok "settings.json valido"
		for hook in "hindsight-recall.sh" "hindsight-retain.sh"; do
			if grep -q "$hook" "$SETT"; then
				ok "$hook registrato in settings.json"
			else
				ko "$hook NON registrato in settings.json"
			fi
		done
		if grep -q '"async": true' "$SETT"; then
			ok "retain hook ha 'async: true'"
		else
			ko "retain hook senza 'async: true'"
		fi
	else
		ko "settings.json non e' JSON valido"
	fi
else
	ko "settings.json non leggibile"
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

# --- 9. END-TO-END RETAIN HOOK (in background, controllo log) ---
sect "9. End-to-end: invoca retain hook"
# HS_RETAIN_FORCE bypassa il throttling ma NON l'interruttore master retain_enabled:
# col retain off il worker esce prima del POST, quindi l'e2e non e' applicabile -> skip.
RETAIN_ON=$(PYTHONUTF8=1 python "$HOOKS_DIR/lib/hindsight_config.py" --get retain_enabled 2>/dev/null)
if [ "$RETAIN_ON" = "False" ]; then
	skip "retain disabilitato (retain_enabled:false) — e2e retain non applicabile"
else
	FAKE=$(mktemp /tmp/hs-check-XXXXXX.jsonl)
	FAKE_WIN=$(cygpath -w "$FAKE")
	cat >"$FAKE" <<EOF
{"type":"user","message":{"role":"user","content":"diagnostica check end-to-end del retain hook con prompt sufficientemente lungo"}}
{"type":"assistant","message":{"role":"assistant","content":[{"type":"text","text":"check OK"},{"type":"tool_use","name":"Bash","input":{"command":"git status"}}]}}
EOF
	RETAIN_PAYLOAD=$(python -c "import json; print(json.dumps({'session_id':'check-1234','transcript_path':r'$FAKE_WIN','cwd':r'$PROJ','hook_event_name':'Stop'}))")
	>/tmp/hs-retain.log
	# HS_RETAIN_FORCE bypassa il throttling (step E) per testare il POST in modo deterministico
	echo "$RETAIN_PAYLOAD" | HS_RETAIN_FORCE=1 "$HOOKS_DIR/hindsight-retain.sh"
	sleep 1
	if grep -q "\[retain\] OK 200" /tmp/hs-retain.log 2>/dev/null; then
		ok "retain hook OK (log: $(head -1 /tmp/hs-retain.log | head -c 120))"
	else
		ko "retain hook non ha scritto OK 200 in /tmp/hs-retain.log"
		note "log: $(cat /tmp/hs-retain.log 2>/dev/null | head -3)"
	fi
	rm -f "$FAKE"
fi

# --- 10. RETAIN WORKER: git_info popola i tag (regression fix A) ---
sect "10. Retain worker: git_info (regression A)"
WORKER_WIN="$(cygpath -w "$HOOKS_DIR/hindsight-retain-worker.py")"
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
GTMP_WIN=$(cygpath -w "$GTMP")
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
WORKER_WIN="$(cygpath -w "$HOOKS_DIR/hindsight-retain-worker.py")"
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
WORKER_WIN="$(cygpath -w "$HOOKS_DIR/hindsight-retain-worker.py")"
DSTATE=$(mktemp -d /tmp/hs-dstate-XXXXXX)
DSTATE_WIN=$(cygpath -w "$DSTATE")
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

# --- 14. THROTTLING retain ogni N + force su SessionEnd (step E) ---
sect "14. Throttling retain (step E)"
WORKER_WIN="$(cygpath -w "$HOOKS_DIR/hindsight-retain-worker.py")"
TSTATE=$(mktemp -d /tmp/hs-tstate-XXXXXX)
TSTATE_WIN=$(cygpath -w "$TSTATE")
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
	ok "should_retain_now: salta N-1 Stop, ritiene all'N-esimo, force sempre"
else
	ko "logica throttling errata ($THR_OK)"
fi
rm -rf "$TSTATE"
# SessionEnd registra hindsight-shutdown.sh, che fa il force-retain finale (cattura la
# coda) PRIMA di fermare i servizi. Il retain finale passa per il wrapper, non diretto:
# percio' verifichiamo (1) shutdown.sh in SessionEnd e (2) che shutdown.sh chiami retain.
if grep -q '"SessionEnd"' "$PROJ/.claude/settings.json" && python -c "
import json,sys
h=json.load(open(sys.argv[1]))['hooks'].get('SessionEnd',[])
cmds=[c.get('command','') for g in h for c in g.get('hooks',[])]
sys.exit(0 if any('hindsight-shutdown.sh' in c for c in cmds) else 1)
" "$(cygpath -w "$PROJ/.claude/settings.json")" 2>/dev/null; then
	if grep -q 'hindsight-retain.sh' "$HOOKS_DIR/hindsight-shutdown.sh"; then
		ok "SessionEnd → hindsight-shutdown.sh, che invoca il force-retain finale"
	else
		ko "hindsight-shutdown.sh non chiama piu' hindsight-retain.sh (retain finale perso)"
	fi
else
	ko "hook SessionEnd con hindsight-shutdown.sh assente in settings.json"
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
if PYTHONUTF8=1 python -c "import json,sys; json.load(open(sys.argv[1],encoding='utf-8'))" "$(cygpath -w "$PLUGIN_CFG")" 2>/dev/null; then
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

RESEED=$(bash "$HOOKS_DIR/ops/hindsight-mental-models.sh" seed 2>/dev/null | grep -c "^+ creato" || true)
if [ "$RESEED" = "0" ]; then
	ok "seed idempotente (nessuna pagina ri-creata)"
else
	ko "seed NON idempotente ($RESEED pagine ri-create)"
fi

SHOW_LEN=$(bash "$HOOKS_DIR/ops/hindsight-mental-models.sh" show user-profile 2>/dev/null | wc -c)
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
legit = "Ho aggiunto le knowledge page al sistema."
out = w.strip_memory_block(block + "\n\n" + legit)
print("OK" if ("knowledge pages" not in out) and (legit in out) else "KO")
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
" "$(cygpath -w "$PROJ/.claude/settings.json")" 2>/dev/null; then
	ok "SessionStart registra hindsight-mm-inject.sh"
else
	ko "hindsight-mm-inject.sh assente da SessionStart in settings.json"
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
case "$DBG_PATH" in
*/logs/hindsight-debug.log) ok "path default del log → $DBG_PATH" ;;
*) ko "path default del log inatteso ($DBG_PATH)" ;;
esac

DBG_TMP="$PROJ/test/hs-debug-check.log"
DBG_TMP_WIN="$(cygpath -w "$DBG_TMP")"
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
RECALL_LIB_WIN="$(cygpath -w "$HOOKS_DIR/lib/hindsight_recall_lib.py")"
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
print("OK" if (base_ok and incl_ok and filt_ok and omit_ok and missing_ok) else f"KO base={base_ok} incl={incl_ok} filt={filt_ok} omit={omit_ok} missing={missing_ok}")
PY
)
if [ "$RT_PAYLOAD" = "OK" ]; then
	ok "build_recall_payload: include types validi, filtra invalidi, omette se vuoto"
else
	ko "build_recall_payload logica errata ($RT_PAYLOAD)"
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
