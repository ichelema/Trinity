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
  # mise non è nel PATH della bash MSYS → cercalo nel PATH, poi ricadi sul launcher
  # sotto la home MSYS dell'utente corrente (il plugin è pensato per Windows+MSYS2).
  HS_MISE="$(command -v mise 2>/dev/null || echo "/c/msys64/home/${USERNAME:-}/.local/bin/mise.exe")"
  HS_PY="$("$HS_MISE" which python 2>/dev/null || true)"
fi
if [ -z "$HS_PY" ] && [ -x /ucrt64/bin/python ]; then
  HS_PY="/ucrt64/bin/python"
fi
[ -z "$HS_PY" ] && HS_PY="python"
export HS_PY
# UTF-8 garantito anche fuori da Trinity (il python MSYS UCRT64 usa cp1252 di
# default -> UnicodeEncodeError sul testo unicode delle memorie).
export PYTHONUTF8=1
