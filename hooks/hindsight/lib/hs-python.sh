# Sourced da ogni hook Hindsight: risolve un interprete Python utilizzabile in
# HS_PY, indipendente dal PATH della sessione, ed esporta PYTHONUTF8=1.
#
# Perche': gli hook girano in OGNI progetto (plugin user-scope). Solo dentro il
# repo Trinity il `.mise.toml` mette `python` nel PATH e setta PYTHONUTF8; in un
# altro progetto `python` puo' NON esistere nel PATH e gli hook fallirebbero in
# silenzio (le invocazioni hanno `2>/dev/null`), niente injection di memoria.
#
# Esporta anche HS_CACHE_DIR: cache e file di stato degli hook, per-utente e 0700.
# NON /tmp — su Linux e' 1777 e si svuota al reboot, quindi un altro utente puo'
# crearci per primo i file che poi rileggiamo (il path dell'interprete qui sotto
# verrebbe eseguito coi nostri privilegi) o leggere quelli che scriviamo.
# Stesso path calcolato da cache_dir() in lib/hindsight_config.py per il lato Python.
HS_CACHE_DIR="${XDG_CACHE_HOME:-$HOME/.cache}/trinity"
# La dir esiste gia' da dopo il primo hook: `[ -d ]` e' un builtin (~0ms), mentre
# mkdir e chmod sono due fork da ~400ms l'uno su Windows/MSYS (misurato 2026-07-28).
# Paghiamoli solo alla creazione.
[ -d "$HS_CACHE_DIR" ] || {
  mkdir -p "$HS_CACHE_DIR" 2>/dev/null && chmod 700 "$HS_CACHE_DIR" 2>/dev/null
}
export HS_CACHE_DIR
#
# Root del plugin (lib/ -> hindsight/ -> hooks/ -> plugin): serve per `mise -C` cosi'
# si risolve SEMPRE il python del plugin (3.13), non quello del cwd del progetto ospite.
# Parameter expansion, zero fork: il vecchio `$(cd "$(dirname ...)" && pwd)` pagava
# subshell + exec di dirname (~400ms su MSYS) a OGNI hook, anche sul fast-path che
# non usa mise. Path non canonicalizzato (resta il /../../..): a `mise -C` basta.
HS_PLUGIN_ROOT="${BASH_SOURCE[0]%/*}"
[ "$HS_PLUGIN_ROOT" = "${BASH_SOURCE[0]}" ] && HS_PLUGIN_ROOT="."
HS_PLUGIN_ROOT="$HS_PLUGIN_ROOT/../../.."

# Risolve il binario python reale di mise per il plugin, con cache su file. Lo shim
# mise rilancerebbe mise.exe a OGNI invocazione (~300ms, benchmark 2026-07-10): qui
# si risolve una volta e si cacha; il check -x invalida la cache solo se il VECCHIO
# binario sparisce (es. mise prune) — un upgrade lo lascia accanto al nuovo, percio'
# e' il task install-hindsight a buttare la cache quando il runtime puo' cambiare.
# NB: cache globale (non per-cwd) — coerente perche' e'
# sempre il python del PLUGIN. || true: cache scritta senza newline -> read ritorna 1
# a EOF pur popolando la variabile; senza guardia, sotto set -e lo script morirebbe.
_hs_mise_python() {
  local cache="$HS_CACHE_DIR/hs-python-real.path" real="" mise
  { [ -f "$cache" ] && IFS= read -r real < "$cache"; } || true
  if [ ! -x "$real" ]; then
    mise="$(command -v mise 2>/dev/null || echo "$HOME/.local/bin/mise")"
    real="$("$mise" -C "$HS_PLUGIN_ROOT" which python 2>/dev/null | tr '\\' '/' || true)"
    # se la cache dir non e' scrivibile non cachiamo e basta (si risolve ogni volta).
    [ -n "$real" ] && [ -x "$real" ] && { printf '%s' "$real" > "$cache" 2>/dev/null || true; }
  fi
  [ -x "$real" ] && printf '%s' "$real"
}

