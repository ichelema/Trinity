#!/usr/bin/env bash
# Logica condivisa dai git hook post-commit / post-merge.
#
# Se la sorgente versionata della callback LiteLLM è tra i file cambiati,
# lancia il deploy idempotente che la copia in $HOME/.litellm/callbacks.py
# (o $LITELLM_CONFIG_DIR). Nessun path hardcoded: la destinazione la decide
# script/deploy-litellm-callback.sh.

TARGET="script/litellm-callbacks.py"

# deploy_if_changed <file>...  — $@ = elenco di path (relativi alla root repo)
deploy_if_changed() {
	local f
	for f in "$@"; do
		if [ "$f" = "$TARGET" ]; then
			local repo
			repo="$(git rev-parse --show-toplevel)"
			echo "[git hook] $TARGET modificato → deploy callback LiteLLM"
			bash "$repo/script/deploy-litellm-callback.sh"
			return $?
		fi
	done
}
