# Replica del plugin Trinity su un nuovo PC (Windows 11 + MSYS2 UCRT64)

Guida passo-passo per ottenere su un **altro** sistema la stessa identica configurazione del
plugin Trinity per Claude Code. Tutti i comandi e i path sono estratti dai file reali del repo
(`mise.toml`, `README.md`, `.mcp.json`, `hooks/`, `scheduler/`). Dove un passo **non** è
documentato/automatizzato nel repo è marcato esplicitamente con `[DA VERIFICARE]`.

> Convenzione path: `<USER>` = il tuo username Windows (in MSYS2 è `$USERNAME`). Sostituiscilo
> ovunque. Esempio: `C:/msys64/home/<USER>/.local/bin/mise.exe`.
> Path repo usato qui come esempio: `D:/AI/Claude/Trinity` — puoi clonarlo dove vuoi, ma poi
> devi riflettere quel path in `TRINITY_PLUGIN_DIR` e nei job dello scheduler.

---

## 0. Panoramica architetturale (cosa stai replicando)

Il plugin è il *cervello* (file versionati nel repo). Server, DB e runtime sono il *corpo*
installato sulla macchina e **non** sono nel repo:

| Componente | Dove vive | Come si installa |
|---|---|---|
| File del plugin (hook, skill, comandi, `core-behavior.md`, `.mcp.json`) | il repo clonato | `git clone` + junction skills-dir |
| Runtime Python/Node/Ruby | gestiti da `mise` | `mise install` (legge `mise.toml`) |
| Server Hindsight (`localhost:8888`) + Postgres embedded | `~/.pg0`, processo Python | `mise run install-hindsight` + `mise run start-hindsight` |
| CA bundle aziendale | `C:/certs/cacert.pem` | manuale (vedi §1) |
| Chiavi API + path machine-specific | env utente Windows / `~/.claude/settings.json` | manuale (vedi §3 e §9) |

---

## 1. Prerequisiti

1. **MSYS2** installato in `C:\msys64` con l'ambiente **UCRT64** (`MSYSTEM=UCRT64`).
   Pacchetti utili già presenti di default ma da verificare: `git`, `curl`, `gettext`
   (fornisce `envsubst`, usato dall'iniezione di `core-behavior.md` — fallback su `sed` se
   manca).

2. **mise** (binario nativo Windows), atteso in:
   ```
   C:/msys64/home/<USER>/.local/bin/mise.exe
   ```
   NON è nel PATH della shell MSYS2: invocalo sempre col path assoluto, oppure aggiungi
   `~/.local/bin` al PATH nel tuo `~/.zshrc`/`~/.bashrc`.
   `[DA VERIFICARE]` Il repo non documenta **come** installare mise stesso (winget/scoop/exe).
   Conferma il metodo di installazione di `mise.exe` sul nuovo PC.

3. **CA bundle aziendale** (solo se sei dietro il proxy MITM ENINET; necessario per far passare
   le chiamate TLS a PyPI / npm / ZeroEntropy):
   ```
   C:/certs/cacert.pem
   ```
   È il bundle CA di `curl` (Mozilla + CA root aziendale). Le env `SSL_CERT_FILE`,
   `REQUESTS_CA_BUNDLE`, `NODE_EXTRA_CA_CERTS` nel `mise.toml` puntano qui.
   `[DA VERIFICARE]` Il repo dà per scontato questo file ma non spiega come ottenerlo/generarlo.
   Su una rete senza proxy MITM probabilmente non serve; conferma se il nuovo PC è dietro lo
   stesso proxy e, in caso, procurati/copia `cacert.pem` in `C:/certs/`.

4. **Claude Code CLI** (`claude.exe`) installato e funzionante.

---

## 2. Clone del repo

Clona dove preferisci; l'esempio usa `D:/AI/Claude/Trinity`:

```bash
git clone <URL-del-tuo-remote> /d/AI/Claude/Trinity
cd /d/AI/Claude/Trinity
```

