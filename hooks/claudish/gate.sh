#!/usr/bin/env bash
# MessageDisplay: gate sulla whitelist modelli, poi delega a rewrite.sh.
#
# Se CLAUDISH_ONLY_MODELS è impostata (lista di token separati da virgola,
# match case-insensitive per sottostringa sulla "famiglia" del modello — es.
# "fable,opus"), riscrive solo se il modello della sessione (catturato a
# SessionStart da capture-model.sh) contiene uno dei token. Altrimenti esce
# muto: fail-open, il testo originale resta invariato.
#
# rewrite.sh resta intatto: questo wrapper legge SOLO il file del modello,
# lo stdin JSON di MessageDisplay fluisce invariato a rewrite.sh via exec.
set -uo pipefail

if [ -n "${CLAUDISH_ONLY_MODELS:-}" ]; then
    ACTIVE="$(cat "${TMPDIR:-/tmp}/claudish/active-model" 2>/dev/null || true)"
    [ -n "$ACTIVE" ] || exit 0
    ok=0
    IFS=',' read -ra _wl <<< "$CLAUDISH_ONLY_MODELS"
    for _m in "${_wl[@]}"; do
        _m="${_m// /}"   # nessun id di modello contiene spazi
        [ -n "$_m" ] || continue
        case "${ACTIVE,,}" in
            *"${_m,,}"*) ok=1; break ;;
        esac
    done
    [ "$ok" = "1" ] || exit 0
fi

DIR="${BASH_SOURCE[0]%/*}"; [ "$DIR" = "${BASH_SOURCE[0]}" ] && DIR="."
exec "$DIR/rewrite.sh"
