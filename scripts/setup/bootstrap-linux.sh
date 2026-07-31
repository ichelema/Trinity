#!/usr/bin/env bash
# Bootstrap di Trinity su un host Linux. IDEMPOTENTE: rieseguibile senza danni,
# ogni passo controlla lo stato prima di agire.
#
# Prerequisiti: git, curl, bash (il resto viene segnalato/installato qui).
# Uso:  bash scripts/setup/bootstrap-linux.sh
# Docs: docs/SETUP-LINUX.md (guida completa, incluse chiavi API e primo restore)
set -uo pipefail

case "$(uname -s)" in
Linux) : ;;
*)
	echo "[bootstrap] questo script e' solo per Linux (qui: $(uname -s))" >&2
	exit 1
	;;
esac

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
MISE="$HOME/.local/bin/mise"
OK=0
WARN=0
MCP_SKIPPED=""
ok() { echo "  [OK ] $1"; OK=$((OK + 1)); }
warn() {
	echo "  [!! ] $1" >&2
	WARN=$((WARN + 1))
}
sect() { printf '\n== %s ==\n' "$1"; }

sect "1. Prerequisiti di sistema"
MISSING=""
for bin in git curl jq lsof; do
	command -v "$bin" > /dev/null 2>&1 || MISSING="$MISSING $bin"
done
if [ -n "$MISSING" ]; then
	warn "mancano:$MISSING — installa con: sudo apt-get install -y$MISSING (o equivalente della distro)"
else
	ok "git, curl, jq, lsof presenti"
fi
# Opzionali: ffmpeg (yt-extract/suoni), notify-send (toast desktop).
command -v ffmpeg > /dev/null 2>&1 || echo "  [i  ] ffmpeg assente (opzionale: serve a yt-extract e ai suoni)"

sect "2. mise (gestore runtime)"
if command -v mise > /dev/null 2>&1; then
	MISE="$(command -v mise)"
	ok "mise gia' presente: $MISE"
elif [ -x "$MISE" ]; then
	ok "mise gia' presente: $MISE"
else
	echo "  installo mise..."
	curl -fsSL https://mise.run | sh || {
		warn "installazione mise fallita"
		exit 1
	}
	ok "mise installato in $MISE"
fi
grep -q 'mise activate' "$HOME/.bashrc" 2> /dev/null || {
	echo 'eval "$("$HOME/.local/bin/mise" activate bash)"' >> "$HOME/.bashrc"
	ok "mise activate aggiunto a ~/.bashrc"
}

sect "3. Runtime del repo (python/node/ruby via mise)"
"$MISE" trust "$ROOT/mise.toml" > /dev/null 2>&1 || true
if "$MISE" -C "$ROOT" install; then
	ok "runtime installati (mise install)"
else
	warn "mise install ha riportato errori — controlla l'output"
fi

sect "4. hindsight-api (server memoria) + mcp-remote (bridge shim)"
if "$MISE" -C "$ROOT" run install-hindsight > /dev/null 2>&1; then
	ok "hindsight-api installato/aggiornato"
	"$MISE" reshim > /dev/null 2>&1 || true
else
	warn "install-hindsight fallito (rete/proxy?)"
fi
if "$MISE" -C "$ROOT" x -- npm ls -g mcp-remote > /dev/null 2>&1; then
	ok "mcp-remote gia' presente"
elif "$MISE" -C "$ROOT" x -- npm install -g mcp-remote > /dev/null 2>&1; then
	ok "mcp-remote installato (npm -g)"
else
	warn "npm install -g mcp-remote fallito — lo shim MCP hindsight non partira'"
fi

sect "5. Skills-dir: symlink ~/.claude/skills/* -> repo"
mkdir -p "$HOME/.claude/skills"
# link_skill NOME TARGET: crea/ripara ~/.claude/skills/NOME -> TARGET
link_skill() {
	local link="$HOME/.claude/skills/$1" target="$2"
	if [ -L "$link" ]; then
		# readlink -f su ENTRAMBI i lati: se il path del repo contiene un componente
		# symlink, il target logico non combacia mai col target risolto del link e il
		# symlink verrebbe "ricreato" a ogni run pur essendo corretto.
		if [ "$(readlink -f "$link")" = "$(readlink -f "$target")" ]; then
			ok "symlink $1 gia' corretto"
		else
			# Symlink presente ma verso il target sbagliato o PENDENTE (clone rimosso/spostato).
			# Il ramo -e sotto NON lo intercetta: su un link pendente -e e' falso, quindi si
			# finiva nell'else dove `ln -s` fallisce ("File exists") -> nessuna riparazione,
			# nessun avviso, plugin non caricato. Rimuovere un symlink e' sicuro: cancella il
			# puntatore, non il target.
			rm -f "$link" && ln -s "$target" "$link" \
				&& ok "symlink $1 ricreato (era verso un target errato/pendente): $link -> $target" \
				|| warn "impossibile ricreare il symlink $link"
		fi
	elif [ -e "$link" ]; then
		warn "$link esiste ma e' una dir/file reale, non un symlink — sistemalo a mano (rm e rilancia)"
	else
		ln -s "$target" "$link" && ok "symlink $1 creato: $link -> $target"
	fi
}
link_skill trinity "$ROOT"
link_skill ui-craft "$ROOT/vendor/ui-craft"
link_skill claude-bionify "$ROOT/vendor/claude-bionify"

