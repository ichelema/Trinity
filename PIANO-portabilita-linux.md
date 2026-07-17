# Piano — Trinity multipiattaforma (Windows + server Linux)

> Stato al 2026-07-15: **fasi 0, 1, 2, 4 ESEGUITE e verificate su Windows**
> (commit da `74925de` a `2349941`); **fasi 3 e 5**: deliverable scritti e
> committati (`b04e0b5`, `f422b39`), esecuzione e collaudo DA FARE sul server
> (bootstrap → chiavi API → start → db-restore → timer). Al primo riavvio di
> Claude Code su Windows verificare: playwright MCP, LSP (nomi shim nel PATH),
> suoni via play-sound.sh. Basato sull'audit del 2026-07-15 (9 agent, 88
> finding + 3 gap); tempi DB misurati sul cluster reale.

## Decisioni prese (vincolanti per il piano)

| Tema | Decisione |
|---|---|
| Database | **Due istanze** (pg0 Windows esistente + istanza Linux nuova), sync via `pg_dump`/`pg_restore` |
| Raggiungibilità | Il server Linux **non** è raggiungibile dal PC di lavoro → niente DB di rete |
| Scope Linux | **Tutto Trinity**: Claude Code + hook + skill + comandi + scheduler |
| Concorrenza | **Nessuna sessione contemporanea**: uso sempre alternato |
| chezmoi | **NO** (vedi confronto sotto): bootstrap script idempotente nel repo |

Assunzione da confermare al primo accesso: distro con systemd e permessi root
(il piano usa systemd timer; con cron classico cambia solo la Fase 5).

Numeri misurati (2026-07-15): DB `hindsight` 322 MB → `pg_dump -Fc` **8 s / 77 MB**;
`pg_restore` **10 s**; export logico API (241 doc) 1 s / 620 KB. Bank attuali:
trinity-project 241 doc, Obsidian_Sinapsi 47, Remit_Mappa 9, PluginPilot 1.

---

## Architettura target

```
   PC lavoro (Win)          PC casa (Win)              Server Linux
   ┌─────────────┐          ┌─────────────┐          ┌──────────────────┐
   │ MSYS2 su E: │          │ MSYS2 su E: │          │ clone git Trinity│
   │ repo su E:  │◄─chiavetta─►│ repo su E:  │          │ ~/ai/trinity     │
   │ pg0 Windows │          │ pg0 Windows │  dump    │ pg0 Linux (nuovo)│
   │  (junction→E:)│        │  (junction→E:)│ ◄──────► │  cluster nativo  │
   └─────────────┘          └─────────────┘ chiavetta └──────────────────┘
                                            o scp (da casa)
```

- **Codice**: viaggia via **git** (repo privato `sphynx79/Trinity`). La chiavetta resta
  la fonte per le due macchine Windows; il server ha un **clone** normale.
- **Database**: ogni ambiente ha il suo cluster nativo. I dump `-Fc` (77 MB) viaggiano
  sulla chiavetta stessa (`E:/var/backups/hindsight/`) o via scp quando sei a casa.
  Il datadir NON si condivide mai tra OS (formato on-disk incompatibile — verificato).
- **Config per-macchina**: env in `~/.claude/settings.json` + un file env opzionale,
  creati dal bootstrap script. Nessun path assoluto nel codice versionato.

---

## Con chezmoi o senza? Confronto e verdetto

**Cosa risolverebbe chezmoi**: solo lo strato "config per-macchina" — `~/.claude/settings.json`,
symlink/junction skills-dir, export di env nel profilo shell, eventuali file certs. ~4-5 file.

