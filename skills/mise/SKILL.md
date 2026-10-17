---
name: mise
description: Convenzioni di mise in questo ambiente (Windows 11 + MSYS2 UCRT64 e Arch Linux): mise.toml, task, tool gestiti (Python, Node, Bun, Ruby) e cosa non fare da MSYS2. Usala quando tocchi mise.toml, scrivi o lanci un task, installi o fissi la versione di un tool, o un comando mise/node/npx si comporta in modo strano su Windows.
---

# mise

Indice: Serve · Regole di questo ambiente · Task · Tool e versioni · Riferimento

Questa skill contiene solo le convenzioni di questo ambiente. Per la sintassi
generale usa `mise <comando> --help` o https://mise.jdx.dev.

## Serve

- Arch Linux: `pacman -S --noconfirm mise`.
- Windows: binario nativo `mise.exe` in `~/.local/bin`
  (istruzioni: https://mise.jdx.dev/installing-mise.html).

## Regole di questo ambiente

| Fai | Non fare | Perché |
| --- | --- | --- |
| `mise run <task>` o `mise x -- <cmd>`; esporta solo le variabili che servono | `eval "$(mise env -s bash)"` da MSYS2 | corrompe il `PATH` |
| `node` e `npx` dagli shim di mise (`~/.local/share/mise/shims`) | `/ucrt64/bin/npx` (Node di MSYS2) | crasha (segfault, `bad_weak_ptr`) |
| Python, Node, Bun e Ruby dalla sezione `[tools]` di `mise.toml` | runtime MSYS2 per questi linguaggi | versioni diverse tra le macchine |
| pacchetti Python con `mise x python -- python -m pip install <pkg>` | `pip` di sistema | il pacchetto finisce nel Python sbagliato |
| codice con backslash in un file `.mjs`, poi `mise x bun -- bun file.mjs` | codice inline con backslash in `mise x bun -e '...'` da MSYS2 | MSYS2 perde i backslash negli argomenti |

## Task

- Ogni task di `mise.toml` dichiara `shell = "bash -c"`. Su Windows mise
  usa `cmd /c` come default. Non scrivere `/usr/bin/bash -c`: `mise.exe` è un
  programma Windows e non risolve i path MSYS2.
- I task del plugin vivono nel `mise.toml` del repo Trinity. Da qualsiasi
  cartella: `mise -C "$TRINITY_PLUGIN_DIR" run <task>`.
- In un worktree: `mise -C "<wt-path>" run <task>`.
- Elenco dei task: `mise -C "$TRINITY_PLUGIN_DIR" tasks`.
- Sulla VPS (Arch) le unit systemd usano
  `mise -C <repo> exec -- <cmd>` o `mise -C <repo> run <task>`.

## Tool e versioni

1. Prima di fissare una versione in `mise.toml`, controlla che il backend
   veda il tool: `mise ls-remote <backend>:<tool> | tail -5`.
2. Se `ls-remote` non restituisce niente, il binario può stare in un altro
   repo. Esempio: `github:juxt/allium` è vuoto, `github:juxt/allium-tools`
   ha le release. Cerca un repo `-tools`, `-cli` o `-releases`.
3. Per i binari delle release GitHub usa `github:owner/repo`. Il prefisso
   `ubi:` è deprecato.
4. Dopo la modifica esegui `mise install`. Controlla la versione attiva con
   `mise ls --current`.

## Riferimento

- `mise <comando> --help`
- `mise registry | grep <tool>` per trovare il nome del tool nel registry
- https://mise.jdx.dev
