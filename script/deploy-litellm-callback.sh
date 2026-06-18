#!/usr/bin/env bash
# Deploya la callback del proxy LiteLLM nella config dir del proxy.
#
# La fonte versionata è script/litellm-callbacks.py (questo repo); LiteLLM
# carica il modulo `callbacks` dalla dir del config (litellm_config.yaml),
# di default ~/.litellm/. Questo script copia la fonte nella destinazione.
#
# Portabile: $HOME si adatta al sistema (Windows MSYS2, Linux, macOS).
# Override della destinazione con LITELLM_CONFIG_DIR se il config sta altrove.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SRC="$SCRIPT_DIR/litellm-callbacks.py"
DST_DIR="${LITELLM_CONFIG_DIR:-$HOME/.litellm}"
DST="$DST_DIR/callbacks.py"

if [ ! -f "$SRC" ]; then
    echo "errore: sorgente non trovata: $SRC" >&2
    exit 1
fi
if [ ! -d "$DST_DIR" ]; then
    echo "errore: config dir non trovata: $DST_DIR (imposta LITELLM_CONFIG_DIR)" >&2
    exit 1
fi

cp "$SRC" "$DST"
echo "deployed: $SRC -> $DST"
echo "ricorda: riavvia il proxy per caricare la callback aggiornata."