`[DA VERIFICARE]` Il repo non contiene l'URL del remote `origin`. Recuperalo dal repo esistente
con `git remote -v` (sul vecchio PC) e usalo qui.

Attiva gli hook git versionati (post-commit/post-merge — vanno riattivati per ogni clone nuovo):

```bash
C:/msys64/home/<USER>/.local/bin/mise.exe -C /d/AI/Claude/Trinity trust
C:/msys64/home/<USER>/.local/bin/mise.exe -C /d/AI/Claude/Trinity run install-git-hooks
```

(`install-git-hooks` esegue `git config core.hooksPath .githooks`.)

---

## 3. Attivazione come plugin (skills-dir junction) + env var utente

> **IMPORTANTE — il modello è cambiato.** Dal 2026-06-19 Trinity **non** è più caricato come
> marketplace: è una **skills-dir** agganciata via *junction* di directory. Si modifica il repo
> e si riavvia Claude Code — niente `plugin update`, niente bump di versione, niente cache.
>
> ⚠️ Il `README.md` del repo descrive ancora il **vecchio** modello marketplace
> (`claude plugin marketplace add` / `claude plugin install` / `claude plugin update`,
> `enabledPlugins`). **Quelle istruzioni sono datate**: NON seguirle per la replica. Anche i
> file `.claude-plugin/marketplace.json` e `.claude-plugin/plugin.json` sopravvivono nel repo ma
> non governano più il caricamento.

### 3a. Crea la junction skills-dir

La junction collega `~/.claude/skills/trinity` alla root del repo. Sul sistema attuale è
esattamente:

```
~/.claude/skills/trinity  ->  /d/AI/Claude/Trinity
```

Crea la cartella `skills` se non c'è, poi la junction. La junction di **directory** su Windows
si crea con `mklink /J` (richiede `cmd`, non serve admin):

```bash
mkdir -p ~/.claude/skills
# via cmd (mklink è un built-in di cmd.exe):
cmd //c 'mklink /J "C:\Users\<USER>\.claude\skills\trinity" "D:\AI\Claude\Trinity"'
```

> Adatta i due path: il **target** è la home `.claude` di Windows
> (`C:\Users\<USER>\.claude\...`), la **sorgente** è la root del repo.
> ⚠️ Per rimuovere la junction in futuro usa **`rmdir`** (`cmd //c 'rmdir "...\trinity"'`),
> **MAI** `rm -rf` (seguirebbe la junction e cancellerebbe il contenuto del repo).

Verifica:

```bash
ls -la ~/.claude/skills/    # deve mostrare: trinity -> /d/AI/Claude/Trinity
```

`[DA VERIFICARE]` Il repo non contiene uno script che crei la junction; il comando `mklink /J`
sopra è ricavato dalla struttura osservata sul sistema attuale (junction reale verificata), non
da un file del repo. Conferma che il nuovo Claude Code carichi effettivamente skill/hook/comandi
da quella junction dopo il restart.

### 3b. Definisci le env var machine-specific in `~/.claude/settings.json`

I valori che cambiano da macchina a macchina vengono da variabili d'ambiente, **non** sono
hardcodati nel plugin. Definiscile una volta in `~/.claude/settings.json` (file utente, non
versionato col plugin):

```json
{
  "env": {
    "OBSIDIAN_VAULT": "D:/Obsidian/Sinapsi",
    "OBSIDIAN_VAULT_NAME": "Sinapsi",
    "TRINITY_PLUGIN_DIR": "D:/AI/Claude/Trinity"
  }
}
```

- `TRINITY_PLUGIN_DIR` → root del repo (la usano comandi/skill e, come override, alcuni script
  e il `.mcp.json`).
- `OBSIDIAN_VAULT` / `OBSIDIAN_VAULT_NAME` → vault Obsidian; espansi dentro `core-behavior.md`
  all'iniezione di SessionStart. Su un PC senza Obsidian puoi ometterli (il testo iniettato
  mostrerà un avviso esplicito al posto del valore).

