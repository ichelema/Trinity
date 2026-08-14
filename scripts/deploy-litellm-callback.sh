#!/usr/bin/env bash
# Deploya i moduli Python del proxy LiteLLM nella config dir del proxy.
#
# Le fonti versionate stanno in scripts/ (questo repo); LiteLLM carica i moduli
# dalla dir del config (litellm_config.yaml), di default ~/.litellm/:
#   litellm-callbacks.py        -> callbacks.py         (pre-call hook)
#   litellm-responses-bridge.py -> responses_bridge.py  (ponte /v1/responses)
# I nomi di destinazione non sono arbitrari: `callbacks` è referenziato in
# litellm_settings.callbacks del config, `responses_bridge` è importato da
# ~/.local/bin/litellm-proxy-run.py.
#
# Portabile: $HOME si adatta al sistema (Windows MSYS2, Linux, macOS).
# Override della destinazione con LITELLM_CONFIG_DIR se il config sta altrove.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DST_DIR="${LITELLM_CONFIG_DIR:-$HOME/.litellm}"

MODULI=(
    "litellm-callbacks.py:callbacks.py"
    "litellm-responses-bridge.py:responses_bridge.py"
)

if [ ! -d "$DST_DIR" ]; then
    echo "errore: config dir non trovata: $DST_DIR (imposta LITELLM_CONFIG_DIR)" >&2
    exit 1
fi

for modulo in "${MODULI[@]}"; do
    src="$SCRIPT_DIR/${modulo%%:*}"
    dst="$DST_DIR/${modulo##*:}"
    if [ ! -f "$src" ]; then
        echo "errore: sorgente non trovata: $src" >&2
        exit 1
    fi
    cp "$src" "$dst"
    echo "deployed: $src -> $dst"
done

echo "ricorda: riavvia il proxy per caricare i moduli aggiornati."
