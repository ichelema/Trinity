---
name: nushell
description: One-liner Nushell (`nu -c "..."`) per leggere, filtrare, aggregare e convertire dati strutturati (JSON, CSV, YAML, TOML, tabelle di file). Usala quando serve output tabulare o un filtro su dati strutturati al posto di pipe testuali (awk, jq, cut). Non per scrivere script — quelli sono JavaScript `.mjs` con Bun — né per orchestrare processi.
---

# Nushell — one-liner su dati strutturati

Nushell qui è uno strumento da **una riga**: `nu -c "..."` quando i dati sono
strutturati. Gli script si scrivono in JavaScript (`.mjs`, Bun), non in Nu.

## Environment (this setup)

- Serve: Arch `pacman -S --noconfirm nushell`. Windows: native `nu.exe` from the Nushell GitHub
  releases, copied into `/ucrt64/bin` (no MSYS2 package), plus the wrapper `$HOME/.local/bin/nu`
  that sets `XDG_CONFIG_HOME` and runs it.
- Binary: `$HOME/.local/bin/nu` — always use the full path.
- On Windows it is a **native Windows binary**, not MSYS2: pass Windows paths (`C:/...`), never MSYS paths (`/c/...`, `/e/...`).
  - Correct: `nu -c "open 'C:/path/to/data.json'"`
  - Wrong: `nu -c "open '/c/path/to/data.json'"`
- On Linux, if `nu` is not in `~/.local/bin`, use the one in PATH; paths are plain POSIX.
- Do not pipe MSYS2 process output into `nu` (stdin issues) — read files with `open` and Windows paths instead.

## Quick one-liner use cases

- List files with filters: `nu -c "ls | where size > 1mb | sort-by size"` instead of `ls -la | awk ...`
- Read and filter JSON/CSV/YAML: `nu -c "open data.json | where status == 'active' | select name email"` instead of `cat data.json | jq ...`
- Aggregations/reports: `nu -c "ls | group-by type | transpose type files | insert count { |r| $r.files | length }"`
- Format conversion: `nu -c "open data.csv | to json"`

## Pitfalls

- External commands: inside `nu`, `ls -la` is parsed as Nu's own `ls`. Prefix with `^` to call the external program (`^ls -la`).
- Quoting: wrap the whole pipeline in double quotes for bash and use single quotes inside for Nu strings, so bash does not expand `$r`, `$env`, `$in`.

## When NOT to use Nushell

Stay on bash for process orchestration, simple text pipes, system scripting, and commands without structured data (`git`, `pacman`, `curl` without parsing). For anything longer than a one-liner, write a `.mjs` script and run it with Bun.
