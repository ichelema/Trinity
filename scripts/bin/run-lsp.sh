#!/usr/bin/env bash
# Lancia un language server risolvendo il binario A RUNTIME, per nome.
# Serve a tenere UN SOLO .lsp.json valido su Windows e su Linux: i path degli
# shim differiscono per suffisso (.exe solo su Windows) e non sono esprimibili
# in una stringa unica.
#
# Uso (da .lsp.json): command = <plugin>/scripts/bin/run-lsp.sh
#                     args    = ["<nome-server>", "--stdio", ...]
#
# Ordine di risoluzione: shim di mise -> layout tarball ~/.local/bin/<nome>/bin/
# (es. lua-language-server) -> PATH. NB: si usano gli shim e non `mise which`
# perche' su Windows quest'ultimo restituisce i wrapper .cmd/.bat, che
# passerebbero da cmd.exe: rischioso per un server che parla su stdio.
set -uo pipefail

NAME="${1:?uso: run-lsp.sh <nome-language-server> [args...]}"
shift

SHIMS="$HOME/.local/share/mise/shims"
BIN=""
for _cand in \
	"$SHIMS/$NAME.exe" "$SHIMS/$NAME" \
	"$HOME/.local/bin/$NAME/bin/$NAME.exe" "$HOME/.local/bin/$NAME/bin/$NAME"; do
	if [ -x "$_cand" ]; then
		BIN="$_cand"
		break
	fi
done
[ -n "$BIN" ] || BIN="$(command -v "$NAME" 2> /dev/null || true)"

if [ -z "$BIN" ]; then
	echo "[run-lsp] language server non trovato: $NAME (shim mise, ~/.local/bin, PATH)" >&2
	exit 1
fi

exec "$BIN" "$@"
