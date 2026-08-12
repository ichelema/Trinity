#!/usr/bin/env bash
# SessionStart: inietta core-behavior.md come contesto, espandendo SOLO le
# variabili machine-specific (OBSIDIAN_VAULT, OBSIDIAN_VAULT_NAME). Tutto il
# resto del file (inclusi gli esempi Nushell con $PATH/$r/$in) resta letterale.
#
# I valori si definiscono UNA VOLTA per macchina in ~/.claude/settings.json (env);
# vedi README "Setup per-macchina". Se mancano, il testo mostra un avviso anziché
# un valore vuoto, così è evidente che la config va completata.
set -uo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
FILE="$ROOT/core-behavior.md"

: "${OBSIDIAN_VAULT:=⚠️ imposta OBSIDIAN_VAULT in ~/.claude/settings.json}"
: "${OBSIDIAN_VAULT_NAME:=⚠️ imposta OBSIDIAN_VAULT_NAME}"
export OBSIDIAN_VAULT OBSIDIAN_VAULT_NAME

# La sezione "Retain a fine task" (marker RETAIN:manual) vale solo nei progetti
# SENZA retain automatico: dove retain_enabled e' true salva gia' il gate
# dell'hook Stop, e la regola agent-side creerebbe salvataggi doppi. Config
# risolta dal loader centralizzato (rispetta l'override di progetto via
# CLAUDE_PROJECT_DIR). Se python non risponde, la sezione resta: con gli hook
# rotti il retain MCP e' l'unica strada che funziona.
. "$ROOT/hooks/hindsight/lib/hs-python.sh"
CFG_PY="$ROOT/hooks/hindsight/lib/hindsight_config.py"
command -v cygpath >/dev/null 2>&1 && CFG_PY="$(cygpath -w "$CFG_PY")"
RETAIN_DROP=0
[ "$("$HS_PY" "$CFG_PY" --get retain_enabled 2>/dev/null)" = "True" ] && RETAIN_DROP=1

# Il file contiene blocchi per-OS delimitati da <!-- OS:windows --> e
# <!-- OS:linux -->: tieni solo quelli dell'OS corrente e togli i marker.
case "$(uname -s)" in
MINGW* | MSYS* | CYGWIN*) OS_DROP=linux ;;
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
        esac
        [ "$drop" -eq 1 ] && continue
        printf '%s\n' "$line"
    done < "$FILE"
}

if command -v envsubst > /dev/null 2>&1; then
    # Lista esplicita: envsubst tocca SOLO queste due var, non $PATH/$r/$in.
    filter_os | envsubst '${OBSIDIAN_VAULT} ${OBSIDIAN_VAULT_NAME}'
else
    # Fallback senza gettext: _NAME prima (evita match parziali).
    filter_os | sed -e "s|\${OBSIDIAN_VAULT_NAME}|${OBSIDIAN_VAULT_NAME}|g" \
        -e "s|\${OBSIDIAN_VAULT}|${OBSIDIAN_VAULT}|g"
fi
