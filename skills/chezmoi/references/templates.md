# Templates

Source: <https://www.chezmoi.io/reference/templates/> (variables, functions, directives, init functions).

A file is a template when it ends in `.tmpl` (or `chezmoi add -T` / `chattr +template`).
Syntax is Go `text/template` + **all sprig functions** + chezmoi functions.
`.chezmoiignore`, `.chezmoiremove`, `.chezmoiexternal.*` are **always** templates.

## Data available as `.`

Merged, later wins: `.chezmoi.*` built-ins → `.chezmoidata.*` / `.chezmoidata/` files → `[data]` in config.
Inspect with `chezmoi data` (add `--format yaml` for readability).

## `.chezmoi.*` variables

| Variable | Value |
|----------|-------|
| `.chezmoi.os` | `linux`, `darwin`, `windows`, `freebsd`… (GOOS) |
| `.chezmoi.arch` | `amd64`, `arm64`, `arm`… (GOARCH) |
| `.chezmoi.hostname` | hostname up to first `.` |
| `.chezmoi.fqdnHostname` | full hostname |
| `.chezmoi.username`, `.uid`, `.gid`, `.group` | current user |
| `.chezmoi.homeDir` | home, forward slashes (also on Windows) |
| `.chezmoi.rawHomeDir` | home, native separators (`C:\Users\me`) |
| `.chezmoi.sourceDir` / `.workingTree` | source dir / git working tree |
| `.chezmoi.destDir`, `.cacheDir` | destination / cache dir |
| `.chezmoi.configFile`, `.config` | config path / parsed config object |
| `.chezmoi.sourceFile` | this template, relative to source dir |
| `.chezmoi.targetFile` | absolute target path of this template |
| `.chezmoi.osRelease` | `/etc/os-release` (Linux): `.id`, `.versionID`, `.idLike`… |
| `.chezmoi.kernel` | `/proc/sys/kernel` info (Linux) — detect WSL via `.osrelease` |
| `.chezmoi.windowsVersion` | Windows: `.currentBuild`, `.productName`, `.displayVersion`… |
| `.chezmoi.pathSeparator`, `.pathListSeparator` | `\` / `;` on Windows, `/` / `:` elsewhere |
| `.chezmoi.executable`, `.args`, `.flags` | chezmoi binary, argv, selected flags |
| `.chezmoi.version.version` | chezmoi version (+ `.commit`, `.date`, `.builtBy`) |
| `.chezmoi.stdin` | only in `modify_` templates: current file content |

WSL detection:
```
{{ if and (eq .chezmoi.os "linux") (.chezmoi.kernel.osrelease | lower | contains "microsoft") }}
```

## Control flow & whitespace

```
{{- if eq .chezmoi.os "darwin" }}
…
{{- else if and (eq .chezmoi.os "linux") (eq .chezmoi.osRelease.id "ubuntu") }}
…
{{- end }}

