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

if command -v envsubst > /dev/null 2>&1; then
    # Lista esplicita: envsubst tocca SOLO queste due var, non $PATH/$r/$in.
    envsubst '${OBSIDIAN_VAULT} ${OBSIDIAN_VAULT_NAME}' < "$FILE"
else
    # Fallback senza gettext: _NAME prima (evita match parziali).
    sed -e "s|\${OBSIDIAN_VAULT_NAME}|${OBSIDIAN_VAULT_NAME}|g" \
        -e "s|\${OBSIDIAN_VAULT}|${OBSIDIAN_VAULT}|g" "$FILE"
fi
