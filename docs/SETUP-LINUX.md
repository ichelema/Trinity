# Setup di Trinity su un server Linux

Guida gemella di `SETUP-NUOVO-PC.md` (che resta la procedura Windows/chiavetta).
Su Linux **niente chiavetta come runtime**: il repo arriva via git, il database
via `db-restore`, i runtime si installano nativi. La chiavetta serve al massimo
come corriere dei dump (montata in sola lettura) — mai come datadir Postgres.

> Contesto: architettura a due istanze decisa il 2026-07-15 (vedi
> `PIANO-portabilita-linux.md`). Il cluster pg0 di Windows NON e' apribile da un
> Postgres Linux (formato on-disk diverso): i dati viaggiano SOLO via
> `pg_dump`/`pg_restore` con i task `db-dump` / `db-restore`.

## 1. Prerequisiti

```bash
sudo apt-get install -y git curl jq lsof          # Debian/Ubuntu; adatta alla distro
sudo apt-get install -y ffmpeg                    # opzionale: yt-extract, suoni
```

## 2. Clone e bootstrap

```bash
git clone git@github.com:sphynx79/Trinity.git ~/ai/trinity
cd ~/ai/trinity
bash scripts/setup/bootstrap-linux.sh
```

Il bootstrap e' **idempotente** (rieseguibile). Fa: mise + runtime del repo,
`hindsight-api` via pip, `mcp-remote` via npm, symlink
`~/.claude/skills/trinity -> ~/ai/trinity`, `TRINITY_PLUGIN_DIR` in
`~/.claude/settings.json`, `core.hooksPath .githooks`, registrazione MCP
`hindsight` a scope user, `~/backups/hindsight`.

## 3. Chiavi API (mai nel repo)

In `~/.profile` (o un env file caricato da mise):

```bash
export OPENAI_API_KEY="sk-..."        # retain/recall/reflect (gpt-4.1-nano/mini)
export ZEROENTROPY_API_KEY="ze-..."   # OBBLIGATORIA: embedding (zembed-1) + rerank
export TICKTICK_API_KEY="..."         # MCP TickTick (opzionale; web TickTick: Settings > Account > API Token)
```

`ZEROENTROPY_API_KEY` NON e' opzionale: `mise.toml` imposta
`HINDSIGHT_API_EMBEDDINGS_PROVIDER = "zeroentropy"`, quindi senza chiave il server
muore all'avvio (`ValueError: ...ZEROENTROPY_API_KEY is required when
HINDSIGHT_API_EMBEDDINGS_PROVIDER is 'zeroentropy'`). Non aggirarla cambiando
provider: il DB ha colonne `vector(1280)` (zembed-1) e gli altri hanno dimensioni
diverse (gemini 1536, bge-m3 1024), quindi i vettori nuovi non entrerebbero. Per il
solo rerank la chiave sarebbe invece opzionale (fallback a interleaving), ma il
provider e' lo stesso.

Il server MCP `ticktick` e' remoto (`https://mcp.ticktick.com/`): niente da installare,
si autentica col Bearer token letto da questa variabile. E' l'unico MCP che funziona
identico su Linux senza adattamenti.

## 4. Claude Code

Installa il CLI `claude` nativo Linux (nessun alias/USERPROFILE da manipolare,
a differenza di Windows). Al primo avvio in un progetto qualsiasi il plugin
Trinity viene scoperto dal symlink skills-dir; l'hook SessionStart avvia da
solo il server Hindsight.

> **Poi rilancia il bootstrap** (è idempotente): `bash scripts/setup/bootstrap-linux.sh`.
> Al primo giro `claude` non c'era ancora, quindi la registrazione del server MCP
> `hindsight` (scope user) è stata saltata con un avviso; ora che il CLI è installato
> viene fatta. Senza questo passo i tool `mcp__hindsight__*` non compaiono in sessione.

## Language server per la navigazione codice (opzionale)

Il plugin abilita 4 language server (`.lsp.json`): TypeScript, Python (pyright),
Ruby (ruby-lsp), Lua. Servono solo alla navigazione semantica del codice (il tool
`LSP`); Trinity funziona senza. Il bootstrap **non** li installa: li rileva e, se
mancano, stampa il comando. Su Arch sono tutti nel repo `extra`:

```bash
sudo pacman -S --needed lua-language-server pyright typescript-language-server ruby-lsp
```

`run-lsp.sh` cerca ogni server tra gli shim di mise, `~/.local/bin/<nome>/bin/` e
il PATH: i binari messi in `/usr/bin` da pacman vengono trovati senza altra
configurazione. Su distro non-Arch, installa gli equivalenti col package manager locale.

## 5. Primo avvio del server e import della memoria

```bash
mise -C ~/ai/trinity run start-hindsight   # pg0 scarica i binari Postgres Linux
                                           # e crea un cluster NUOVO in ~/.pg0 (ext4)
curl -fsS -m 3 http://127.0.0.1:8888/ -o /dev/null -w "%{http_code}\n"  # 404 = up
```

Poi importa il dump piu' recente fatto su Windows:

```bash
# via scp dal PC di casa:
scp pc-casa:/e/var/backups/hindsight/hindsight-*.dump* ~/backups/hindsight/
printf '%s\n' "$(ls ~/backups/hindsight/hindsight-*.dump | sort | tail -1 | xargs basename)" > ~/backups/hindsight/LATEST
# oppure montando la chiavetta NTFS (sola lettura basta):
#   sudo mount -o ro /dev/sdX1 /mnt/usb && cp /mnt/usb/var/backups/hindsight/* ~/backups/hindsight/

mise -C ~/ai/trinity run db-restore
mise -C ~/ai/trinity run start-hindsight   # il restore ferma il server MCP
```

## 6. Flusso quotidiano (uso alternato, mai concorrente)

| Momento | Comando |
|---|---|
| lasci una macchina (Windows o Linux) | `mise run db-dump` |
| arrivi sull'altra | copia il dump se serve, poi `mise run db-restore` |

Il restore **rifiuta** se il DB locale ha scritture piu' recenti del dump
(guardrail sul watermark) — in quel caso fai prima `db-dump` locale o decidi
consapevolmente con `--force`. Un dump di sicurezza `pre-restore-*` viene
comunque creato.

## 7. Timer schedulati

Solo i job che hanno senso sul server: vedi `scheduler/systemd/README.md`
(promote-scan, api-check, cp-check). I job nb-check / yt-check /
nb-auth-refresh restano su Windows (dipendono da installazioni exe-free e dai
cookie del browser).

## 8. Verifica end-to-end

```bash
cd ~/ai/trinity
bash hooks/hindsight/tools/hindsight-check.sh        # suite completa (attesi OK, KO recall se disabilitato)
python hooks/hindsight/lib/hindsight_config.py --banks   # risoluzione bank (python3 se serve)
echo '{"prompt":"test recall di prova sul server"}' | HS_CFG_RECALL_ENABLED=true bash hooks/hindsight/hindsight-recall.sh | head -c 200
bash hooks/play-sound.sh Windows_Proximity_Notification.wav; echo "exit=$? (0 anche headless)"
```

In una sessione Claude Code: i tool `mcp__hindsight__*` devono comparire e
`recall` rispondere con le memorie importate.

## 9. Vincoli di versione (i due lati devono restare in coppia)

- **Postgres**: stessa major 18.x su entrambi i lati (il dump `-Fc` attraversa
  le minor senza problemi; una major diversa richiede attenzione).
- **hindsight-api**: aggiorna su ENTRAMBI i lati quando l'alert `api-check`
  segnala una nuova versione (lo schema del DB e' legato alla versione).

## 10. Cosa NON fare

- Non montare mai il datadir Postgres della chiavetta su Linux (formato
  Windows, e Postgres su NTFS/ntfs-3g e' inaffidabile per fsync/permessi).
- Non usare le due istanze in contemporanea: il sync e' una fotografia, non un
  merge — l'uso e' alternato per decisione di progetto.
- Non copiare i runtime dalla chiavetta (`E:\msys64`, mise Windows): sono
  binari PE; su Linux si reinstalla tutto nativo (fa gia' tutto il bootstrap).
