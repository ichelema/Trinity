#!/usr/bin/env bash
# Triggers a Windows toast + sound when Claude is about to run a Bash command
# whose first word is NOT in a hardcoded safe list. Works around the fact that
# Claude Code does not emit Notification events for permission prompts.
#
# Exits 0 always (never blocks the tool call).

set -euo pipefail

payload=$(cat)

tool_name=$(printf '%s' "$payload" | jq -r '.tool_name // ""')
[[ "$tool_name" != "Bash" ]] && exit 0

command=$(printf '%s' "$payload" | jq -r '.tool_input.command // ""')
[[ -z "$command" ]] && exit 0

# Strip leading whitespace, get first token
first=$(printf '%s' "$command" | awk '{print $1}')
second=$(printf '%s' "$command" | awk '{print $2}')

# Safe single-word commands (read-only / no side effects)
safe_single=(ls cat echo pwd date head tail grep find wc sleep true false
	which type whoami hostname uname printf stat file dirname basename
	realpath readlink env id tty tput clear column sort uniq cut tr
	awk sed jq nu python python3 ruby uv pnpm node npx)

# Safe `git <subcmd>` patterns
safe_git=(status diff log show branch blame describe remote config tag stash)

is_safe=0

if [[ "$first" == "git" ]]; then
	for sub in "${safe_git[@]}"; do
		[[ "$second" == "$sub" ]] && is_safe=1 && break
	done
else
	for cmd in "${safe_single[@]}"; do
		[[ "$first" == "$cmd" ]] && is_safe=1 && break
	done
fi

[[ "$is_safe" == "1" ]] && exit 0

# Fire toast + sound (background, non-blocking)
# Path derivati dalla posizione dello script: il plugin e' rilocabile.
PLUGIN_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ffplay -nodisp -autoexit -loglevel quiet \
	"$PLUGIN_ROOT/sound/Windows_Exclamation.wav" >/dev/null 2>&1 &

# Toast with snippet of the command for context
snippet=$(printf '%s' "$command" | head -c 80 | tr -d '\n')
echo "{\"message\":\"Permission richiesta per: ${snippet}\"}" |
	/c/Appl/PowerShell/pwsh.exe -NoProfile -ExecutionPolicy Bypass \
		-File "$(cygpath -w "$PLUGIN_ROOT/hooks/windows-toast.ps1")" \
		>/dev/null 2>&1 &

exit 0