{{ range .packages.common }}{{ . }} {{ end }}
{{ $dir := joinPath .chezmoi.homeDir ".config" }}
{{ with .work }}{{ .proxy }}{{ end }}        {{/* skips if .work missing/empty */}}
{{ if hasKey . "gpgKey" }}…{{ end }}
{{ .optional | default "fallback" }}
```

`{{-` trims whitespace before, `-}}` after. Comments: `{{/* … */}}`.
Missing keys error by default (`missingkey=error`); guard with `hasKey`, `with`, `default`, or `dig`.

## chezmoi functions (beyond sprig)

**Files & paths**
- `include "path"` — raw content of a file in the source dir (relative to source root). Not rendered.
- `includeTemplate "name" [data]` — render a template from `.chezmoitemplates/` (or source path).
- `joinPath a b …`, `glob "pattern"`, `globCaseInsensitive`, `stat path`, `lstat path` (nil if missing)
- `lookPath "exe"`, `findExecutable "exe" (list dirs)`, `findOneExecutable`, `isExecutable path`

**Commands**
- `output "cmd" "arg" …` — stdout of a command (cached per run; fails template on error)
- `outputList "cmd" (list …)`, `exec "cmd" "arg"` → bool (exit code success)
- `ioreg` (macOS), `mozillaInstallHash path`

**Data formats**
- `fromJson`, `fromJsonc`, `fromToml`, `fromYaml`, `fromIni`
- `toJson` (sprig), `toPrettyJson`, `toToml`, `toYaml`, `toIni`, `toString`, `toStrings`
- `jq ".query" data`, `setValueAtPath "a.b" value dict`, `deleteValueAtPath`, `pruneEmptyDicts`

**Strings**
- `quote` (sprig), `shellQuote`, `shellQuoteList`, `quoteList`, `comment "# " text`
- `ensureLinePrefix`, `replaceAllRegex re repl s`, `eqFold a b`, `hexEncode`/`hexDecode`

**Control / debug**
- `abortEmpty` — skip the target entirely; `warnf "fmt" …`; `debugf`
- `encrypt` / `decrypt` (configured method), `completion "zsh"`, `getRedirectedURL`

**GitHub** (cached `gitHub.refreshPeriod`, token from `CHEZMOI_GITHUB_ACCESS_TOKEN`, `GITHUB_TOKEN`…):
`gitHubKeys "user"`, `gitHubLatestRelease "owner/repo"`, `gitHubLatestReleaseAssetURL "owner/repo" "pattern"`,
`gitHubRelease`, `gitHubReleaseAssetURL`, `gitHubReleases`, `gitHubLatestTag`, `gitHubTags`.

```
{{ range gitHubKeys "myuser" }}{{ .Key }}
{{ end }}
```

Password manager functions → see secrets.md.

## Reusable fragments: `.chezmoitemplates/`

Every file there is a named template (name = path relative to the dir). Pass the context explicitly:

```
# .chezmoitemplates/aliases.sh
alias ll='ls -la'
{{ if eq .chezmoi.os "darwin" }}alias o=open{{ end }}

# dot_zshrc.tmpl
{{ template "aliases.sh" . }}
# or, to pipe/assign:
{{ includeTemplate "aliases.sh" . | trim }}
```

Without `.` the fragment runs with nil data and `.chezmoi.os` fails.

## Init functions (only in `.chezmoi.<fmt>.tmpl`)

| Function | Signature |
|----------|-----------|
| `promptString` / `promptStringOnce` | `promptStringOnce . "path" "Prompt" ["default"]` |
| `promptBool` / `promptBoolOnce` | `promptBoolOnce . "isWork" "Work machine"` |
| `promptInt` / `promptIntOnce` | `promptIntOnce . "fontSize" "Font size" 12` |
| `promptChoice` / `promptChoiceOnce` | `promptChoiceOnce . "role" "Role" (list "home" "work")` |
| `promptMultichoice` / `…Once` | `promptMultichoiceOnce . "langs" "Langs" (list "go" "py")` |
| `stdinIsATTY` (usable anywhere) | false in CI / non-interactive — guard prompts with it |
| `writeToStdout "text"`, `exit code` | message / abort init |

`*Once` returns the existing value at `path` in the current config `data` and only prompts if missing,
so re-running `chezmoi init` doesn't re-ask. Non-interactive: `chezmoi init --promptString "Email address=a@b.c"
--promptBool "Is this a work machine=true"` (key = the **prompt text**, not the data path) or `--promptDefaults`. Test with `chezmoi execute-template --init`.

## Directives

Put on any line (the line is removed):

```
chezmoi:template:left-delimiter="[[" right-delimiter="]]"   # for files full of {{ }} (e.g. Helm, Jinja)
chezmoi:template:missing-key=zero                            # error (default) | invalid | zero
chezmoi:template:line-endings=crlf                           # crlf | lf | native
chezmoi:template:encoding=utf-16-le                          # utf-8, utf-8-bom, utf-16-{le,be}[-bom]
chezmoi:template:format-indent-width=4                       # or format-indent="\t" (toJson/toYaml/toToml)
```

Usually wrapped in a comment: `{{/* chezmoi:template:line-endings=crlf */}}`.

Escaping a literal `{{`: `{{ "{{" }}` or a backtick string `` {{ `{{ .NotChezmoi }}` }} ``.

## Debugging

```bash
chezmoi execute-template '{{ .chezmoi.os }}/{{ .chezmoi.arch }}'
chezmoi execute-template < "$(chezmoi source-path ~/.zshrc)"
chezmoi execute-template --init < .chezmoi.toml.tmpl     # with init functions
chezmoi cat ~/.zshrc                                     # rendered target
chezmoi data --format yaml
chezmoi execute-template --override-data '{"isWork":true}' < file.tmpl
```
