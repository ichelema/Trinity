#!/usr/bin/env bash
# Lancia dream_report_lint.py con lo stesso Python degli hook Hindsight
# (hs-python.sh risolve HS_PY indipendente dal PATH ed esporta PYTHONUTF8=1).
# Uso: dream-report-lint.sh <report.md> [--apply]   — exit come il lint.
set -uo pipefail

HERE="${BASH_SOURCE[0]%/*}"; [ "$HERE" = "${BASH_SOURCE[0]}" ] && HERE="."
case "$HERE" in
[A-Za-z]:/*) _d="${HERE%%:*}"; HERE="/${_d,,}${HERE#?:}" ;;
esac

. "$HERE/../hindsight/lib/hs-python.sh"

LINT="$HERE/dream_report_lint.py"
# Python nativo Windows vuole path Windows (come CFG_PY in inject-core-behavior.sh).
if command -v cygpath >/dev/null 2>&1; then
    LINT="$(cygpath -w "$LINT")"
    [ $# -gt 0 ] && set -- "$(cygpath -w "$1")" "${@:2}"
fi

exec "$HS_PY" "$LINT" "$@"
