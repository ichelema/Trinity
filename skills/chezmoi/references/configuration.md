# Configuration file

Source: <https://www.chezmoi.io/reference/configuration-file/>.

Location: `~/.config/chezmoi/chezmoi.{toml,yaml,json,jsonc}` (Windows: `%USERPROFILE%\.config\chezmoi\`).
Machine-specific, **not committed**. Commands: `chezmoi edit-config`, `cat-config`, `dump-config`,
`edit-config-template`. Use `-c path` to pick another file.

## Generate it from `.chezmoi.<fmt>.tmpl`

Lives in the source root; rendered by `chezmoi init` (and by any command with `--init`, e.g.
`chezmoi update --init`). Runs **before** the source state is read: config data, template functions
and init functions are available; `.chezmoidata` and `.chezmoitemplates` are **not**.

```toml
{{- $email := promptStringOnce . "email" "Email address" -}}
{{- $isWork := promptBoolOnce . "isWork" "Is this a work machine" -}}
{{- $role := promptChoiceOnce . "role" "Machine role" (list "desktop" "server" "wsl") -}}

encryption = "age"

[age]
    identity = {{ joinPath .chezmoi.homeDir ".config/chezmoi/key.txt" | quote }}
    recipient = "age1…"

[data]
    email = {{ $email | quote }}
    isWork = {{ $isWork }}
    role = {{ $role | quote }}

[git]
    autoCommit = true
    autoPush = true

[diff]
    exclude = ["scripts"]

[merge]
    command = "nvim"
    args = ["-d", {{ "{{ .Destination }}" | quote }}, {{ "{{ .Source }}" | quote }}, {{ "{{ .Target }}" | quote }}]
```

Top-level keys (like `encryption`) must come **before** any `[section]` in TOML.
When the template changes, chezmoi warns that the config is out of date → run `chezmoi init`.

## Top-level variables

| Key | Default | Notes |
|-----|---------|-------|
| `sourceDir` | `~/.local/share/chezmoi` | source state |
| `destDir` | `~` | destination |
| `workingTree` | sourceDir | git working tree if different |
| `mode` | `file` | `symlink` = link plain files into source |
| `encryption` | — | `age`, `gpg`, `transparent` |
| `umask` | system | e.g. `0o022` |
| `pager`, `color`, `verbose`, `progress` | | output |
| `env` / `scriptEnv` | — | extra env vars for scripts (and hooks for `scriptEnv`) |
| `scriptTempDir` | — | where rendered scripts are written (if /tmp is noexec) |

## Sections

| Section | Useful keys |
|---------|-------------|
| `[data]` | anything → available as `.key` in templates |
| `[add]` | `encrypt` (default false), `secrets` (`ignore`/`warning`/`error`), `templateSymlinks` |
| `[edit]` | `command`, `args`, `apply` (apply on exit), `watch` (apply on save), `hardlink` |
| `[diff]` | `command`, `args`, `pager`, `exclude` (e.g. `["scripts"]`), `reverse`, `scriptContents` |
| `[merge]` | `command` (default `vimdiff`), `args` with `{{ .Destination }}` `{{ .Source }}` `{{ .Target }}` |
| `[git]` | `autoAdd`, `autoCommit`, `autoPush`, `commitMessageTemplate[File]`, `lfs`, `command` |
| `[update]` | `apply` (default true), `recurseSubmodules`, `command`/`args` (custom update) |
| `[status]` | `exclude`, `pathStyle` |
| `[template]` | `options` (default `["missingkey=error"]`) |
| `[cd]` | `command`, `args` (shell for `chezmoi cd`) |
| `[age]` / `[gpg]` | see secrets.md |
| `[bitwarden]`, `[onepassword]`, `[keepassxc]`, `[secret]`… | see secrets.md |
| `[gitHub]` | `refreshPeriod` for GitHub template functions |
| `[textconv]` | convert files before diffing (e.g. plist → xml) |
| `[warnings]` | silence specific warnings |

Diff/merge with VS Code:
```toml
[diff]
    command = "code"
    args = ["--wait", "--diff"]
[merge]
    command = "bash"
    args = ["-c", "cp {{ "{{ .Target }}" }} {{ "{{ .Target }}" }}.base && code --new-window --wait --merge {{ "{{ .Destination }}" }} {{ "{{ .Target }}" }} {{ "{{ .Target }}" }}.base {{ "{{ .Source }}" }}"]
```
(The `{{ "{{" }}` escaping is only needed inside `.chezmoi.toml.tmpl`; in a plain config write `{{ .Target }}`.)

Editor on Windows: `[edit] command = "code"` + `args = ["--wait"]` — without `--wait` chezmoi
returns immediately and sees no change.

## Hooks

Run a command before/after a chezmoi command or event. **Unlike scripts, hooks run even with
`--dry-run`**, so keep them fast and idempotent.

Events: any command name (`apply`, `add`, `update`, `init`…), `read-source-state`,
`git-auto-commit`, `git-auto-push`; each with `.pre` / `.post`.

```toml
[hooks.read-source-state.pre]
    command = ".local/share/chezmoi/.install-password-manager.sh"   # ensure bw/op exists before templates run
[hooks.apply.post]
    command = "echo"
    args = ["applied"]
[hooks.add.post]
    script = "post-add-hook.ps1"     # uses interpreter by extension
```

Env in hooks: `CHEZMOI=1`, `CHEZMOI_COMMAND`, `CHEZMOI_COMMAND_DIR`, `CHEZMOI_ARGS`.

## Interpreters

Choose how scripts/hooks run by extension (key without dot). Defaults on Windows:
`.ps1` → `pwsh -NoLogo -File` (falls back to Windows PowerShell), `.py` → `python3`, `.nu` → `nu`,
`.pl` → `perl`, `.rb` → `ruby`. `.bat/.cmd/.exe` run natively. `.tmpl` is stripped first.

```toml
[interpreters.ps1]
    command = "powershell"
    args = ["-NoLogo"]
[interpreters.py]
    command = 'C:\Python312\python.exe'
[interpreters.sh]
    command = 'C:\Program Files\Git\bin\bash.exe'   # run .sh scripts on Windows via Git Bash
```
