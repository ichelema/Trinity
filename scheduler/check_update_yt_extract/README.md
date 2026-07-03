# Reminder aggiornamenti — yt-extract plugin

Sistema che **avvisa quando esce su GitHub una versione del plugin `yt-extract` più recente di quella installata in `E:/AI/tools/claude-code-youtube-extract`**, così si può fare l'upgrade quando si vuole.

## Contesto

Il plugin `yt-extract` è un clone git di `muckybuzzwoo/claude-code-youtube-extract` installato in `E:/AI/tools/claude-code-youtube-extract`. La versione installata è letta dal `CHANGELOG.md` del clone locale (prima riga `## [X.Y.Z]`).

> **Nota (incorporato in Trinity):** da luglio 2026 yt-extract è **incorporato dentro il plugin Trinity** (skill in `skills/yt-extract/`, subagent in `agents/extract-worker.md`, backend in `scripts/yt-extract.py`, namespace `trinity:`). Il clone qui monitorato resta lo **staging upstream** dove fare `git pull` + patch exe-free; dopo l'update va **risincronizzata** la copia dentro Trinity (vedi passo 3 sotto). Lo scheduler continua a leggere la versione dal `CHANGELOG.md` del clone.

Il clone contiene una **patch locale a `scripts/yt-extract.py`** (funzione `run_ytdlp()`) che lo rende exe-free: invoca `python -m yt_dlp` con `PYTHONPATH=E:/AI/tools/yt-dlp` invece del comando esterno `yt-dlp`. Questa patch va **riapplicata dopo ogni `git pull`**, poiché il pull sovrascrive il codice di terzi.

## File in questa cartella

| File                          | Ruolo                                                                                                         |
| ----------------------------- | ------------------------------------------------------------------------------------------------------------- |
| `yt-check.rb`                 | **Il check vero.** Legge versione dal CHANGELOG locale, interroga GitHub API, decide se c'è un update. Exit `0` / `10` / `1`. |
| `yt-check-scheduled.cmd`      | **Il ponte Windows→MSYS.** Lanciato da System Scheduler; imposta l'ambiente MSYS2.                           |
| `yt-check-scheduled.sh`       | **Il wrapper schedulato.** Esegue il check, scrive il log, crea/apre l'alert se c'è novità.                  |
| `README.md`                   | Questo file.                                                                                                  |

## Catena di esecuzione

```
System Scheduler (Splinterware)        ← innesco a orario programmato
        │
        ▼
yt-check-scheduled.cmd                  ← ponte: env MSYS2 + bash --noprofile --norc
        │
        ▼
yt-check-scheduled.sh                   ← cd root, log, gestione alert
        │  mise run yt-check
        ▼
mise run yt-check (.mise.toml)          ← fornisce Ruby + env TLS (SSL_CERT_FILE)
        │  ruby yt-check.rb
        ▼
yt-check.rb                             ← CHANGELOG parse, GitHub API, exit 0/10
```

## Configurazione in System Scheduler

**Tab _Event_:**

| Campo       | Valore                                                                                  |
| ----------- | --------------------------------------------------------------------------------------- |
| Event Type  | `Run Application`                                                                       |
| Title       | `yt-extract — check nuova versione`                                                     |
| Application | `E:\AI\Claude\Trinity\scheduler\check_update_yt_extract\yt-check-scheduled.cmd`        |
| Parameters  | _(vuoto)_                                                                               |
| Working Dir | `E:\AI\Claude\Trinity`                                                                  |
| State       | `Minimized` (o `Hidden`)                                                                |

**Tab _Schedule_:** cadenza **settimanale** consigliata.

## Uso manuale

```bash
mise run yt-check          # controlla (exit 10 = update disponibile)
```

> Lanciare via `mise run` per avere `SSL_CERT_FILE` corretto (proxy ENINET).

## Come aggiornare (quando arriva l'alert)

```bash
git -C /e/AI/tools/claude-code-youtube-extract pull
```

**Dopo il pull, riapplicare la patch exe-free a `run_ytdlp()`** in `scripts/yt-extract.py`:
la funzione deve invocare `python -m yt_dlp` con `PYTHONPATH=E:/AI/tools/yt-dlp` invece del comando esterno `yt-dlp`.

Vedi Hindsight (`recall "yt-extract patch exe-free"`) per il diff completo della patch.

**Passo 3 — risincronizzare la copia dentro Trinity** (necessario da quando yt-extract è incorporato):

```bash
SRC="E:/AI/tools/claude-code-youtube-extract"; DST="E:/AI/Claude/Trinity"
cp -r "$SRC/skills/yt-extract/." "$DST/skills/yt-extract/"
cp "$SRC/agents/extract-worker.md" "$DST/agents/extract-worker.md"
cp "$SRC/scripts/yt-extract.py"    "$DST/scripts/yt-extract.py"
```

Poi **ripatchare il namespace** in `$DST/skills/yt-extract/SKILL.md` (il pull riporta il valore
upstream): `subagent_type: "yt-extract:extract-worker"` → `"trinity:extract-worker"` (2 occorrenze,
righe ~259 e ~261). Infine **riavviare Claude Code** per ricaricare il plugin.

## Note tecniche

- **Versione locale**: letta dalla prima riga `## [X.Y.Z]` del `CHANGELOG.md` del clone. Stabile anche dopo la patch locale (che non tocca il CHANGELOG).
- **GitHub API**: usa `/releases/latest` con fallback a `/tags` se non esistono release formali. Rate limit: 60 req/h senza token (ampiamente sufficiente per un check settimanale).
- **TLS proxy ENINET**: `Net::HTTP` rispetta `SSL_CERT_FILE` impostato nell'`[env]` del `.mise.toml`.
- **`mise` non nel PATH MSYS**: invocato col path assoluto `/e/msys64/home/Sphynx/.local/bin/mise.exe`.
- **`YT_NO_OPEN=1`**: disabilita l'apertura di Notepad (utile per i test da terminale).
- **`YT_FORCE_ALERT=1`**: forza la scrittura dell'alert anche se non c'è update (per testare il flusso).
