#!/usr/bin/env bash
# Riproduce un suono di notifica (best-effort: non deve MAI bloccare o fallire).
# Uso: play-sound.sh <file.wav>   (nome relativo a sound/ oppure path assoluto)
#
# Sostituisce i comandi inline di hooks.json che usavano cygpath (assente su
# Linux): qui il path e' gia' POSIX perche' derivato da BASH_SOURCE. Player in
# ordine di preferenza: ffplay (Windows/MSYS2 e desktop Linux con ffmpeg),
# paplay (PulseAudio/PipeWire), aplay (ALSA). Nessun player o niente audio
# (server headless) -> esce 0 in silenzio.
set -uo pipefail

PLUGIN_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
F="${1:?uso: play-sound.sh <file.wav>}"
case "$F" in
/* | ?:*) : ;;                  # gia' assoluto (POSIX o Windows)
*) F="$PLUGIN_ROOT/sound/$F" ;; # relativo a sound/ del plugin
esac
[ -f "$F" ] || exit 0

if command -v ffplay >/dev/null 2>&1; then
	exec ffplay -nodisp -autoexit -loglevel quiet "$F" >/dev/null 2>&1
elif command -v paplay >/dev/null 2>&1; then
	exec paplay "$F" >/dev/null 2>&1
elif command -v aplay >/dev/null 2>&1; then
	exec aplay -q "$F" >/dev/null 2>&1
fi
exit 0
