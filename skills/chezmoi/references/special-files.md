# Special files and directories

Source: <https://www.chezmoi.io/reference/special-files/>, `/special-directories/`.

All source entries starting with `.` are ignored except these.

| Name | Purpose |
|------|---------|
| `.chezmoiroot` | Read first; contains a subdir name used as the real source root (lets the repo keep README, CI… outside) |
| `.chezmoiversion` | Minimum chezmoi version, e.g. `2.50.0`; older binaries refuse to run |
| `.chezmoi.<fmt>.tmpl` | Template for the config file, rendered by `chezmoi init` (see configuration.md) |
| `.chezmoidata.<fmt>` / `.chezmoidata/` | Static template data (json, jsonc, toml, yaml), merged in lexical order |
| `.chezmoiignore` | Target paths chezmoi must not touch |
| `.chezmoiremove` | Target paths to delete on apply |
| `.chezmoiexternal.<fmt>` / `.chezmoiexternals/` | Files/archives/git repos fetched from URLs |
| `.chezmoitemplates/` | Reusable named templates (see templates.md) |
| `.chezmoiscripts/` | Scripts that run without creating a target directory |

## `.chezmoiroot`

```
# repo layout
.chezmoiroot          ← contains: home
README.md
home/dot_zshrc
home/.chezmoiignore
```

All other special files are then relative to `home/`.

## `.chezmoidata.<fmt>` and `.chezmoidata/`

Static, shared data (not machine-specific — that goes in config `[data]`). **Not templates.**

```yaml
# .chezmoidata/packages.yaml
packages:
  darwin:
    brews: [git, ripgrep, fd]
    casks: [wezterm]
  linux:
    apt: [git, ripgrep, fd-find]
```

Not available inside `.chezmoi.<fmt>.tmpl` (that runs before the source state is read).

## `.chezmoiignore`

- Always a template; matches **target** paths (relative to destination) with doublestar globs.
- `#` comments (mid-line needs preceding whitespace); `!pattern` = exclude from ignore (excludes win over includes).
- A `.chezmoiignore` in a subdir applies only to that subdir.
- `README.md`, `LICENSE` etc. in the source root should be listed here or they'll be applied to `~`.

```
README.md
LICENSE
*.swp
.config/nvim/lazy-lock.json

{{ if ne .chezmoi.os "darwin" }}
Library/
.config/karabiner/
{{ end }}
{{ if ne .chezmoi.os "windows" }}
Documents/PowerShell/
AppData/
{{ end }}
{{ if not .isWork }}
.ssh/config.d/work
{{ end }}
```

Check: `chezmoi ignored` lists what's being ignored.

## `.chezmoiremove`

Template; one target-path pattern per line; matching entries are removed on apply.
Use for retiring old dotfiles across all machines. Preview with `chezmoi apply -n -v`.

```
.oldtoolrc
.config/legacy-app/**
```

## `.chezmoiexternal.<fmt>` / `.chezmoiexternals/*.<fmt>`

Always a template. Key = target path. Formats: toml, yaml, json, jsonc.

| Field | Meaning |
|-------|---------|
| `type` | `file`, `archive`, `archive-file`, `git-repo` |
| `url` / `urls` | source (https, http, file); `urls` = fallbacks |
| `refreshPeriod` | re-download interval, e.g. `"168h"` (default: never) |
| `exact` | archive dir: delete unlisted entries |
| `stripComponents` | drop leading path components from archive |
| `include` / `exclude` | archive member globs |
| `path` | member to extract (`archive-file`) |
| `format` | force archive format (`tar.gz`, `zip`…) |
| `decompress` | file: `gzip`, `bzip2`, `xz`, `zstd` |
| `executable`, `private`, `readonly`, `encrypted` | attributes |
| `checksum.sha256` / `.sha384` / `.sha512` / `.size` | integrity check |
| `filter.command` / `filter.args` | pipe content through a command |
| `clone.args` / `pull.args` | git-repo extra args |
| `targetPath` | override destination path |

```toml
[".oh-my-zsh"]
    type = "archive"
    url = "https://github.com/ohmyzsh/ohmyzsh/archive/master.tar.gz"
    exact = true
    stripComponents = 1
    refreshPeriod = "168h"

[".local/bin/age"]
    type = "archive-file"
    url = {{ gitHubLatestReleaseAssetURL "FiloSottile/age" (printf "age-*-%s-%s.tar.gz" .chezmoi.os .chezmoi.arch) | quote }}
    path = "age/age"
    executable = true

[".vim/autoload/plug.vim"]
    type = "file"
    url = "https://raw.githubusercontent.com/junegunn/vim-plug/master/plug.vim"
    refreshPeriod = "168h"

[".config/private-repo"]
    type = "git-repo"
    url = "git@github.com:me/private-repo.git"
    clone.args = ["--depth", "1"]
    pull.args = ["--ff-only"]
```

Notes:
- `git-repo` only clones/pulls; chezmoi doesn't manage the files inside. Prefer `archive` when possible.
- Inspect an archive first (`tar tzf` / `unzip -l`) to get `stripComponents` / `path` right.
- Force refresh: `chezmoi apply -R` (`--refresh-externals=always`); `-R never` for offline.
- Guard a private repo with `{{ if stat (joinPath .chezmoi.homeDir ".ssh/id_ed25519") }}`.

## `.chezmoiscripts/`

Scripts (with `run_` prefixes) placed here run normally but don't create a corresponding directory
in the target. Recommended home for all bootstrap scripts:

```
.chezmoiscripts/
  run_onchange_before_10-install-packages.sh.tmpl
  run_once_after_50-set-shell.sh
  windows/run_onchange_before_10-winget.ps1.tmpl
```
