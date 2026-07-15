#!/usr/bin/env bash
# Skill Evaluation Hook v2.0
# Wrapper script that delegates to the Node.js evaluation engine
#
# This hook runs on UserPromptSubmit and analyzes the prompt for:
# - Keywords and patterns indicating skill relevance
# - File paths mentioned in the prompt
# - Intent patterns (what the user wants to do)
# - Directory mappings (what directories map to which skills)
#
# Configuration is in skill-rules.json

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
NODE_SCRIPT="$SCRIPT_DIR/skill-eval.js"

# Check if Node.js is available
NODE_BIN="$(command -v node 2>/dev/null || true)"
if [[ -z "$NODE_BIN" ]]; then
	exit 0
fi

# Check if the Node script exists
if [[ ! -f "$NODE_SCRIPT" ]]; then
	exit 0
fi

# Bypass dello shim mise: lo shim rilancia mise.exe a OGNI invocazione (~300ms
# misurati, benchmark 2026-07-10). Risolvi il binario reale una volta e cachalo
# su file; il check -x invalida da solo la cache quando il path cambia.
case "$NODE_BIN" in
	*/mise/shims/*)
		_se_cache="${TMPDIR:-/tmp}/hs-node-real.path"
		_se_real=""
		[[ -f "$_se_cache" ]] && IFS= read -r _se_real <"$_se_cache"
		if [[ ! -x "$_se_real" ]]; then
			_se_mise="$(command -v mise 2>/dev/null || echo "$HOME/.local/bin/mise")"
			_se_real="$("$_se_mise" which node 2>/dev/null | tr '\\' '/' || true)"
			[[ -n "$_se_real" && -x "$_se_real" ]] && printf '%s' "$_se_real" >"$_se_cache"
		fi
		[[ -n "$_se_real" && -x "$_se_real" ]] && NODE_BIN="$_se_real"
		;;
esac

# Pipe stdin to the Node.js script (suppress stderr noise from nvm/shell init)
cat | "$NODE_BIN" "$NODE_SCRIPT" 2>/dev/null

# Always exit 0 to allow the prompt through
exit 0
