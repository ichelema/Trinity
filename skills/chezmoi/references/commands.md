# Commands and flags

Source: <https://www.chezmoi.io/reference/commands/>, <https://www.chezmoi.io/user-guide/command-overview/>.
`chezmoi help <cmd>` for the full flag list.

## Commands by task

**Setup**
| Command | Use |
|---------|-----|
| `init [repo]` | create/clone source dir, render config template |
| `doctor` | diagnose installation/config |
| `upgrade` | upgrade chezmoi binary |
| `completion bash\|zsh\|fish\|powershell` | shell completion |
| `generate install.sh` / `git-commit-message` | bootstrap script / commit message |

**Daily**
| Command | Use |
|---------|-----|
| `add <target>…` | start managing; `-T` template, `--encrypt`, `--exact`, `--create`, `--follow`, `-a` autotemplate, `--secrets error` |
| `edit <target>` | edit source; `--apply`, `--watch` |
| `re-add [target]` | copy modified targets back to source (**skips templates**, keeps encryption) |
| `status` | 2-column summary (see below) |
| `diff [target]` | diff target state vs disk; `--reverse`, `--pager` |
| `apply [target]` | write target state; `-n` dry run, `-v` verbose, `--force`, `-R` refresh externals |
| `update` | `git pull` + apply (`--apply=false` to only pull; `--init` to rerun config template) |
| `merge <target>` / `merge-all` | 3-way merge for conflicts |
| `cd` | shell in source dir |
| `git -- <args>` | run git in source dir (`chezmoi git -- log --oneline`) |
| `push` | `git add` + `commit` + `push` in the source dir in one step |

**Inspect**
| Command | Use |
|---------|-----|
| `managed` / `list` | managed targets (`-i files`, `-p absolute`, `--tree`) |
| `unmanaged` | files in `~` not managed |
| `ignored` | targets ignored by `.chezmoiignore` |
| `source-path [target]` | source file for a target (or source dir) |
| `target-path [source]` | target path for a source file |
| `cat <target>` | rendered target content |
| `data` | template data (`--format yaml`) |
| `execute-template [tmpl]` | render a template string/stdin; `--init`, `--override-data` |
| `cat-config` / `dump-config` / `dump` | config / parsed config / target state dump |
| `verify` | exit 1 if destination ≠ target |
| `archive` | tar/zip of the target state |
| `secret` | run password-manager CLI through chezmoi |

**Change attributes / stop managing**
| Command | Use |
|---------|-----|
| `chattr <attrs> <target>` | rename source to change attributes |
| `forget` / `unmanage` | stop managing (keeps target file) |
| `remove` / `rm` | remove target **and** source entry |
| `destroy` | remove target, source and state — **irreversible** |
| `purge` | delete chezmoi config, source and state from this machine |

**Encryption**: `encrypt`, `decrypt`, `edit-encrypted`, `age` (`age encrypt/decrypt --passphrase`), `age-keygen`.
**State**: `state` (see below). **Remote** (experimental, potentially destructive): `ssh <host> <user>` / `docker` / `podman` —
install chezmoi on the host/container, run `init --apply`, open a shell (`chezmoi ssh host -- --one-shot user`).
**Config**: `edit-config`, `edit-config-template`.

## `status` codes

Two columns, like `git status`:
- **1st**: difference between last state chezmoi wrote and what's on disk now (someone edited it).
- **2nd**: what `apply` will do.

| Code | 1st column | 2nd column |
|------|-----------|-----------|
| ` ` | no change | no change |
| `A` | entry was created | will be created |
| `D` | entry was deleted | will be deleted |
| `M` | entry was modified | will be modified |
| `R` | — | script will run |

`MM` = you edited the target *and* source changed → use `chezmoi merge` (or `diff` first).

## `chattr`

