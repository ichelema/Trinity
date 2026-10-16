#!/usr/bin/env bash
# SessionStart: inietta core-behavior.md come contesto, tenendo solo i blocchi
# dell'OS corrente e scartando i blocchi manuali RECALL/RETAIN dove l'hook
# automatico li rende superflui. Il resto del file resta letterale.
#
# Zero fork: su MSYS ogni processo costa 200-450ms e l'hook ha 5s di timeout,
# condivisi all'avvio con gli altri SessionStart. Con due python, cygpath, uname
# e dirname girava in ~1,8s (fino a 6s all'avvio) ed e' andato in timeout 5 volte
# a ottobre 2026: sessioni partite senza le regole base.
set -uo pipefail

# Root del plugin (bin/ -> hooks/ -> plugin) per parameter expansion, come in
# lib/hs-python.sh: niente subshell ne' dirname.
ROOT="${BASH_SOURCE[0]%/*}"
[ "$ROOT" = "${BASH_SOURCE[0]}" ] && ROOT="."
ROOT="$ROOT/../.."
FILE="$ROOT/core-behavior.md"

# retain_enabled / recall_enabled con la precedenza di lib/hindsight_config.py:
# default true -> config del plugin -> config di progetto -> env HS_CFG_*
# (HS_CONFIG_FILE forza un solo file). Scarta il blocco solo il valore `true`,
# come il vecchio confronto con l'output "True" di --get. La parita' con Python
# la controlla hooks/hindsight/test_inject_core_behavior.py.
# ponytail: parser per riga, non JSON: chiave e valore sulla stessa riga, un file JSON rotto non viene ignorato in blocco come fa Python, env senza trim degli spazi. Se servono altre chiavi, tornare a hindsight_config.py.
RETAIN_ON=true
RECALL_ON=true
RE_RETAIN='"retain_enabled"[[:space:]]*:[[:space:]]*([^,}[:space:]]+)'
RE_RECALL='"recall_enabled"[[:space:]]*:[[:space:]]*([^,}[:space:]]+)'
read_flags() {
    local line
    [ -f "$1" ] || return 0
    while IFS= read -r line || [ -n "$line" ]; do
        [[ $line =~ $RE_RETAIN ]] && [ "${BASH_REMATCH[1]}" != null ] && RETAIN_ON=${BASH_REMATCH[1]}
        [[ $line =~ $RE_RECALL ]] && [ "${BASH_REMATCH[1]}" != null ] && RECALL_ON=${BASH_REMATCH[1]}
    done < "$1"
}
if [ -n "${HS_CONFIG_FILE:-}" ]; then
    read_flags "$HS_CONFIG_FILE"
else
    read_flags "$ROOT/hindsight.config.json"
    [ -n "${CLAUDE_PROJECT_DIR:-}" ] && read_flags "$CLAUDE_PROJECT_DIR/hindsight.config.json"
fi
v="${HS_CFG_RETAIN_ENABLED:-}"
case "${v,,}" in 1 | true | yes) RETAIN_ON=true ;; 0 | false | no) RETAIN_ON=false ;; esac
v="${HS_CFG_RECALL_ENABLED:-}"
case "${v,,}" in 1 | true | yes) RECALL_ON=true ;; 0 | false | no) RECALL_ON=false ;; esac

# La sezione "Retain a fine task" (marker RETAIN:manual) vale solo nei progetti
# SENZA retain automatico: dove retain_enabled e' true salva gia' il gate
# del retain automatico, e la regola agent-side creerebbe salvataggi doppi.
RETAIN_DROP=0
[ "$RETAIN_ON" = true ] && RETAIN_DROP=1
# Stesso criterio per "Recall a inizio task" (marker RECALL:manual): dove
# recall_enabled e' true le memorie le inietta gia' l'hook UserPromptSubmit.
RECALL_DROP=0
[ "$RECALL_ON" = true ] && RECALL_DROP=1

# Il file contiene blocchi per-OS delimitati da <!-- OS:windows --> e
# <!-- OS:linux -->: tieni solo quelli dell'OS corrente e togli i marker.
# $OSTYPE e' una variabile di bash (zero fork), come in lib/hs-python.sh.
case "$OSTYPE" in
msys* | cygwin*) OS_DROP=linux ;;
*) OS_DROP=windows ;;
esac
# Filtro in puro bash (niente sed: col sed nativo ucrt64 la path conversion
# MSYS2 mangia le espressioni che contengono slash).
filter_os() {
    local drop=0 line
    while IFS= read -r line; do
        case "$line" in
        *"<!-- OS:$OS_DROP -->"*) drop=1; continue ;;
        *"<!-- /OS:$OS_DROP -->"*) drop=0; continue ;;
        *"<!-- OS:"* | *"<!-- /OS:"*) continue ;;
        *"<!-- RETAIN:manual -->"*) [ "$RETAIN_DROP" -eq 1 ] && drop=1; continue ;;
        *"<!-- /RETAIN:manual -->"*) [ "$RETAIN_DROP" -eq 1 ] && drop=0; continue ;;
        *"<!-- RECALL:manual -->"*) [ "$RECALL_DROP" -eq 1 ] && drop=1; continue ;;
        *"<!-- /RECALL:manual -->"*) [ "$RECALL_DROP" -eq 1 ] && drop=0; continue ;;
        esac
        [ "$drop" -eq 1 ] && continue
        printf '%s\n' "$line"
    done < "$FILE"
}

filter_os
