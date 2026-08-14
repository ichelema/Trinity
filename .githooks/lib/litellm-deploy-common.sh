#!/usr/bin/env bash
# Logica condivisa dai git hook post-commit / post-merge.
#
# Se una delle sorgenti versionate dei moduli LiteLLM è tra i file cambiati,
# lancia il deploy idempotente che le copia in $HOME/.litellm/ (o in
# $LITELLM_CONFIG_DIR). Nessun path hardcoded: la destinazione la decide
# scripts/deploy-litellm-callback.sh.

TARGETS=(
	"scripts/litellm-callbacks.py"
	"scripts/litellm-responses-bridge.py"
)

# deploy_if_changed <file>...  — $@ = elenco di path (relativi alla root repo)
deploy_if_changed() {
	local f t
	for f in "$@"; do
		for t in "${TARGETS[@]}"; do
			if [ "$f" = "$t" ]; then
				local repo
				repo="$(git rev-parse --show-toplevel)"
				echo "[git hook] $f modificato → deploy moduli LiteLLM"
				bash "$repo/scripts/deploy-litellm-callback.sh"
				return $?
			fi
		done
	done
}
