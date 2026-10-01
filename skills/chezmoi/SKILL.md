---
name: chezmoi
description: Expert guide for managing dotfiles with chezmoi — source-state naming (dot_, private_, run_onchange_, modify_, exact_…), Go templates and .chezmoi.* variables, .chezmoiignore/.chezmoiexternal/.chezmoidata, config file (chezmoi.toml), scripts and hooks, age/gpg encryption, password-manager secrets (Bitwarden, 1Password, KeePassXC…), multi-machine and Windows/macOS/Linux setups, and every chezmoi CLI command. Use this skill whenever the user mentions chezmoi, dotfiles, ~/.local/share/chezmoi, *.tmpl dotfile templates, syncing shell/editor/git config across machines, or bootstrapping a new machine from a dotfiles repo — even if they don't say "chezmoi" explicitly.
---

# chezmoi

chezmoi manages dotfiles across machines: it keeps a **source state** (a git repo) and computes
from it the **target state** that it writes into the **destination** (usually `~`).

## Mental model

```
source dir (~/.local/share/chezmoi)   +   config (~/.config/chezmoi/chezmoi.toml)
        │  file names encode attributes        │  machine-specific data
        └──────────────► target state ◄────────┘
                            │  chezmoi apply
                            ▼
                   destination (~)  ← what's actually on disk
```

- **Source state**: only regular files/dirs; attributes live in the *name* (`private_dot_ssh/` → `~/.ssh` mode 0700).
- **Target state**: computed result — files, dirs, symlinks, scripts to run, entries to remove.
- **Destination state**: what's on disk right now. `status`/`diff` compare it with the target.
- Config file is per-machine and **not** in the repo; generate it from `.chezmoi.toml.tmpl` at `init`.

Rule of thumb: **edit the source, never the target.** Editing `~/.zshrc` directly gets overwritten
on the next `apply` (use `chezmoi edit`, or `chezmoi re-add` / `chezmoi merge` to pull changes back).

## Core workflow

```bash
chezmoi init                     # new source repo   |  chezmoi init --apply <github-user>  # existing one
chezmoi add ~/.zshrc             # start managing (add -T for template, --encrypt for secrets)
chezmoi edit --apply ~/.zshrc    # edit source + apply
chezmoi status                   # what apply would do (2-letter codes)
chezmoi diff                     # full diff target vs disk
chezmoi apply -v                 # write it   (-n = dry run)
chezmoi cd && git commit -am … && git push   # or chezmoi git -- …
chezmoi update                   # on other machines: git pull + apply
```

## Before you act

1. **Inspect, don't guess.** `chezmoi source-path <target>` gives the real source file name;
   `chezmoi data` shows template variables; `chezmoi doctor` shows setup problems.
2. **Preview every change**: `chezmoi diff` or `chezmoi apply -n -v` before `apply`.
   Destructive features (`exact_`, `remove_`, `.chezmoiremove`, `destroy`, `purge`) delete real files.
3. **Test templates in isolation**: `chezmoi execute-template < file.tmpl`, or
   `chezmoi cat ~/.target` to see the rendered result without writing anything.
4. **Secrets never go in plain text** in the repo: use a password-manager function or `--encrypt`.

## Where to look — references

Load only the file the task needs.

| Task | Read |
|------|------|
| File/dir naming: `dot_`, `private_`, `exact_`, `create_`, `modify_`, `remove_`, `symlink_`, scripts `run_once_/onchange_/before_/after_`, prefix order, apply order | [references/source-state.md](references/source-state.md) |
| Templates: `.chezmoi.*` variables, functions (sprig + chezmoi), `prompt*Once`, directives, `.chezmoitemplates`, debugging | [references/templates.md](references/templates.md) |
| Special files/dirs: `.chezmoiignore`, `.chezmoiexternal`, `.chezmoidata`, `.chezmoiremove`, `.chezmoiroot`, `.chezmoiversion`, `.chezmoiscripts/` | [references/special-files.md](references/special-files.md) |
| Config file `chezmoi.toml`: variables, editor/diff/merge tools, git auto-commit, hooks, interpreters, `.chezmoi.toml.tmpl` | [references/configuration.md](references/configuration.md) |
| Full command list, flags, `status` codes, `chattr`, `state` reset, `init` URL shorthand | [references/commands.md](references/commands.md) |
| Encryption (age/gpg) and password managers (Bitwarden, 1Password, KeePassXC, pass, generic `secret`) | [references/secrets.md](references/secrets.md) |
| Ready-made patterns: multi-machine, package install scripts, Windows, partial-file edits, bootstrap | [references/recipes.md](references/recipes.md) |

## Top pitfalls

- **Prefix order matters**: `private_executable_dot_foo` ✓, `dot_private_foo` ✗ (becomes a file literally named `.private_foo`). See source-state.md.
- **`.chezmoitemplates/` is used with `template`/`includeTemplate`**, not `include` (which reads a raw file).
- **Whitespace**: use `{{-` / `-}}` so conditionals don't leave blank lines.
- **`run_onchange_` reruns only when the script's rendered content changes** — embed a hash of the
  data it depends on (`# hash: {{ include "Brewfile" | sha256sum }}`) to trigger it.
- **`.chezmoiignore` matches target paths** (`.zshrc`), not source names (`dot_zshrc`), and is always a template.
- **`re-add` skips templates** — for templated files edit the source, or use `chezmoi merge`.
- **Init functions (`promptStringOnce`…) only work in `.chezmoi.<fmt>.tmpl`**; elsewhere use data from the config.
- **Literal `{{` in a config template** (e.g. `merge.args`) must be escaped: `{{ "{{ .Destination }}" }}`.
- **Windows**: permission prefixes (`private_`, `executable_`) are mostly no-ops; symlinks need Developer Mode;
  `.ps1` scripts run via `pwsh`. See recipes.md.
