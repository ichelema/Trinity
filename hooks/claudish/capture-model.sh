#!/usr/bin/env bash
# SessionStart: cattura il modello della sessione dallo stdin JSON e lo scrive
# in $TMPDIR/claudish/active-model, letto da gate.sh (MessageDisplay) per la
# whitelist CLAUDISH_ONLY_MODELS.
#
# Il campo `model` arriva SOLO in SessionStart interattivo (i call site headless
# `-p` lo omettono): se manca, niente file -> la whitelist fa saltare la
# riscrittura (fail-open). /model a metà sessione non rilancia SessionStart,
# quindi il valore resta quello di avvio.
set -uo pipefail

IFS= read -r -d '' HOOK_INPUT || true

case "$HOOK_INPUT" in
*'"model":"'*)
    MODEL="${HOOK_INPUT#*'"model":"'}"
    MODEL="${MODEL%%'"'*}"
    ;;
*) exit 0 ;;
esac

[ -n "$MODEL" ] || exit 0
DIR="${TMPDIR:-/tmp}/claudish"
mkdir -p "$DIR" 2>/dev/null || exit 0
printf '%s' "$MODEL" > "$DIR/active-model" 2>/dev/null
exit 0
