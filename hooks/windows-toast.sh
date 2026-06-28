#!/usr/bin/env bash
# Wrapper toast: trova pwsh e lancia windows-toast.ps1 (BurntToast).
# Usato dal Notification hook (hooks.json). Lo stdin
# (eventuale {"message":...}) fluisce al .ps1, che senza message usa un default.
#
# pwsh non è nel PATH MSYS: cercalo, poi ricadi sull'install standard di PowerShell 7.
# Se manca, esce 0 senza fare nulla (il toast è best-effort, non deve mai bloccare).
set -uo pipefail

PLUGIN_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PWSH="$(command -v pwsh 2>/dev/null || echo "/c/Program Files/PowerShell/7/pwsh.exe")"
[ -x "$PWSH" ] || exit 0

exec "$PWSH" -NoProfile -ExecutionPolicy Bypass \
	-File "$(cygpath -w "$PLUGIN_ROOT/hooks/windows-toast.ps1")"