> La versione MSYS del path (`/d/...`) si ricava con `cygpath -u`, non serve una variabile
> separata.

### 3c. (Se usi il proxy aziendale) `TRINITY_PLUGIN_DIR` nell'env **utente di Windows**

Il contesto noto indica che `TRINITY_PLUGIN_DIR` va impostata anche nell'**env utente di
Windows** (non solo nella shell), perché gli script dello scheduler e i job Splinterware girano
fuori dalla shell MSYS. Impostala (PowerShell, persistente a livello utente):

```powershell
[Environment]::SetEnvironmentVariable("TRINITY_PLUGIN_DIR", "D:/AI/Claude/Trinity", "User")
```

> Gli script dello scheduler hanno comunque un **fallback relativo** alla root del repo
> (`scheduler/*/ -> ../..`), quindi `TRINITY_PLUGIN_DIR` è un override, non strettamente
> obbligatorio per loro. Resta consigliata per i comandi delle skill.

---

## 4. Installazione runtime (`mise install`)

Il `mise.toml` del repo dichiara i runtime nella sezione `[tools]`:

```toml
[tools]
python = "3.13"
node = "lts"
ruby = "4.0.1"
```

Installa tutto leggendo il `mise.toml` (eseguilo **dalla root del repo**):

```bash
cd /d/AI/Claude/Trinity
C:/msys64/home/<USER>/.local/bin/mise.exe trust        # mise rifiuta un mise.toml non "trusted"
C:/msys64/home/<USER>/.local/bin/mise.exe install      # installa python 3.13, node lts, ruby 4.0.1
```

> `mise trust` è idempotente e va ri-eseguito dopo ogni modifica del `mise.toml` (che invalida
> il trust).

### Workaround noti

- **Node per le build (CCR, `tsc`, Control Plane):** usa **sempre** il Node gestito da mise, MAI
  il Node MSYS2 UCRT64 (`/ucrt64/bin/node`), che crasha (`bad_weak_ptr`/segfault) su `npx` e
  `tsc`. Il `mise.toml` lo dichiara apposta (`node = "lts"`) e l'`[env]._path` espone la Scripts
  dir del Python di mise.

- **Gemme native Ruby con GCC 16 (per `mise run install-dashboard`):**
  `[DA VERIFICARE]` Il contesto noto indica che su mise/Windows con GCC 16 le gemme native
  richiedono una patch a `CONFIG["CFLAGS"]` in `rbconfig.rb` (l'env / `--with-cflags` NON
  funziona), e che `nokogiri` va installata a parte con `--use-system-libraries`. **Nel repo
  NON esiste alcuno script o README che automatizzi questa patch** (solo una menzione testuale
  in `skills/hindsight/SKILL.md` riga 312, come "learning"). Inoltre il `Gemfile` della
  dashboard (`hooks/hindsight/hindsight-dashboard/Gemfile`) contiene solo `roda` e `puma`, che
  sono **pure-Ruby** e probabilmente non innescano il problema. → Verifica al volo: lancia
  `mise run install-dashboard`; se una gemma nativa fallisce in compilazione, applica
  manualmente la patch a `rbconfig.rb` del Ruby di mise (4.0.1) come da nota
  `learning_mise_ruby_gcc16_native_gems`. La procedura esatta non è codificata nel repo.

---

## 5. Installazione Hindsight (server + chiavi API)

Hindsight è il sistema di memoria persistente: server MCP locale su `localhost:8888`, storage
Postgres **embedded** in `~/.pg0`.

### 5a. Installa il pacchetto Python

Il task `install-hindsight` del `mise.toml` fa:

```toml
[tasks.install-hindsight]
run = "python -m pip install --upgrade hindsight-api"
```

Eseguilo:

```bash
cd /d/AI/Claude/Trinity
C:/msys64/home/<USER>/.local/bin/mise.exe run install-hindsight
```

