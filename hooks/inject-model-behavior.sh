#!/usr/bin/env bash
# SessionStart: inietta il file di istruzioni del modello in uso, cercandolo
# nella root del progetto corrente (CLAUDE_FABLE.md con Fable, CLAUDE_OPUS.md
# con Opus, ecc.). Il nome è derivato dall'id del modello, non da una lista:
# per aggiungere un modello basta creare il file.
#
# Il campo `model` arriva nello stdin JSON di SessionStart SOLO in sessione
# interattiva (verificato su claude 2.1.227: i call site headless `-p` lo
# omettono). Se manca, o se il file del modello non esiste, l'hook esce muto.
#
# Limite noto: /model a metà sessione non rilancia SessionStart.
set -uo pipefail

IFS= read -r -d '' HOOK_INPUT || true

case "$HOOK_INPUT" in
*'"model":"'*)
    MODEL="${HOOK_INPUT#*'"model":"'}"
    MODEL="${MODEL%%'"'*}"
    ;;
*) exit 0 ;;
esac

# claude-fable-5 -> FABLE, claude-haiku-4-5-20251001 -> HAIKU
FAMILY="${MODEL#claude-}"
FAMILY="${FAMILY%%-*}"

# $PWD dell'hook è la root del progetto (verificato: coincide col campo `cwd`
# del payload, ma già in forma POSIX anziché Windows con backslash).
FILE="$PWD/CLAUDE_${FAMILY^^}.md"

[ -f "$FILE" ] || exit 0
cat "$FILE"