sect "6. Env utente in ~/.claude/settings.json"
SETTINGS="$HOME/.claude/settings.json"
"$MISE" -C "$ROOT" x -- python - "$SETTINGS" "$ROOT" <<'PY'
import json, os, sys
path, root = sys.argv[1], sys.argv[2]
data = {}
if os.path.exists(path):
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
env = data.setdefault("env", {})
changed = False
if env.get("TRINITY_PLUGIN_DIR") != root:
    env["TRINITY_PLUGIN_DIR"] = root
    changed = True
if changed:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    print("  [OK ] TRINITY_PLUGIN_DIR impostata in", path)
else:
    print("  [OK ] TRINITY_PLUGIN_DIR gia' corretta")
print("  [i  ] OBSIDIAN_VAULT/OBSIDIAN_VAULT_NAME: impostale qui solo se il vault esiste su questa macchina")
PY

sect "7. Git hooks del repo"
if [ "$(git -C "$ROOT" config core.hooksPath 2> /dev/null)" = ".githooks" ]; then
	ok "core.hooksPath gia' .githooks"
else
	git -C "$ROOT" config core.hooksPath .githooks && ok "core.hooksPath impostato"
fi

sect "8. Server MCP hindsight (scope user)"
SHIM="$ROOT/hooks/hindsight/mcp/hindsight-mcp-shim.sh"
if command -v claude > /dev/null 2>&1; then
	if claude mcp get hindsight > /dev/null 2>&1; then
		ok "server MCP hindsight gia' registrato"
	else
		claude mcp add-json hindsight "{\"type\":\"stdio\",\"command\":\"$SHIM\"}" --scope user \
			&& ok "server MCP hindsight registrato (scope user)" \
			|| warn "registrazione MCP fallita"
	fi
else
	MCP_SKIPPED=1
	warn "claude CLI non trovato: la registrazione MCP e' saltata — rilancia questo script (idempotente) dopo aver installato claude"
fi

sect "9. Directory dei backup DB"
mkdir -p "$HOME/backups/hindsight" && ok "~/backups/hindsight pronta"

sect "10. Language server (LSP) — opzionali, per la navigazione codice"
# .lsp.json abilita 4 server; run-lsp.sh li risolve via shim mise, ~/.local/bin
# (tarball) o PATH. Come per i prerequisiti di sistema al passo 1, il bootstrap NON
# li installa: li rileva e, se mancano, stampa il comando (niente sudo qui dentro).
# Coppie "binario da cercare : pacchetto da installare" (il binario di pyright e'
# pyright-langserver, ma il pacchetto e' pyright).
LSP_SHIMS="$HOME/.local/share/mise/shims"
lsp_present() {
	[ -x "$LSP_SHIMS/$1" ] && return 0
	[ -x "$HOME/.local/bin/$1/bin/$1" ] && return 0
	command -v "$1" > /dev/null 2>&1
}
MISSING_LSP=""
for pair in \
	typescript-language-server:typescript-language-server \
	pyright-langserver:pyright \
	ruby-lsp:ruby-lsp \
	lua-language-server:lua-language-server; do
	lsp_present "${pair%%:*}" || MISSING_LSP="$MISSING_LSP ${pair##*:}"
done
if [ -z "$MISSING_LSP" ]; then
	ok "4 language server presenti (typescript, pyright, ruby-lsp, lua)"
elif command -v pacman > /dev/null 2>&1; then
	warn "LSP mancanti (opzionali):$MISSING_LSP — installa con: sudo pacman -S --needed$MISSING_LSP"
else
	warn "LSP mancanti (opzionali):$MISSING_LSP — installali col package manager della distro (su Arch: extra/*, un solo pacman -S)"
fi

sect "11. Server MCP opzionali del plugin (playwright, notebooklm, obsidian)"
# .mcp.json versionato definisce anche server pensati per il PC Windows. Come per
# gli LSP al passo 10: si rileva e si segnala, niente install automatico. Dettagli
# e alternativa disabledMcpjsonServers in docs/SETUP-LINUX.md ("Server MCP del
# plugin su Linux").
if "$MISE" -C "$ROOT" x -- npm ls -g @playwright/mcp > /dev/null 2>&1; then
	ok "@playwright/mcp presente (npm -g)"
else
	warn "playwright MCP: manca @playwright/mcp — installa con: mise -C \"$ROOT\" x -- npm install -g @playwright/mcp (serve anche un browser), oppure disabilitalo in ~/.claude/settings.json (disabledMcpjsonServers)"
fi
echo "  [i  ] notebooklm resta spento (warning innocuo) finche' NOTEBOOKLM_DATA/NOTEBOOKLM_LIB non sono definite in ~/.claude/settings.json"
echo "  [i  ] obsidian_semantic_notes_vault richiede Obsidian in esecuzione su questo host: senza, disabilitalo (disabledMcpjsonServers)"

sect "Riepilogo"
echo "  passi ok: $OK, avvisi: $WARN"
echo
echo "Prossimi passi (vedi docs/SETUP-LINUX.md):"
# Punto condizionale fuori dall'heredoc: dentro ${VAR:+...} l'apostrofo di "l'MCP"
# aprirebbe una stringa quotata e romperebbe l'espansione (bad substitution).
[ -n "$MCP_SKIPPED" ] && echo "  0. registra l'MCP hindsight:   installa claude, poi rilancia  bash scripts/setup/bootstrap-linux.sh"
cat <<EOF
  1. chiavi API in ~/.profile:  export OPENAI_API_KEY=... ZEROENTROPY_API_KEY=...
  2. primo avvio:               mise -C "$ROOT" run start-hindsight
  3. importa la memoria:        mise -C "$ROOT" run db-restore  (dump dalla chiavetta o via scp)
  4. timer schedulati:          vedi scheduler/systemd/README.md
EOF
exit 0