> **Cosa installa davvero:** sul sistema attuale risultano installati nel Python di mise sia
> `hindsight_api-0.8.3` sia `hindsight_api_slim-0.8.3`, entrambi forniscono il modulo
> `hindsight_api` e gli entry-point `hindsight-local-mcp.exe`, `hindsight-api.exe`,
> `hindsight-admin.exe`, `hindsight-worker.exe`. Quindi `pip install --upgrade hindsight-api`
> è il comando corretto e allinea alla **v0.8.3**.
> Nota: `pip show hindsight-api` può rispondere "not found" pur essendo i `.dist-info`
> presenti — è un quirk dei metadati pip su questo setup, non un'assenza reale (gli `.exe`
> esistono e il server gira). Il check ufficiale di versione lo fa `mise run api-check`.

### 5b. Chiavi API necessarie (env utente Windows)

Le chiavi sono risolte a runtime dall'env utente (NON sono nel `mise.toml`):

| Env var | Obbligatoria? | A cosa serve |
|---|---|---|
| `OPENAI_API_KEY` | **Sì** | LLM di produzione `gpt-4.1-mini` per retain/recall/reflect **e** consolidation (e triage promozione su `gpt-4.1-nano`). Senza, i task abortiscono. |
| `ZEROENTROPY_API_KEY` | **Sì** | Embedding `zembed-1` + reranker `zerank-2` (ZeroEntropy). Senza, recall/retain non funzionano. |
| `GEMINI_API_KEY` | No (opzionale) | Fallback embedding Gemini `gemini-embedding-001`, **non** attivo in produzione (provider = zeroentropy). Ha default `''` nel `mise.toml`: la sua assenza non blocca il boot. |

Impostale a livello utente (esempio PowerShell):

```powershell
[Environment]::SetEnvironmentVariable("OPENAI_API_KEY",      "sk-...",  "User")
[Environment]::SetEnvironmentVariable("ZEROENTROPY_API_KEY", "ze-...",  "User")
# opzionale:
# [Environment]::SetEnvironmentVariable("GEMINI_API_KEY",    "AI...",   "User")
```

> Nota: il `mise.toml` imposta `HINDSIGHT_API_SKIP_LLM_VERIFICATION=true` — una `OPENAI_API_KEY`
> errata NON emerge al boot ma al primo retain.

### 5c. Avvia il server e fai il seeding

```bash
cd /d/AI/Claude/Trinity
MISE=C:/msys64/home/<USER>/.local/bin/mise.exe

"$MISE" run start-hindsight          # avvia hindsight-local-mcp su :8888 (log in /tmp/hs.log)
# attendi ~20s che il server (e il Postgres embedded) salgano

# seed delle 3 "knowledge page" / mental model (richiesto dalla suite di verifica):
bash hooks/hindsight/ops/hindsight-mental-models.sh seed

# imposta retain_mission + reflect_mission sul bank:
bash hooks/hindsight/ops/hindsight-set-mission.sh
```

> Normalmente il server viene avviato **automaticamente** dall'hook `SessionStart` quando apri
> Claude Code (via `hooks/hindsight/hindsight-ensure-up.sh`), quindi lo `start-hindsight`
> manuale serve solo per il setup/verifica iniziale. Stop con `mise run stop-hindsight`.

> Il bank **core** è `trinity-project` e si **auto-crea al primo retain** — nessun provisioning
> manuale del DB. I bank di progetto si auto-creano allo stesso modo.

---

## 6. Patch / integrazioni custom (solo quelle documentate nel repo)

- **MCP registrati** (`.mcp.json`): `hindsight` (HTTP, `http://127.0.0.1:8888/mcp/trinity-project/`)
  è l'unico **attivo**. `excalidraw` e `obsidian_semantic_notes_vault` sono `"disabled": true`;
  `playwright` è attivo ma punta a un path Node di mise versionato
  (`.../installs/node/24.16.0/...`) — **`[DA VERIFICARE]`**: quel numero di versione Node è
  cablato nel `.mcp.json` e potrebbe non corrispondere alla LTS installata da `mise install` sul
  nuovo PC; aggiorna il path o installa quella versione se ti serve Playwright.