Attributes (abbr): `after`(a) `before`(b) `empty`(e) `encrypted` `exact` `executable`(x) `external`
`once`(o) `onchange` `private`(p) `readonly`(r) `remove` `template`(t).
Types: `create`, `modify`, `script`, `symlink`. Remove with `no`/`-` prefix.

```bash
chezmoi chattr +template ~/.bashrc
chezmoi chattr private,template ~/.netrc
chezmoi chattr -- -x ~/.zshrc               # `--` before a leading `-`
chezmoi chattr +create,+private ~/.kube/config
chezmoi chattr noempty ~/.profile
```

## `init` URL shorthand

| Arg | HTTPS (default) | `--ssh` |
|-----|-----------------|---------|
| `user` | `https://github.com/user/dotfiles.git` | `git@github.com:user/dotfiles.git` |
| `user/repo` | `https://github.com/user/repo.git` | `git@github.com:user/repo.git` |
| `gitlab.com/user/repo` | `https://gitlab.com/user/repo.git` | `git@gitlab.com:user/repo.git` |
| `sr.ht/~user` | `https://git.sr.ht/~user/dotfiles` | `git@git.sr.ht:~user/dotfiles.git` |

Useful flags: `--apply`, `--branch`, `--depth 1`, `--one-shot` (= apply + depth 1 + force + purge +
purge-binary; for throwaway containers), `--prompt` (force re-prompt of `*Once`), `--promptDefaults`,
`--promptString "Prompt text=value,Other prompt=v2"` (key = prompt text), `--promptBool`, `--promptChoice`, `-C <config path>`.

One-liner on a fresh machine:
```bash
sh -c "$(curl -fsLS get.chezmoi.io)" -- init --apply myuser
```
```powershell
iex "&{$(irm 'https://get.chezmoi.io/ps1')} -- init --apply myuser"
```

## `state` — reset script memory

```bash
chezmoi state delete-bucket --bucket=scriptState   # rerun all run_once_ scripts
chezmoi state delete-bucket --bucket=entryState    # rerun all run_onchange_ scripts
chezmoi state dump                                 # inspect
chezmoi state reset                                # wipe everything
```

## Global flags

| Flag | Meaning |
|------|---------|
| `-n, --dry-run` | change nothing |
| `-v, --verbose` | print actions + diffs |
| `--force` | no prompts on conflicts |
| `--interactive` / `--less-interactive` | prompt per target |
| `-k, --keep-going` | continue after errors |
| `-R, --refresh-externals[=always\|auto\|never]` | external cache |
| `-S, --source <dir>` / `-D, --destination <dir>` | override dirs (great for testing in a temp dir) |
| `-c, --config <file>` | alternate config |
| `-o, --output <file>` | write output to file |
| `--no-pager`, `--no-tty`, `--color`, `--progress` | output control |
| `--mode file\|symlink` | override mode |
| `--use-builtin-git`, `--use-builtin-age`, `--use-builtin-diff` | avoid external binaries |
| `--skip-secrets` | skip templates that need secrets |
| `--error-on-conflict` | fail instead of prompting (CI) |

## Common flags (many commands)

| Flag | Meaning |
|------|---------|
| `-i, --include <types>` / `-x, --exclude <types>` | types: `all,none,dirs,files,remove,scripts,symlinks,always,encrypted,externals,templates` (prefix `no` to negate) |
| `-r, --recursive` | recurse (default on for most) |
| `-P, --parent-dirs` | also act on parent dirs |
| `-p, --path-style` | `relative`, `absolute`, `source-relative`, `source-absolute`, `all` |
| `-f, --format json\|yaml` | structured output |
| `--init` | regenerate config from template first |
| `--override-data '{json}'` / `--override-data-file` | override template data |
| `--tree` | tree output |

Examples:
```bash
chezmoi apply -x scripts                  # files only, no scripts
chezmoi diff -i scripts                   # only show scripts
chezmoi managed -i files -p absolute
chezmoi apply -S ./dotfiles -D /tmp/test -n -v   # sandbox test
```
