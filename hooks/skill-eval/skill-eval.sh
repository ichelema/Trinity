#!/usr/bin/env bash
# Skill Evaluation Hook v3.0
# Wrapper che delega al motore Python (skill-eval.py)
#
# `dirname` e la subshell $(cd && pwd) sono 2 fork (~600ms su MSYS); l'espansione
# %/* e' interna a bash. Guardia: senza `/` nel path, %/* non taglia nulla -> ".".
SCRIPT_DIR="${BASH_SOURCE[0]%/*}"; [ "$SCRIPT_DIR" = "${BASH_SOURCE[0]}" ] && SCRIPT_DIR="."
PY_SCRIPT="$SCRIPT_DIR/skill-eval.py"

# Check if Python is available
PY_BIN="$(command -v python 2>/dev/null || command -v python3 2>/dev/null || true)"
if [[ -z "$PY_BIN" ]]; then
  exit 0
fi

# Check if the Python script exists
if [[ ! -f "$PY_SCRIPT" ]]; then
  exit 0
fi

# Bypass dello shim mise: lo shim rilancia mise.exe a OGNI invocazione. Risolvi il
# binario reale una volta e cachalo su file; il check -x invalida da solo la cache.
case "$PY_BIN" in
  */mise/shims/*)
    _se_cache_dir="${XDG_CACHE_HOME:-$HOME/.cache}/trinity"
    [ -d "$_se_cache_dir" ] || {
      mkdir -p "$_se_cache_dir" 2>/dev/null && chmod 700 "$_se_cache_dir" 2>/dev/null
    }
    _se_cache="$_se_cache_dir/hs-python-real.path"
    _se_real=""
    [[ -f "$_se_cache" ]] && IFS= read -r _se_real <"$_se_cache"
    if [[ ! -x "$_se_real" ]]; then
      _se_mise="$(command -v mise 2>/dev/null || echo "$HOME/.local/bin/mise")"
      _se_real="$("$_se_mise" which python 2>/dev/null | tr '\\' '/' || true)"
      [[ -n "$_se_real" && -x "$_se_real" ]] && { printf '%s' "$_se_real" >"$_se_cache" 2>/dev/null || true; }
    fi
    [[ -n "$_se_real" && -x "$_se_real" ]] && PY_BIN="$_se_real"
    ;;
esac

# Python eredita gia' lo stdin dell'hook.
"$PY_BIN" "$PY_SCRIPT" 2>/dev/null

# Always exit 0 to allow the prompt through
exit 0