- **Excalidraw canvas (opzionale):** i task `start-excalidraw`/`stop-excalidraw` e il server MCP
  presumono `C:/msys64/home/<USER>/.local/opt/mcp_excalidraw/dist/...`.
  `[DA VERIFICARE]` Il repo **non** contiene quel build né istruzioni per produrlo: andrebbe
  installato/buildato a parte (fuori dal repo). Salta se non usi il canvas.

- **zembed / ttyd / CCR / LiteLLM:** **non** sono parte del setup del plugin nel repo (zembed è
  già il provider di default via `mise.toml`, senza patch da applicare qui). Le integrazioni
  ttyd/CCR/LiteLLM citate nel contesto noto sono ambienti separati e **fuori scope** per la
  replica del solo plugin. Non c'è nulla da fare nel repo per esse.

---

## 7. Job dello scheduler da registrare a mano (System Scheduler / Splinterware)

Tre job opzionali (check aggiornamenti + scan promozione) vanno registrati **manualmente** nella
GUI di **System Scheduler (Splinterware)**. Per ciascuno, tab _Event_:

- **Event Type:** `Run Application`
- **Parameters:** _(vuoto)_
- **Working Dir:** `D:\AI\Claude\Trinity`  *(adatta al tuo path repo)*
- **State:** `Minimized` (o `Hidden`)
- **Schedule:** settimanale (consigliato)

| Job | Application (campo "Application") | Cosa fa |
|---|---|---|
| Hindsight API — check nuova versione | `D:\AI\Claude\Trinity\scheduler\check_update_hindsight_api\api-check-scheduled.cmd` | Avvisa se su PyPI esce una versione più recente di `hindsight-api`/`hindsight-api-slim` |
| Control Plane — check nuova versione | `D:\AI\Claude\Trinity\scheduler\check_update_hindsight_control_plane\cp-check-scheduled.cmd` | Avvisa se esce una versione del Control Plane > pin nel `mise.toml` |
| promote_scan — triage settimanale | `D:\AI\Claude\Trinity\scheduler\promote_scan\promote-scan-scheduled.cmd` | Scan + triage LLM dei candidati alla promozione (NON promuove) |

> I `.cmd` sono i "ponti" Windows→MSYS (impostano `MSYSTEM=UCRT64` ed entrano in login shell);
> i job trovano la root del repo via `TRINITY_PLUGIN_DIR` con fallback relativo. Dopo aver
> creato ogni evento, premi **▶ (Run)** in System Scheduler e controlla che compaia una riga
> fresca nel log corrispondente in `logs/` (`api-check-scheduled.log`, ecc.).

> `[DA VERIFICARE]` I path delle "Application" sopra sono presi **alla lettera** dai README in
> `scheduler/*` e contengono `D:\AI\Claude\Trinity`. Se cloni il repo altrove, sostituisci il
> path. Il repo non automatizza la registrazione dei job: è un'operazione GUI manuale.

Test manuale (senza scheduler), dalla root del repo:

```bash
MISE=C:/msys64/home/<USER>/.local/bin/mise.exe
"$MISE" run api-check     # exit 10 = c'è una versione nuova
"$MISE" run cp-check      # exit 10 = c'è una versione nuova del Control Plane
PROMOTE_NO_OPEN=1 bash scheduler/promote_scan/promote-scan-scheduled.sh; echo "rc=$?"
```

---

## 8. Verifica finale

Avvia il server (se non già su) e lancia la suite di diagnostica completa. Deve passare
**tutti** i check:

```bash
cd /d/AI/Claude/Trinity
bash hooks/hindsight/tools/hindsight-check.sh
```

