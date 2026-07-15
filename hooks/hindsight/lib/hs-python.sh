# Sourced da ogni hook Hindsight: risolve un interprete Python utilizzabile in
# HS_PY, indipendente dal PATH della sessione, ed esporta PYTHONUTF8=1.
#
# Perche': gli hook girano in OGNI progetto (plugin user-scope). Solo dentro il
# repo Trinity il `.mise.toml` mette `python` nel PATH e setta PYTHONUTF8; in un
# altro progetto `python` puo' NON esistere nel PATH e gli hook fallirebbero in
# silenzio (le invocazioni hanno `2>/dev/null`), niente injection di memoria.
#
# Ordine di risoluzione: python/python3 nel PATH -> python gestito da mise ->
# python MSYS2 UCRT64 -> "python" come ultimo tentativo.
HS_PY="$(command -v python 2>/dev/null || command -v python3 2>/dev/null || true)"
if [ -z "$HS_PY" ]; then
  # mise non è nel PATH ristretto degli hook → cercalo nel PATH, poi ricadi sul
  # launcher standard ~/.local/bin/mise (su MSYS2 risolve da solo il .exe).
  HS_MISE="$(command -v mise 2>/dev/null || echo "$HOME/.local/bin/mise")"
  HS_PY="$("$HS_MISE" which python 2>/dev/null || true)"
fi
if [ -z "$HS_PY" ] && [ -x /ucrt64/bin/python ]; then
  HS_PY="/ucrt64/bin/python"
fi
[ -z "$HS_PY" ] && HS_PY="python"
# Bypass dello shim mise: lo shim rilancia mise.exe a OGNI invocazione (~300ms
# misurati, benchmark 2026-07-10). Risolvi il binario reale una volta e cachalo
# su file; il check -x invalida da solo la cache quando il path cambia (upgrade
# python). NB: la cache e' globale (non per-cwd): un progetto con una versione
# python pinnata nel proprio mise.toml userebbe comunque quella cachata.
case "$HS_PY" in
  */mise/shims/*)
    _hs_cache="${TMPDIR:-/tmp}/hs-python-real.path"
    _hs_real=""
    # || true: la cache e' scritta senza newline finale -> read ritorna 1 a EOF
    # pur popolando la variabile; senza guardia, sotto set -e lo script morirebbe.
    { [ -f "$_hs_cache" ] && IFS= read -r _hs_real < "$_hs_cache"; } || true
    if [ ! -x "$_hs_real" ]; then
      _hs_mise="$(command -v mise 2>/dev/null || echo "$HOME/.local/bin/mise")"
      _hs_real="$("$_hs_mise" which python 2>/dev/null | tr '\\' '/' || true)"
      [ -n "$_hs_real" ] && [ -x "$_hs_real" ] && printf '%s' "$_hs_real" > "$_hs_cache"
    fi
    [ -n "$_hs_real" ] && [ -x "$_hs_real" ] && HS_PY="$_hs_real"
    ;;
esac
export HS_PY
# UTF-8 garantito anche fuori da Trinity (il python MSYS UCRT64 usa cp1252 di
# default -> UnicodeEncodeError sul testo unicode delle memorie).
export PYTHONUTF8=1
