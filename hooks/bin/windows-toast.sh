#!/usr/bin/env bash
# Wrapper toast: trova pwsh e lancia windows-toast.ps1 (BurntToast).
# Usato dal Notification hook (hooks.json). Lo stdin
# (eventuale {"message":...}) fluisce al .ps1, che senza message usa un default.
#
# pwsh non è nel PATH MSYS: cercalo, poi ricadi sull'install standard di PowerShell 7.
# Se manca, esce 0 senza fare nulla (il toast è best-effort, non deve mai bloccare).
set -uo pipefail

PLUGIN_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"

# Linux: notify-send se c'e' un desktop, altrimenti no-op (server headless).
case "$(uname -s)" in
MINGW* | MSYS* | CYGWIN*) ;; # ramo Windows sotto
*)
	MSG="$(jq -r '.message // empty' 2>/dev/null || true)"
	if command -v notify-send >/dev/null 2>&1; then
		notify-send "Claude Code" "${MSG:-Richiesta di conferma in attesa}" 2>/dev/null || true
	fi
	exit 0
	;;
esac

PWSH="$(command -v pwsh 2>/dev/null || echo "/c/Program Files/PowerShell/7/pwsh.exe")"
[ -x "$PWSH" ] || exit 0

exec "$PWSH" -NoProfile -ExecutionPolicy Bypass \
	-File "$(cygpath -w "$PLUGIN_ROOT/hooks/bin/windows-toast.ps1")"
