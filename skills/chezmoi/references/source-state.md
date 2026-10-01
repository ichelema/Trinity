# Source state: names, attributes, target types

Source: <https://www.chezmoi.io/reference/source-state-attributes/>, `/target-types/`, `/application-order/`.

## Prefixes

| Prefix | Effect |
|--------|--------|
| `dot_` | Leading dot: `dot_foo` → `.foo` |
| `private_` | Remove group/world permissions (file 0600, dir 0700) |
| `readonly_` | Remove all write permissions |
| `executable_` | Add executable bits |
| `empty_` | Keep the file even if empty (empty files are removed by default) |
| `encrypted_` | Source content is encrypted (age/gpg) |
| `exact_` | Directory: **delete** anything in the target dir not managed by chezmoi |
| `external_` | Directory: ignore attributes of child entries (keep names verbatim) |
| `create_` | Create the file only if missing; never overwrite afterwards |
| `modify_` | Content is a script/template that transforms the existing file |
| `remove_` | Remove the target file/symlink (or dir if empty) |
| `symlink_` | Create a symlink; content = link target |
| `run_` | Content is a script to execute |
| `once_` | Script: run only if this content never ran successfully |
| `onchange_` | Script: run if this content never ran successfully *with this filename* |
| `before_` / `after_` | Script: run before / after updating files |
| `literal_` | Stop parsing prefixes (for names that clash with attributes) |

## Suffixes

| Suffix | Effect |
|--------|--------|
| `.tmpl` | Treat content as a Go template |
| `.literal` | Stop parsing suffixes |
| `.age` / `.asc` | Stripped from encrypted files (configurable via `age.suffix` / `gpg.suffix`) |

## Allowed attributes per target type (order is mandatory)

| Target | Prefixes, in order | Suffixes |
|--------|--------------------|----------|
| Directory | `remove_`, `external_`, `exact_`, `private_`, `readonly_`, `dot_` | — |
| Regular file | `encrypted_`, `private_`, `readonly_`, `empty_`, `executable_`, `dot_` | `.tmpl` |
| Create file | `create_`, `encrypted_`, `private_`, `readonly_`, `empty_`, `executable_`, `dot_` | `.tmpl` |
| Modify file | `modify_`, `encrypted_`, `private_`, `readonly_`, `executable_`, `dot_` | `.tmpl` |
| Remove | `remove_`, `dot_` | — |
| Script | `run_`, `once_` **or** `onchange_`, `before_` **or** `after_` | `.tmpl` |
| Symlink | `symlink_`, `dot_` | `.tmpl` |

Examples:

```
private_dot_ssh/                         → ~/.ssh            (0700)
private_dot_ssh/encrypted_private_id_ed25519.age → ~/.ssh/id_ed25519 (0600, decrypted)
dot_config/exact_nvim/                   → ~/.config/nvim    (unmanaged files deleted!)
executable_dot_local/bin/…               ✗ wrong: executable_ is for files
dot_local/bin/executable_backup.sh       → ~/.local/bin/backup.sh (+x)
create_dot_npmrc                         → ~/.npmrc only if absent
symlink_dot_vimrc                        → ~/.vimrc → (file content)
run_onchange_after_10-reload.sh.tmpl     → script, after files, on content change
literal_run_me.txt                       → ~/run_me.txt (a plain file)
```

Don't hand-craft names when unsure: `chezmoi add` with flags (`--template`, `--encrypt`, `--exact`,
`--create`) or `chezmoi chattr +private,+template ~/.netrc` produce correct names.

Files/dirs starting with `.` in the source are ignored unless they are `.chezmoi*` special files.

## Target types in detail

### `create_`
Writes the content only when the target doesn't exist. Good for files apps later modify
(e.g. initial settings).

### `modify_` — manage part of a file
Two modes:

1. **Template mode** (preferred, cross-platform): the file contains `chezmoi:modify-template`.
   That line is removed, the rest runs as a template; the current file content is in `.chezmoi.stdin`.
   ```
   {{- /* chezmoi:modify-template */ -}}
   {{ fromJson .chezmoi.stdin | setValueAtPath "profiles.defaults.fontSize" 12 | toPrettyJson }}
   ```
2. **Script mode**: an executable that reads the current file on stdin and writes the new content
   on stdout. Empty stdin = file doesn't exist yet.
   ```sh
   #!/bin/sh
   # modify_dot_gitconfig — keep everything, force one value
   sed 's/^\([[:space:]]*autocrlf[[:space:]]*=\).*/\1 input/'
   ```

### `remove_`
`remove_dot_oldrc` (empty file) deletes `~/.oldrc`. For patterns use `.chezmoiremove`.

### `exact_` directories
Any entry in the target dir not in the source is **deleted** on apply. Check with
`chezmoi apply -n -v` first. Use `.chezmoiignore` to protect specific files.

### Symlinks
`symlink_name` content (trailing newlines stripped) is the link target. With `.tmpl`:
```
{{ .chezmoi.sourceDir }}/shared/config.yaml
```
Empty/whitespace-only content → symlink removed.
`mode = "symlink"` in config makes plain files symlinks into the source dir (except encrypted,
executable, private, or templated files).

## Scripts

| Name | Runs |
|------|------|
| `run_x.sh` | every `apply` |
| `run_once_x.sh` | once per distinct content (keyed by content hash, not name) |
| `run_onchange_x.sh` | whenever the content changes (also keyed by name) |
| `…before_…` / `…after_…` | before / after all files are updated |

- Templated scripts (`.tmpl`) are rendered first; a script that renders to empty/whitespace is skipped
  — use this for OS conditionals.
- Working dir = the script's equivalent location in the destination (or nearest existing parent).
- Env: `CHEZMOI=1`, `CHEZMOI_*` vars, plus `env`/`scriptEnv` from config.
- Interpreter chosen by extension (`.ps1`, `.py`, `.nu`, …) — see configuration.md.
- Put scripts in `.chezmoiscripts/` to keep them out of the target tree (no dir is created).
- Force a rerun: `chezmoi state delete-bucket --bucket=scriptState` (once) / `--bucket=entryState` (onchange).

Ordering: numeric prefixes sort ASCII, e.g. `run_onchange_before_10-packages.sh`, `…before_20-fonts.sh`.

## Application order

1. Read source state → 2. read destination state → 3. compute target state
4. `run_before_` scripts, alphabetical
5. Update files/dirs/symlinks alphabetically **by target name** (attributes stripped), dirs before contents;
   scripts without before/after run in this pass at their sorted position
6. `run_after_` scripts, alphabetical

`run_before_` scripts can't rely on externals (applied in step 5); `run_after_` can.
