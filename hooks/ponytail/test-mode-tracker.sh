#!/usr/bin/env bash
# Verifica lo stato per sessione: off resta dopo compact e resume, un'altra sessione non lo tocca,
# /clear (nuova sessione) riparte dal default, /trinity:ponytail:ponytail senza argomento riattiva dopo un off.
set -euo pipefail
dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
tmp="$(mktemp -d)"; trap 'rm -rf "$tmp"' EXIT
# lua nativo su Windows non capisce i path /tmp/...: convertili se c'è cygpath
export CLAUDE_CONFIG_DIR="$(cygpath -m "$tmp" 2>/dev/null || echo "$tmp")" PONYTAIL_DEFAULT_MODE=full
unset PONYTAIL_SUBAGENT_MATCHER
fail() { echo "FAIL: $1"; exit 1; }
state() { cat "$tmp/ponytail-state/$1" 2>/dev/null || echo none; }
check() { [ "$(state "$1")" = "$2" ] || fail "$3 (stato di $1: $(state "$1"))"; }
start() { printf '{"session_id":"%s","source":"%s"}' "$1" "$2" | lua "$dir/ponytail-activate.lua" >/dev/null; }
prompt() { printf '{"session_id":"%s","prompt":"%s"}' "$1" "$2" | lua "$dir/ponytail-mode-tracker.lua" >/dev/null; }
sub() { printf '{"session_id":"%s","agent_type":"x"}' "$1" | lua "$dir/ponytail-subagent.lua"; }

start s1 startup;                           check s1 full "startup non usa il default"
prompt s1 "/trinity:ponytail:ponytail off"; check s1 off "off non ha spento"
start s1 compact;                           check s1 off "compact ha riacceso"
start s1 resume;                            check s1 off "resume ha riacceso"
start s2 startup;                           check s1 off "un'altra sessione ha cambiato lo stato"
check s2 full "la seconda sessione non usa il default"
[ -z "$(sub s1)" ] || fail "il subagent della sessione spenta riceve ponytail"
[ -n "$(sub s2)" ] || fail "il subagent della sessione attiva non riceve ponytail"
start s3 clear;                             check s3 full "clear non riparte dal default"
prompt s1 "/trinity:ponytail:ponytail";     check s1 full "senza argomento non riattiva"
echo PASS
