# Setup di Trinity su un server Linux

Versione Linux della procedura di setup; su Windows il setup segue invece la
modalità portatile a chiavetta USB (guida tenuta solo in locale, non versionata).
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
git clone git@github.com:ichelema/Trinity.git ~/ai/trinity
cd ~/ai/trinity
bash scripts/setup/bootstrap-linux.sh
```

Il bootstrap e' **idempotente** (rieseguibile). Fa: mise + runtime del repo,
`hindsight-api` via pip, `mcp-remote` via npm, i symlink skills-dir
(`~/.claude/skills/trinity -> ~/ai/trinity` **piu' uno per ogni plugin
vendorizzato** in `vendor/`: `ui-craft`, `mattpocock-skills` — funzione
`link_skill`, README §8), la generazione di `~/.claude/settings.json` da
`config/claude/` (shared + overlay `settings.linux.json`, con
`TRINITY_PLUGIN_DIR` calcolata dal path del repo — stesso script del task
`mise run sync-settings`), `core.hooksPath .githooks`, registrazione MCP
`hindsight` a scope user, `~/backups/hindsight`.

## 3. Chiavi API (mai nel repo)

In `~/.profile` (o un env file caricato da mise):

```bash
export OPENAI_API_KEY="sk-..."        # retain/recall/reflect + consolidation (gpt-4.1-mini)
export GEMINI_API_KEY="..."           # OBBLIGATORIA: embedding (gemini-embedding-001, 1536 dim, dal 2026-07-27)
export VOYAGE_API_KEY="..."           # reranker voyage/rerank-2.5 (senza: fallback senza rerank, qualita' recall peggiore)
export TICKTICK_API_KEY="..."         # MCP TickTick (opzionale; web TickTick: Settings > Account > API Token)
```

`GEMINI_API_KEY` NON e' opzionale: `mise.toml` imposta
`HINDSIGHT_API_EMBEDDINGS_PROVIDER = "google"` (gemini-embedding-001, dal
2026-07-27) e il DB ha vettori a 1536 dimensioni. Non aggirarla cambiando
provider: dimensioni diverse (zembed-1 1280/2560, bge-m3 1024) richiederebbero
un rebuild del bank. Usare un progetto Google con **billing attivo** (sul free
tier i contenuti inviati possono essere usati per addestrare i modelli).
Il task `start-hindsight` fa fail-fast su `OPENAI_API_KEY` e `GEMINI_API_KEY`.

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

## Server MCP del plugin su Linux

`.mcp.json` e' versionato e definisce anche server pensati per il PC Windows.
Su un host Linux appena bootstrappato lo stato e' questo:

| Server | Stato su Linux | Per usarlo |
|---|---|---|
| `hindsight` | registrato dal bootstrap (§2 + rilancio in §4) | niente da fare |
| `ticktick` | funziona identico (server remoto) | solo `TICKTICK_API_KEY` (§3) |
| `notebooklm` | non parte, con un warning innocuo: `NOTEBOOKLM_DATA`/`NOTEBOOKLM_LIB` non sono definite | installa notebooklm-py su questo host e definisci le 2 variabili in `config/claude/settings.linux.json` → `env` coi path dell'installazione **Linux**, poi `mise run sync-settings` (vedi README §10) |
| `playwright` | parte ma muore subito: il bootstrap non installa `@playwright/mcp` | `mise -C ~/ai/trinity x -- npm install -g @playwright/mcp` **piu'** un browser: il `--browser chrome` in `.mcp.json` presuppone Google Chrome installato; su un server headless conviene disabilitarlo |
| `obsidian_semantic_notes_vault` | in errore a ogni sessione: punta a `http://localhost:3002/mcp`, servito dal plugin MCP dentro Obsidian | ha senso solo dove gira Obsidian con quel plugin; su un server disabilitalo |
| `ui-craft` (dal plugin vendorizzato, non da questo `.mcp.json`) | dichiarato nel `.mcp.json` di `vendor/ui-craft`: `npx -y ui-craft-mcp` | serve un `node`/`npx` raggiungibile nel PATH (quello di mise del bootstrap basta); se non vuoi il server, disabilitalo come gli altri |

Per spegnere i server che non vuoi su questo host usa il layer per-macchina
(`~/.claude/settings.json`), NON `.mcp.json` (versionato, condiviso tra gli OS):

```json
{ "disabledMcpjsonServers": ["playwright", "notebooklm", "obsidian_semantic_notes_vault"] }
```

Chiavi come questa sopravvivono al sync del bootstrap: il merge di
`sync-claude-settings.py` preserva le chiavi presenti solo nel file locale e
sovrascrive soltanto quelle definite in `config/claude/` (README §10).

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

### 6.1 Due inciampi del Postgres embedded su Linux

Entrambi incontrati il 2026-08-14 su CachyOS (Arch), durante il restore
descritto in `MIGRAZIONE-EMBEDDING-LINUX.md`.

**`CREATE DATABASE` rifiutato per collation version.** Quando la glibc di
sistema viene aggiornata (qui 2.43 -> 2.44) il cluster resta indietro e
Postgres 18 blocca la creazione di nuovi database dal template:

```
ERROR: template database "template1" has a collation version mismatch
```

Il restore muore subito dopo il dump di sicurezza, senza toccare il DB
reale. Si allinea una volta sola, e i database creati dopo nascono gia'
corretti (quello ripristinato compreso):

```bash
PSQL=$(echo "$HOME"/.pg0/installation/*/bin/psql)
for db in template1 postgres; do
  "$PSQL" "postgresql://hindsight:hindsight@127.0.0.1:5432/postgres" \
    -c "ALTER DATABASE $db REFRESH COLLATION VERSION;"
done
```

Il `REFRESH` dichiara solo che le collation sono allineate: su un DB con
indici testuali andrebbe seguito da un `REINDEX`, ma qui i due database
sono vuoti e quello di lavoro viene ricreato dal dump.

**`psql`/`pg_ctl` a mano non partono.** I binari portabili di pg0 cercano
le proprie librerie (libicu 70 & c.), che il loader di sistema non
conosce — su Arch c'e' la 78:

```
error while loading shared libraries: libicuuc.so.70
```

Serve indicarle esplicitamente; gli script del repo lo fanno gia' da se',
il problema si presenta solo nei comandi lanciati a mano:

```bash
export LD_LIBRARY_PATH="$HOME/.pg0/installation/18.1.0/lib:${LD_LIBRARY_PATH:-}"
```

E per avviare il cluster fuori dal server MCP (es. per un'ispezione)
serve anche `-k /tmp`: la socket dir di default `/run/postgresql` la crea
solo il servizio systemd di sistema, che qui non e' in uso.

```bash
pg_ctl -D "$HOME/.pg0/instances/hindsight-mcp/data" -o "-k /tmp" \
  -l /tmp/pg-manuale.log start
```

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
bash hooks/bin/play-sound.sh Windows_Proximity_Notification.wav; echo "exit=$? (0 anche headless)"
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
