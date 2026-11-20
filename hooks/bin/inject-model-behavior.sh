#!/usr/bin/env bash
# SessionStart: inietta il file di istruzioni del modello in uso, preso dalla
# root di Trinity (CLAUDE_FABLE.md con Fable, CLAUDE_OPUS.md con Opus, ecc.):
# una sola copia per tutti i progetti e i worktree; le copie nei progetti sono
# ignorate. Il nome è derivato dall'id del modello, non da una lista: per
# aggiungere un modello basta creare il file.
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

# claude-fable-5 -> FABLE, claude-haiku-4-5-20251001 -> HAIKU, opus[1m] -> OPUS
FAMILY="${MODEL%%\[*}"
FAMILY="${FAMILY#claude-}"
FAMILY="${FAMILY%%-*}"

# Root di Trinity ricavata dal percorso dello script, come inject-core-behavior.sh.
ROOT="${BASH_SOURCE[0]%/*}"
[ "$ROOT" = "${BASH_SOURCE[0]}" ] && ROOT="."
FILE="$ROOT/../../CLAUDE_${FAMILY^^}.md"

[ -f "$FILE" ] || exit 0
cat "$FILE"