**Cosa NON risolve chezmoi** (cioè il 90% del lavoro emerso dall'audit): i path
hardcoded *dentro il repo* (`.mcp.json`, `.lsp.json`, shim MCP, `mise.toml`), i comandi
Windows-only negli script (taskkill, pwsh, cygpath, ps -W), i bit eseguibili nell'indice
git, lo scheduler, il sync del DB. Tutto questo va sistemato nel repo comunque, con o
senza chezmoi.

| Criterio | Senza chezmoi (bootstrap nel repo) | Con chezmoi |
|---|---|---|
| Dipendenze nuove | 0 | chezmoi su 3 macchine + repo dotfiles separato |
| Fonti di verità | 1 (repo Trinity) | 2 (Trinity + chezmoi source state) — rischio drift |
| Copertura del problema | totale (script vede OS a runtime) | solo strato per-macchina |
| Debug su macchina nuova | `bash bootstrap.sh` e leggi l'output | capire chezmoi apply + template |
| Coerenza col progetto | già così (SETUP-NUOVO-PC.md è procedurale) | paradigma nuovo |

**Verdetto: senza chezmoi.** Con sole 3 macchine e ~5 file per-macchina, chezmoi
aggiunge un sistema da imparare e mantenere per gestire meno file di quanti ne tocchi
il bootstrap. La soluzione più robusta è rendere il repo *OS-aware* (gli script rilevano
l'OS a runtime) + un `scripts/setup/bootstrap.sh` idempotente che crea lo strato
per-macchina. Chezmoi torna sul tavolo solo se in futuro vorrai gestire con template
tutti i tuoi dotfile (zsh, WezTerm, nvim…) su tutte le macchine: in quel caso si integra
DOPO, senza conflitti con questo piano.

---

## Fase 0 — Igiene del repo (sicura, utile anche solo su Windows)

Nessun cambio di comportamento su Windows; sblocca il checkout Linux.

| # | Task | Verifica |
|---|---|---|
| 0.1 | `git update-index --chmod=+x` sugli 8 script `100644`: `hooks/hindsight/hindsight-failcheck.sh`, `hooks/hindsight/mcp/hindsight-mcp-shim.sh`, `.githooks/post-commit`, `.githooks/post-merge`, i 4 `*-scheduled.sh` (nb-check, yt-check, auth-refresh, promote-scan) | `git ls-files -s <file>` → tutti `100755` |
| 0.2 | Fallback `mise` senza `.exe` (funziona identico su MSYS2): `hindsight-ensure-up.sh:24`, `hs-python.sh:15,33`, `skill-eval.sh:36`, i 6 `*-scheduled.sh` | grep `mise.exe` → 0 occorrenze negli script (ok nei .cmd) |
| 0.3 | `python` nudo → `$HS_PY` (source `lib/hs-python.sh`): `hindsight-mcp-shim.sh:31` (**critico**: oggi su Linux degraderebbe in silenzio al bank core), `ops/hindsight-reflect.sh:13`, `ops/hindsight-set-mission.sh:23`, `ops/hindsight-mental-models.sh:18` | `bash -n` + smoke test recall/reflect su Windows |
| 0.4 | `localhost` → `127.0.0.1` dove compare nei client HTTP interni (evita la penalità IPv6 di Windows: 0,21 s vs 0,003 s a richiesta, misurata) | export API < 5 s |

## Fase 1 — Piano di controllo start/stop portabile

Pattern unico: `case "$(uname -s)" in MINGW*|MSYS*|CYGWIN*) …windows…;; *) …unix…;; esac`.
Il ramo Windows resta ESATTAMENTE quello attuale (modifiche chirurgiche, zero regressioni).

| # | File | Ramo Linux da aggiungere | Verifica |
|---|---|---|---|
| 1.1 | `hooks/hindsight/ops/hindsight-stop-services.sh` | `pkill -TERM -f hindsight-local-mcp`; pg_ctl da `$HOME/.pg0/installation/*/bin/pg_ctl` (senza .exe), `$HOME` al posto di `$HOMEDRIVE$HOMEPATH`+cygpath | su Win: stop-hindsight ok come oggi |
| 1.2 | `hooks/hindsight/ops/kill-port.sh` | `lsof -ti :$PORT \| xargs -r kill` (fallback `fuser -k`) prima del ramo pwsh | `mise run stop-dashboard` ok su Win |
| 1.3 | `hooks/hindsight/hindsight-shutdown.sh` | sostituire `ps -W` con `pgrep -fc` nel ramo unix (**critico**: oggi su Linux spegnerebbe il server con sessioni attive) | conteggio sessioni corretto su Win |
| 1.4 | `hooks/hindsight/mcp/hindsight-mcp-shim.sh` | `NODE=$(command -v node \|\| mise which node)`, proxy.js risolto dal prefix di node, `PLUGIN_DIR` da `BASH_SOURCE` (niente fallback `E:/`) | tool MCP hindsight ok su Win dopo il cambio |
| 1.5 | `hooks/hooks.json` + nuovo `hooks/play-sound.sh` | wrapper: cygpath solo se esiste; player in ordine ffplay→paplay→aplay→exit 0 (server headless = no-op) | suono fine turno ok su Win |
| 1.6 | `hooks/windows-toast.sh` | ramo `notify-send` se disponibile, altrimenti exit 0 | toast ok su Win |
| 1.7 | `hooks/hindsight/tools/hindsight-check.sh` | `ss -ltnp`/`lsof` al posto di netstat.exe; wrapper `w()` per cygpath condizionale | check completo verde su Win |

## Fase 2 — Config senza path assoluti

| # | File | Modifica | Verifica |
|---|---|---|---|
| 2.1 | `.mcp.json` | sostituire i path assoluti `node.exe`/`python.exe`/`E:/AI/tools` con wrapper nel repo (`scripts/bin/run-node.sh`, `run-python.sh`: risolvono l'interprete a runtime via `command -v`/mise) e path `${TRINITY_PLUGIN_DIR}`; i tool esterni (notebooklm) via env per-macchina (`NOTEBOOKLM_PY`, `NOTEBOOKLM_ROOT`) | server MCP tutti up su Windows dopo il cambio |
| 2.2 | `.lsp.json` | stessi wrapper (o shim mise nel PATH, senza `.exe` e senza versione pinnata) | LSP attivi su Win |
| 2.3 | `core-behavior.md` + `hooks/inject-core-behavior.sh` | sezione «Ambiente» divisa in blocco Windows e blocco Linux; lo script inietta solo il blocco dell'OS corrente (via uname), il resto resta condiviso | testo iniettato corretto su Win |
| 2.4 | `hindsight.config.json` | mission retain/reflect e query mental-model neutre rispetto all'OS: «annota sempre su quale host/OS è stato osservato il fatto» al posto di «Windows 11 + MSYS2» (**protegge il DB condiviso** dall'inquinamento di fatti sbagliati) | reflect di prova coerente |
| 2.5 | `mise.toml` | `_.path` e `_.file` con `{{env.HOME}}` e/o voci per-OS (le voci inesistenti sono innocue, già verificato); porta 8888/5432 invariate | `mise run start-hindsight` ok su Win |
| 2.6 | Scheduler `.rb` | `E:/AI/tools/...` → env con default attuale (`NB_INST_DIR`, `YT_CLONE_DIR`); alert: `notepad.exe`/cygpath solo su Windows, su Linux scrive il file e logga | job manuali ok su Win |
| 2.7 | Skill e comandi (dettaglio sotto) | vedi 2.7a-2.7d | lettura skill coerente su entrambi gli OS |

### 2.7 — Dettaglio skill e comandi

Principio: lo stesso `SKILL.md` serve entrambi gli OS (viaggia col repo), quindi mai
riscritture Linux-only ma **sezioni condizionali per OS** (il modello che la legge sa su
che OS gira dal core-behavior iniettato) o **path via env**, sul modello già usato da
`skills/yt-extract` (matrice per-OS).

Stato dall'audit: 7 skill già neutre (mise, nushell, ruby, lsp-enable, book-to-skill,
excel-data-analyst, yt-extract), 2 col ramo Linux già documentato (obsidian,
obsidian-cli headless). I 6 comandi usano già `${CLAUDE_PLUGIN_ROOT}`/`$TRINITY_PLUGIN_DIR`
(verificato: il path assoluto visto nell'espansione di /trinity:reflect è l'espansione
runtime della variabile, non testo del file).

| # | File | Intervento |
|---|---|---|
| 2.7a | `skills/notebooklm/SKILL.md` | **il più grave**: le istruzioni operative impongono `/e/AI/tools/notebooklm-data/notebooklm ...` — sostituire con launcher via env (`$NOTEBOOKLM_BIN`) e tabella per-OS (su Linux: install pip normale, niente exe-free) |
| 2.7b | `skills/hindsight/SKILL.md` | separare i gotcha MSYS2/taskkill/path `E:\` in una sottosezione «Windows/MSYS2» e aggiungere l'equivalente Linux (stop via pkill nel task mise per-OS, storage `~/.pg0` su ext4) |
| 2.7c | `skills/excalidraw-skill/SKILL.md` | nota rebuild: `node.exe` pinnato → `npx tsc` come via standard, la nota npx-MSYS2-rotto marcata Windows-only |
| 2.7d | Comandi: `hindsight-create-agent.md` (doc stale: server hindsight ora a scope user, non in .mcp.json), `promote.md` (`python` → nota esecuzione via mise), `ccr_model.md` (richiede `TRINITY_PLUGIN_DIR` esportata — la crea il bootstrap Fase 3), `release.md` (nota SSH marcata MSYS2-only) |

## Fase 3 — Setup del server Linux

Deliverable: `scripts/setup/bootstrap-linux.sh` (idempotente, rieseguibile) + `docs/SETUP-LINUX.md`.

1. Prerequisiti sistema: git, curl, jq, lsof, ffmpeg (opz.), build tools.
2. mise nativo (`curl https://mise.run | sh`), poi dal clone: `mise install` (python/node/ruby — i runtime della chiavetta sono PE Windows, NON riutilizzabili).
3. Clone del repo in `~/ai/trinity` (o path a scelta) + `git config core.hooksPath .githooks`.
4. `pip install hindsight-api` nel Python di mise + `mise reshim` (niente vincolo EDR su Linux: installazione normale, zero exe-free).
5. Symlink skills-dir: `ln -sfn ~/ai/trinity ~/.claude/skills/trinity` (equivalente POSIX della junction).
6. `~/.claude/settings.json` con env: `TRINITY_PLUGIN_DIR`, `OBSIDIAN_VAULT*` (se il vault esiste lì, altrimenti omesse). Chiavi API (`OPENAI_API_KEY`, `ZEROENTROPY_API_KEY`, `TICKTICK_API_KEY`) in `~/.profile` o file env caricato da mise.
   - **Server MCP con strumento esterno** (`.mcp.json` usa `${VAR}` puro, senza più fallback hardcoded dopo il refactoring del 2026-07-16): le variabili vanno definite qui con i **percorsi dell'installazione Linux** di quegli strumenti, non i path Windows `E:/...`. Servono `NOTEBOOKLM_DATA` e `NOTEBOOKLM_LIB` (root dei dati e libreria di notebooklm, install pip normale su Linux) e — se si abilita excalidraw — `MCP_EXCALIDRAW_DIR`. Se una di queste manca, quel solo server non parte (warning in avvio, resto invariato): definirle solo per gli strumenti che si installa davvero sul server.
   - **CLI adhd** (aggiunta 2026-07-17, stesso pattern): il wrapper versionato `scripts/bin/adhd` risolve Node via `run-node.sh` e legge la root dell'installazione da `ADHD_LIB`. Su Linux: `npm install adhd-agent` in una cartella locale (niente exe-free) e `ADHD_LIB` puntata lì; se la variabile manca il wrapper esce con errore esplicito e resta fuori uso solo `/trinity:adhd-cli` (la skill `skills/adhd/` è puro Markdown e funziona ovunque senza setup).
7. Registrazione MCP hindsight a scope user: `claude mcp add-json hindsight … hindsight-mcp-shim.sh` (stesso shim, ora portabile dalla Fase 1).
8. Primo avvio: `mise run start-hindsight` → pg0 scarica i binari Postgres **Linux** e crea un cluster nuovo in `~/.pg0/` (su filesystem nativo ext4: niente junction, niente NTFS).
9. Primo import dati: `mise run db-restore` (Fase 4) dal dump più recente.

Verifica end-to-end: checklist in `docs/SETUP-LINUX.md` — server risponde su :8888, `hindsight_config.py --banks` risolve i bank, recall hook inietta contesto, tool MCP visibili, retain di prova completa, suoni/toast degradano a no-op senza errori.

## Fase 4 — Sync del database (il cuore del multi-macchina)

Due nuovi script in `hooks/hindsight/tools/` + task mise `db-dump` / `db-restore`:

- **`hs-db-dump.sh`**: `pg_dump -Fc` del DB `hindsight` → tre file in `BACKUP_DIR`:
  - `hindsight-<UTC>.dump` — il dump vero e proprio (~77-80 MB, 8 s);
  - `hindsight-<UTC>.dump.meta.json` — `{host, dumped_at, max_write_at, database}`;
    il watermark è letto PRIMA del dump ed è quello che il restore confronta col DB locale;
  - `LATEST` — contiene il nome dell'ultimo dump: è il file che il restore legge per
    sapere quale ripristinare.

  Rotazione: tiene le ultime `HS_BACKUP_KEEP` coppie dump+meta (default 5, ~385 MB).
- **`hs-db-restore.sh`**: **guardrail anti-perdita** prima di toccare qualsiasi cosa:
  confronta l'ultima scrittura locale (watermark su `created_at` E `updated_at`) con
  `max_write_at` registrato nel dump. Se il DB locale ha scritture PIÙ RECENTI del
  dump → **rifiuta** con messaggio chiaro (`--force` per forzare consapevolmente).
  Poi: dump di sicurezza locale, `pg_restore --no-owner` su un DB temporaneo e swap
  dei nomi (l'originale non è droppato finché il nuovo non è validato). Il DB
  `litellm` resta fuori dal sync (è per-macchina: chiavi virtuali e spend log locali).
- Workflow d'uso (documentato, ~20 secondi in tutto):
  - lasci una macchina → `mise run db-dump` (la chiavetta ha il dump)
  - arrivi sull'altra → `mise run db-restore` (rifiuta se stai per perdere dati)
  - dal server Linux, in alternativa alla chiavetta montata: `scp` da/verso il PC di casa.
- Uso alternato = zero conflitti; il guardrail copre la dimenticanza (se scrivi su
  entrambi i lati senza sync, te ne accorgi al restore, non dopo).

### Dove viene salvato il dump (e come arriva all'altra macchina)

`BACKUP_DIR` è risolto per-OS in `hooks/hindsight/tools/hs-db-lib.sh`, senza path
hardcoded altrove:

| Ambiente | `BACKUP_DIR` di default | Riga |
|---|---|---|
| Windows (MSYS2) | `E:/var/backups/hindsight` — **sulla chiavetta stessa**, che fa da corriere tra le macchine | `hs-db-lib.sh:17` |
| Linux | `$HOME/backups/hindsight` — disco nativo del server | `hs-db-lib.sh:23` |

Su entrambi si sovrascrive con `HS_BACKUP_DIR` (es. per dumpare su un disco esterno
diverso dalla chiavetta). La cartella viene creata dal dump se non esiste.

**Trasporto Windows → Linux**: la chiavetta è già il supporto fisico del dump, quindi
il passaggio è "stacca e riattacca". Sul server, se la chiavetta NTFS non è montata,
si copia il dump via `scp` dal PC di casa (`scp E:/var/backups/hindsight/hindsight-*.dump
server:~/backups/hindsight/` — serve anche il `.meta.json`, altrimenti il guardrail
non ha il watermark da confrontare). La chiavetta serve solo in LETTURA: il datadir
Postgres non si condivide mai tra OS.

**Stato al 2026-07-15**: la cartella su Windows contiene già un dump reale,
`hindsight-20260715T030357Z.dump` (80 MB) + meta + `LATEST` — prodotto dal collaudo
della Fase 4. È il candidato per il primo `db-restore` sul server (punto 9 della Fase 3).

Verifica: ciclo completo Windows→dump→restore su Linux→retain di prova→dump→restore su Windows, con conteggio documenti identico alle estremità (oggi: 298 totali).

## Fase 5 — Scheduler su Linux

Solo i job che hanno senso sul server (systemd user timer, template in `scheduler/systemd/`):

| Job | Su Linux? | Note |
|---|---|---|
| promote-scan | ✅ settimanale | parla solo con Hindsight locale — il candidato ideale |
| api-check / cp-check | ✅ settimanale | baseline già relative a mise/repo |
| nb-check / yt-check / nb-auth-refresh | ❌ restano su Windows | legati a install exe-free su `E:/AI/tools` e ai cookie del browser |

I `.cmd` e System Scheduler restano invariati per Windows. Gli `*-scheduled.sh` (già
bash) vengono invocati direttamente dai timer con `TRINITY_PLUGIN_DIR` nell'unit.

## Cose da fare successivamente (miglioramenti al sync, non bloccanti)

0. **`.lsp.json`** — RISOLTO (portabile via `scripts/bin/run-lsp.sh`). Da
   confermare al primo riavvio: che Claude Code spawni il wrapper `.sh` come
   command LSP (per i server MCP lo fa gia'). Se non lo facesse, il fallback
   e' tornare ai path assoluti degli shim **con `.exe`** e generare il file
   per-OS dal bootstrap.

Oggi `db-dump`/`db-restore` sono manuali (scelta deliberata: il restore è
distruttivo). Automazione proposta, da fare dopo il collaudo sul server:

1. **Dump automatico in uscita** — nel worker di `hindsight-shutdown.sh`
   (scatta solo alla chiusura dell'ULTIMA sessione Claude), chiamare
   `hs-db-dump.sh` tra il retain finale e `hindsight-stop-services.sh`.
   Sicuro (sola lettura, ~8 s, rotazione a 5 copie): chiudi e basta, il dump
   fresco finisce sulla chiavetta da solo.
2. **Restore assistito in ingresso** — a SessionStart (in `ensure-up` o hook
   dedicato) confrontare il watermark del dump in `BACKUP_DIR` (`.meta.json`)
   con `hs_db_watermark()` locale: se la chiavetta è più avanti, iniettare un
   avviso in sessione ("dump più recente del DB locale: lancia
   `mise run db-restore`"). Il restore RESTA manuale: mai drop automatico
   all'avvio. Il guardrail rimane come ultima difesa.

## Fuori scope (esplicitamente)

- **LiteLLM / CCR / Headroom su Linux**: tool esterni per-macchina; si installano lì
  solo se vorrai usare quei provider dal server (fase successiva separata).
- **Obsidian sul server**: la skill obsidian-cli documenta già il ramo headless
  (xvfb + .deb); si attiva solo se serve il vault sul server.
- Sync bidirezionale/merge del DB: non necessario con uso alternato (deciso).

## Rischi e mitigazioni

| Rischio | Mitigazione |
|---|---|
| Restore sovrascrive scritture non ancora dumpate | guardrail `max_write_at` in `hs-db-restore.sh` (rifiuta, serve `--force`) |
| Drift di versione Postgres/hindsight-api tra i due lati | pin: pg0 18.x entrambi; `api-check` gira su entrambi; nota in SETUP-LINUX.md di aggiornare in coppia |
| Regressioni su Windows durante il porting | ogni task di Fase 1-2 ha verifica su Windows PRIMA del commit; ramo Windows testuale invariato |
| pg0 su Linux si comporta diversamente dal previsto | punto 8 della Fase 3 è la prima cosa da provare sul server: se pg0 non supporta Linux si passa al Postgres di sistema + pgvector (piano B, stesso restore) |
| Chiavetta NTFS montata male su Linux | serve solo in LETTURA per i dump (mai datadir); in alternativa scp |

## Ordine di esecuzione consigliato

1. **Fase 0** subito (commit singolo, zero rischio).
2. **Fasi 1-2** su Windows, un commit per gruppo, verificando che tutto continui a funzionare qui (il criterio di successo è: nessuna differenza di comportamento su Windows).
3. **Fase 4** (script di sync) sviluppata e provata su Windows (dump+restore locale già misurati).
4. **Fase 3** sul server (primo contatto reale con Linux: bootstrap + primo restore).
5. **Fase 5** timer + una settimana di rodaggio con la checklist.