# Cache su file del valore FINALE di HS_PY (gia' de-shimmato): la lettura e' un
# read builtin (zero fork), la risoluzione sotto (command -v / mise = 1-2 fork a
# prompt) gira solo su cache-miss o se il binario e' sparito. NB: cache globale,
# primo-risolutore-vince — coerente con la cache mise qui sopra; install-hindsight
# la elimina insieme a hs-python-real.path quando il runtime puo' cambiare.
_hs_py_cache="$HS_CACHE_DIR/hs-python-final.path"
HS_PY=""
{ [ -f "$_hs_py_cache" ] && IFS= read -r HS_PY < "$_hs_py_cache"; } || true
if [ ! -x "$HS_PY" ]; then
HS_PY=""
# Ordine di risoluzione, dipendente dall'OS. $OSTYPE e' una variabile di bash (zero
# fork); `uname -s` costava ~475ms su MSYS/Windows (misurato 2026-07-28). Valori:
# linux-gnu / darwin* / cygwin (bash MSYS2) / msys.
case "$OSTYPE" in
linux* | darwin*)
  # Il python di sistema (spesso 3.9) precede quello di mise nel PATH e NON e' quello
  # con cui il plugin e' testato (3.13): i moduli sono scritti 3.9-safe (future
  # annotations, niente sintassi 3.10+ runtime), ma un domani un match/case romperebbe
  # in silenzio. Preferisci mise (cachato); fallback al PATH se mise non c'e'.
  HS_PY="$(_hs_mise_python)"
  [ -z "$HS_PY" ] && HS_PY="$(command -v python3 2>/dev/null || command -v python 2>/dev/null || true)"
  ;;
*)
  # Windows/MSYS: PATH-first (dentro Trinity il .mise.toml mette gia' il python
  # giusto nel PATH; veloce, nessun python eseguito), poi mise per i progetti
  # fuori-Trinity, infine MSYS UCRT64.
  HS_PY="$(command -v python 2>/dev/null || command -v python3 2>/dev/null || true)"
  # Scarta il python MSYS (/usr/bin/python, flavor cygwin): tratta i path
  # drive-letter (E:/...) come RELATIVI -> ModuleNotFoundError sui moduli in
  # HOOKS_DIR/lib e hook morti con exit 1 muto (visto 2026-07-30, quando
  # `pacman -S git-filter-repo` lo ha portato come dipendenza). Il pattern non
  # tocca /ucrt64/bin/python (nativo, va bene).
  case "$HS_PY" in */usr/bin/python*) HS_PY="" ;; esac
  [ -z "$HS_PY" ] && HS_PY="$(_hs_mise_python)"
  [ -z "$HS_PY" ] && [ -x /ucrt64/bin/python ] && HS_PY="/ucrt64/bin/python"
  ;;
esac
[ -z "$HS_PY" ] && HS_PY="python"

# Se il python risolto dal PATH e' uno shim mise (Windows dentro Trinity), bypassalo
# risolvendo il binario reale (stessa cache): evita i ~300ms dello shim a ogni hook.
case "$HS_PY" in
*/mise/shims/*)
  _hs_real="$(_hs_mise_python)"
  [ -n "$_hs_real" ] && HS_PY="$_hs_real"
  ;;
esac
# "python" nudo (fallback estremo) non e' un path: -x fallisce e non viene cachato.
[ -x "$HS_PY" ] && { printf '%s' "$HS_PY" > "$_hs_py_cache" 2>/dev/null || true; }
fi
unset -f _hs_mise_python 2>/dev/null || true
unset _hs_py_cache
export HS_PY
# UTF-8 garantito anche fuori da Trinity (il python MSYS UCRT64 usa cp1252 di
# default -> UnicodeEncodeError sul testo unicode delle memorie).
export PYTHONUTF8=1
