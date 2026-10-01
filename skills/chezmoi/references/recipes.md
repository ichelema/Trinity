# Recipes

Copy-and-adapt patterns. Each assumes data keys defined in `.chezmoi.toml.tmpl` (see configuration.md).

## Repo layout that scales

```
dotfiles/
├── .chezmoiroot                 # "home"
├── README.md
└── home/
    ├── .chezmoi.toml.tmpl
    ├── .chezmoiversion
    ├── .chezmoiignore
    ├── .chezmoidata/packages.yaml
    ├── .chezmoiexternal.toml
    ├── .chezmoitemplates/
    ├── .chezmoiscripts/
    ├── dot_config/
    ├── private_dot_ssh/
    └── dot_zshrc.tmpl
```

## Machine roles (work / home / server)

```toml
# .chezmoi.toml.tmpl
{{- $isWork := promptBoolOnce . "isWork" "Work machine" -}}
{{- $headless := not stdinIsATTY -}}
[data]
    isWork = {{ $isWork }}
    headless = {{ $headless }}
```

```ini
# dot_gitconfig.tmpl
[user]
    name = {{ .name | quote }}
    email = {{ if .isWork }}{{ .workEmail | quote }}{{ else }}{{ .email | quote }}{{ end }}
[includeIf "gitdir:~/work/"]
    path = ~/.gitconfig-work
```

Hide whole files per role in `.chezmoiignore`:
```
{{ if not .isWork }}.gitconfig-work{{ end }}
{{ if .headless }}.config/wezterm/{{ end }}
```

## Install packages when the list changes

```yaml
# .chezmoidata/packages.yaml
packages:
  darwin: { brews: [git, ripgrep, fd, chezmoi], casks: [wezterm] }
  linux:  { apt: [git, ripgrep, fd-find] }
  windows: { winget: [Git.Git, BurntSushi.ripgrep.MSVC, sharkdp.fd] }
```

```sh
# .chezmoiscripts/run_onchange_before_10-packages-darwin.sh.tmpl
{{ if eq .chezmoi.os "darwin" -}}
#!/bin/bash
set -euo pipefail
brew bundle --file=/dev/stdin <<EOF
{{ range .packages.darwin.brews -}}
brew {{ . | quote }}
{{ end -}}
{{ range .packages.darwin.casks -}}
cask {{ . | quote }}
{{ end -}}
EOF
{{ end -}}
```

The script content embeds the list, so editing `packages.yaml` changes the rendered script → reruns.
For a script that reads an external file instead, embed its hash:
```sh
# Brewfile hash: {{ include "dot_Brewfile" | sha256sum }}
brew bundle --global
```

## Windows

```powershell
# .chezmoiscripts/run_onchange_before_10-winget.ps1.tmpl
{{ if eq .chezmoi.os "windows" -}}
{{ range .packages.windows.winget -}}
winget install --id {{ . }} --exact --silent --accept-package-agreements --accept-source-agreements
{{ end -}}
{{ end -}}
```

- Scripts: use `.ps1` (runs with `pwsh`, falls back to `powershell`); `.sh` needs an interpreter entry
  pointing at Git Bash (configuration.md).
- Paths: `.chezmoi.homeDir` has `/`; use `.chezmoi.rawHomeDir` or `joinPath` when a tool needs `\`.
- Windows-only targets: `AppData/Roaming/…`, `Documents/PowerShell/Microsoft.PowerShell_profile.ps1`
  → ignore them on other OSes in `.chezmoiignore`, and ignore `.config/…` Unix-only files on Windows.
- `private_`/`executable_`/`readonly_` have little/no effect on NTFS.
- `symlink_` requires Developer Mode or admin; otherwise prefer plain files.
- Line endings: `{{/* chezmoi:template:line-endings=crlf */}}` for files that need CRLF;
  set `git config core.autocrlf false` in the source repo to avoid git rewriting them.
- Editor: `[edit] command = "code" args = ["--wait"]`.

## Same file, different location per OS

Keep one source file and point targets at it via `.chezmoitemplates`:

```
.chezmoitemplates/vscode-settings.json
dot_config/Code/User/settings.json.tmpl                 →  {{ template "vscode-settings.json" . }}
AppData/Roaming/Code/User/settings.json.tmpl            →  {{ template "vscode-settings.json" . }}
Library/Application Support/Code/User/settings.json.tmpl → (same)
```
Then ignore the non-matching locations per OS in `.chezmoiignore`.

## Manage only part of a file an app also writes

JSON (e.g. VS Code, Windows Terminal) — `modify_` template:

```
{{- /* chezmoi:modify-template */ -}}
{{- $s := dict -}}
{{- if .chezmoi.stdin }}{{ $s = fromJsonc .chezmoi.stdin }}{{ end -}}
{{- $_ := set $s "editor.fontSize" 14 -}}
{{- $_ := set $s "files.eol" "\n" -}}
{{ toPrettyJson $s }}
```

VS Code keys like `editor.fontSize` are **literal** top-level keys → use sprig `set`.
`setValueAtPath "a.b" v` splits on dots and creates nested objects — right for real nesting
(Windows Terminal `profiles.defaults.fontSize`), wrong here.

INI/TOML/YAML: same with `fromIni`/`toIni`, `fromToml`/`toToml`, `fromYaml`/`toYaml`.
Alternative for "set once, then let the app own it": `create_` prefix.

## Shell config split into fragments

```
dot_config/zsh/
  dot_zshrc.tmpl          # sources conf.d/*.zsh
  conf.d/
    10-path.zsh.tmpl
    20-aliases.zsh
    {{/* OS-specific fragments ignored via .chezmoiignore */}}
```

## Tool binaries from GitHub releases

```toml
# .chezmoiexternal.toml
[".local/bin/fzf"]
    type = "archive-file"
    url = {{ gitHubLatestReleaseAssetURL "junegunn/fzf" (printf "fzf-*-%s_%s.tar.gz" .chezmoi.os .chezmoi.arch) | quote }}
    path = "fzf"
    executable = true
    refreshPeriod = "168h"
```
(Or delegate tool installs to mise/brew/winget and keep chezmoi for config only.)

## SSH authorized_keys from GitHub

```
# private_dot_ssh/authorized_keys.tmpl
{{ range gitHubKeys "myuser" -}}
{{ .Key }}
{{ end -}}
```

## Pull edits made directly in `~` back into the source

```bash
chezmoi status            # 'M ' in 1st column → target changed outside chezmoi
chezmoi diff ~/.zshrc     # see what differs
chezmoi re-add ~/.zshrc   # plain files
chezmoi merge ~/.zshrc    # templates (re-add won't touch them)
```

## Test safely in a sandbox

```bash
chezmoi apply -S ~/.local/share/chezmoi -D /tmp/chez-test -v
chezmoi apply -n -v                                # dry run against real home
chezmoi apply -x scripts -n -v                     # files only
docker run --rm -it ubuntu sh -c 'apt-get update && apt-get install -y curl git && sh -c "$(curl -fsLS get.chezmoi.io)" -- init --apply myuser'
```

## Auto-commit and push on every change

```toml
[git]
    autoCommit = true
    autoPush = true      # implies autoCommit; mind pushing secrets — keep them encrypted/templated
```