Atteso a fine output: `✓ Tutto OK`, con il riepilogo `N/N check passati`.

> La suite copre server :8888, endpoint REST, recall/retain end-to-end, hook registrati in
> `hooks/hooks.json`, le 3 knowledge page, throttling, multi-bank e tooling di promozione. Se un
> check `KO` cita un comando di fix (es. `hindsight-set-mission.sh`, `hindsight-mental-models.sh
> seed`), eseguilo e ri-lancia.
> Nota: il numero esatto di check dipende dalla configurazione attiva (alcuni sono `SKIP`, es.
> l'e2e del retain quando `retain_enabled:false`). Il criterio di successo è `0 KO`, non un
> conteggio fisso. Sul sistema attuale la suite numera fino alla sezione **§19** (≈48 check).

---

## 9. Tabella riassuntiva env var richieste

| Env var | Dove si imposta | A cosa serve | Esempio / placeholder |
|---|---|---|---|
| `TRINITY_PLUGIN_DIR` | env utente Windows + `~/.claude/settings.json` | root del repo, per comandi skill / script / `.mcp.json` | `D:/AI/Claude/Trinity` |
| `OBSIDIAN_VAULT` | `~/.claude/settings.json` (env) | path vault Obsidian (espanso in `core-behavior.md`) | `D:/Obsidian/Sinapsi` |
| `OBSIDIAN_VAULT_NAME` | `~/.claude/settings.json` (env) | nome del vault Obsidian | `Sinapsi` |
| `OPENAI_API_KEY` | env utente Windows | LLM `gpt-4.1-mini` (retain/recall/reflect/consolidation) + `gpt-4.1-nano` (triage promozione) | `sk-...` |
| `ZEROENTROPY_API_KEY` | env utente Windows | embedding `zembed-1` + reranker `zerank-2` | `ze-...` |
| `GEMINI_API_KEY` | env utente Windows (opzionale) | fallback embedding Gemini (non attivo di default) | `AI...` |

**Già nell'`[env]` del `mise.toml`** (non devi impostarle, ma il file `C:/certs/cacert.pem` deve
esistere — vedi §1):

| Env var (in `mise.toml`) | Valore | A cosa serve |
|---|---|---|
| `SSL_CERT_FILE` / `REQUESTS_CA_BUNDLE` | `C:/certs/cacert.pem` | verifica TLS Python via CA bundle aziendale (proxy MITM) |
| `NODE_EXTRA_CA_CERTS` | `C:/certs/cacert.pem` | equivalente per Node/npm (Control Plane) |
| `PYTHONUTF8` | `1` | forza UTF-8 (Windows non-EN, evita `UnicodeEncodeError`) |
| `_.path` | `.../python/3.13.13/Scripts` | espone gli entry-point di hindsight-api nel PATH |

---

## Appendice — Riferimenti rapidi ai task `mise` (dalla root del repo)

| Task | Azione |
|---|---|
| `mise install` | installa python 3.13 / node lts / ruby 4.0.1 |
| `mise run install-hindsight` | `pip install --upgrade hindsight-api` |
| `mise run start-hindsight` / `stop-hindsight` | avvia/ferma il server :8888 |
| `mise run install-dashboard` | `bundle install` della dashboard log (Ruby mise) |
| `mise run dashboard` / `stop-dashboard` | dashboard log Roda/Puma :9292 |
| `mise run control-plane` / `stop-control-plane` | Web UI Hindsight :9999 (Node mise, pin `0.8.3`) |
| `mise run install-git-hooks` | attiva `.githooks/` |
| `mise run api-check` / `cp-check` | check aggiornamenti (exit 10 = novità) |
| `mise run promote-scan` | triage candidati promozione |

> Tutti i task vanno lanciati dalla root del repo (o con `mise -C "$TRINITY_PLUGIN_DIR" run …`),
> e richiedono `mise trust` la prima volta e dopo ogni modifica del `mise.toml`.
