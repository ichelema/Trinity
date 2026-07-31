# Trinity Plugin

Il **core dell'agente Trinity** come plugin Claude Code: memoria persistente Hindsight, comportamento 
condiviso, skill, comandi e hook di notifica. Installato a livello utente, è attivo in **ogni** 
progetto della macchina, che ne eredita comportamento e memoria.

> Repo unico: `E:\AI\Claude\Trinity` (dal 2026-06-12 include anche gli ex strumenti di laboratorio).

---

## 1. Architettura: repo unico

```
E:\AI\Claude\Trinity\   ← il core dell'agente: plugin distribuibile + strumenti di sviluppo
```

| Parte | Ruolo |
|---|---|
| **Runtime del plugin** | ciò che i progetti ereditano: hook, skill, comandi, `core-behavior.md`, `mise.toml` di servizio, `.mcp.json` |
| **Strumenti di sviluppo** | servono alla manutenzione di Trinity, non ai progetti: benchmark (`hooks/hindsight/benchmark/`), dashboard log (`hooks/hindsight/hindsight-dashboard/`), check aggiornamenti (`scheduler/`) |

La env var **`TRINITY_PLUGIN_DIR`** (definita nell'env utente, vedi §10) punta alla root di 
questo repo: la usano i comandi documentati nelle skill e, come override opzionale, gli script — 
che altrimenti risolvono i path relativamente a sé stessi.

### Cosa è plugin e cosa è ambiente

I **file** del plugin vivono tutti qui dentro. Le **risorse runtime** restano sulla macchina: il 
server Hindsight (`localhost:8888`), il Postgres embedded, i binari (`mise`, `node`, `ffplay`, `pwsh`), 
il CA bundle (`C:/certs/cacert.pem`), le chiavi API (env utente). 
Il plugin è il *cervello*; server, DB e runtime sono il *corpo* installato sul sistema.

---

## 2. Come viene caricato il plugin

Il plugin **non è legato a un progetto**: è abilitato a livello utente tramite **skills-dir** e si
carica in automatico ovunque apri Claude Code.

**Meccanismo (dal 2026-06-19):** junction NTFS che punta la directory skills di Claude Code al repo:

```
~/.claude/skills/trinity  →  E:\AI\Claude\Trinity
```

Claude Code scopre il plugin al SessionStart scansionando `~/.claude/skills/`. Non servono
`plugin install`, `plugin update`, bump di versione o `marketplace.json`: è sufficiente riavviare
Claude Code dopo ogni modifica al repo.

> **Requisito:** Claude Code riconosce un plugin da una cosa sola: la presenza di
> `.claude-plugin/plugin.json` nella root del repo. Senza questo file, la junction
> `~/.claude/skills/trinity` punta a una directory che Claude Code ignora
> silenziosamente — il plugin non si carica in nessun progetto.

Con lo stesso meccanismo si caricano anche i **plugin di terze parti vendorizzati** in
`vendor/` (§8): una junction per ciascuno, così ogni plugin mantiene il proprio namespace
(`ui-craft:*`, `claude-bionify:*`) separato da `trinity:*`.

**Ricreare le junction** (su un nuovo PC o dopo averle rimosse; su Linux le crea
`scripts/setup/bootstrap-linux.sh` come symlink, funzione `link_skill`):

```bash
MSYS_NO_PATHCONV=1 cmd /c mklink /J \
  "%USERPROFILE%\.claude\skills\trinity" \
  "E:\AI\Claude\Trinity"
MSYS_NO_PATHCONV=1 cmd /c mklink /J \
  "%USERPROFILE%\.claude\skills\ui-craft" \
  "E:\AI\Claude\Trinity\vendor\ui-craft"
MSYS_NO_PATHCONV=1 cmd /c mklink /J \
  "%USERPROFILE%\.claude\skills\claude-bionify" \
  "E:\AI\Claude\Trinity\vendor\claude-bionify"
```

---

## 3. Hook: come vengono caricati

Gli hook non stanno in `settings.json`: vivono nel file dedicato **`hooks/hooks.json`**, che 
Claude Code cerca per convenzione in `<plugin>/hooks/hooks.json`. 
Il formato è identico alla sezione `"hooks"` di `settings.json`; cambia solo la variabile 
di path: **`${CLAUDE_PLUGIN_ROOT}`** al posto di `${CLAUDE_PROJECT_DIR}`.

```
All'avvio Claude Code:
  legge "hooks" del progetto (settings.json)
  + legge hooks/hooks.json di ogni plugin abilitato
  → UNISCE le liste per evento (è una somma, non una sostituzione)
  → risolve ${CLAUDE_PLUGIN_ROOT} al path reale del plugin
```

Eventi registrati dal plugin:

| Evento | Matcher | Comandi |
|---|---|---|
| `SessionStart` | — | avvia server Hindsight · **inietta `core-behavior.md`** · inietta mental model |
| `UserPromptSubmit` | — | skill-eval · Hindsight **recall** · failcheck |
| `PreToolUse` | `Bash` | auto-allow `git commit` (solo se senza push nella stessa riga) |
| `PostToolUse` | `mcp__plugin_trinity_excalidraw__export_scene` | esporta canvas Excalidraw → vault Obsidian |
| `Stop` | — | suono di fine · Hindsight **retain** (async) |
| `SessionEnd` | — | shutdown servizi Hindsight |
| `Notification` | `permission_prompt` | suono + toast Windows |

Esempio — un hook del plugin (da `hooks/hooks.json`):

```json
{
  "type": "command",
  "command": "${CLAUDE_PLUGIN_ROOT}/hooks/hindsight/hindsight-recall.sh",
  "timeout": 20
}
```

Gli script `.sh`/`.py`/`.rb` referenziati stanno in `hooks/` e `hooks/hindsight/`; risolvono i propri 
fratelli relativamente alla loro posizione, quindi il plugin è rilocabile.

### Caricamento skill via skill-eval

A ogni prompt l'hook `UserPromptSubmit` esegue **`hooks/skill-eval.sh`**, che delega a un motore 
Node.js (`skill-eval.js`). Il motore analizza il testo del prompt e, se trova corrispondenze 
sufficienti, inietta nel contesto del modello un blocco `SKILL ACTIVATION REQUIRED` con le skill 
più rilevanti — così Claude sa quali skill caricare senza che l'utente debba invocarle a mano.

**Come funziona il punteggio**

Le regole stanno in `hooks/skill-rules.json`. Ogni skill ha una lista di trigger; ogni tipo di 
trigger vale un certo numero di punti:

| Tipo trigger | Punti | Esempio |
|---|---|---|
| `keywords` | 2 | la parola "hindsight" nel prompt |
| `keywordPatterns` | 3 | regex sul prompt (es. `"retain\|recall"`) |
| `intentPatterns` | 4 | pattern che esprimono un'azione (es. `"voglio ricordare"`) |
| `pathPatterns` | 4 | path con estensione riconosciuta menzionato nel prompt |
| `directoryMatch` | 5 | file in una cartella mappata (es. `data/` → skill `excel-data-analyst`) |
| `contentPatterns` | 3 | pattern nel corpo del prompt (case-sensitive) |
| `contextPatterns` | 2 | sottostringa di contesto generica |

Una skill viene proposta solo se raggiunge **almeno 3 punti** (`minConfidenceScore`). Vengono 
mostrate al massimo le **3 skill più rilevanti** (`maxSkillsToShow`), ordinate per score e poi 
per `priority`. Se una skill ha la sua cartella in `skills/` ma non contiene `SKILL.md` (es. 
rinominato in `SKILL.md.disabled`), viene ignorata anche se avrebbe raggiunto il punteggio.

**Output**

Se almeno una skill supera la soglia, `skill-eval.js` scrive su stdout un blocco come:

```
SKILL ACTIVATION REQUIRED

Matched skills (ranked by relevance):
1. hindsight (HIGH confidence)
   Matched: keyword "retain", intent detected
2. obsidian (LOW confidence)
   Matched: keyword "vault"
```

Questo testo arriva al modello come `additionalContext` dell'hook `UserPromptSubmit`, 
visibile nel contesto della sessione prima che il modello risponda.

---

## 4. Iniezione di `core-behavior.md`

`core-behavior.md` (root del plugin) contiene il **comportamento universale** dell'agente: principi, 
"prima la semplicità", modifiche chirurgiche, esecuzione guidata dagli obiettivi, ambiente di lavoro, 
regole operative shell/path, navigazione codice via LSP, Nushell, struttura directory dei progetti, linguaggi. 
Non è un file di sistema speciale: viene iniettato come **contesto** a ogni sessione da un hook 
`SessionStart`, e il suo stdout entra nel contesto del modello.

L'hook non fa un semplice `cat`: passa per lo script `hooks/inject-core-behavior.sh`, che **espande 
solo le variabili machine-specific** (`${OBSIDIAN_VAULT}`, `${OBSIDIAN_VAULT_NAME}`) via `envsubst`, 
lasciando letterale tutto il resto (inclusi gli esempi Nushell con `$PATH`/`$r`). Così il file 
versionato non contiene path hardcoded → il plugin è portabile tra macchine.

```json
// hooks/hooks.json → SessionStart
{
  "type": "command",
  "command": "${CLAUDE_PLUGIN_ROOT}/hooks/inject-core-behavior.sh",
  "timeout": 5
}
```

Conseguenze pratiche:

- Vale in **ogni** progetto col plugin attivo, senza bisogno di un `CLAUDE.md`.
- Il `CLAUDE.md` locale di un progetto ha **precedenza** in caso di conflitto (è più specifico).
- Per modificare il comportamento dell'agente si edita **questo file**, non i singoli progetti.
- I path che cambiano per macchina **non** sono nel file: vengono da variabili d'ambiente (vedi §10).

---

## 5. Skill incluse

In `skills/` (14), attivate per rilevanza dall'hook skill-eval o a richiesta:

| Skill | Uso |
|---|---|
| `hindsight` | memoria persistente (retain/recall/reflect), banchi |
| `obsidian` / `obsidian-cli` | vault Obsidian: note, Dataview, canvas / operazioni via CLI |
| `notebooklm` | NotebookLM via MCP exe-free: notebook, sources, chat, deep research |
| `mise` | gestione runtime, env e task |
| `nushell` | pipeline su dati strutturati |
| `ruby` | stile funzionale pragmatico per Ruby (Switchyard): pipeline dichiarative di action, contratti `expects`/`promises`, errori come valori con `try!`/`fail_and_return!`, immutabilità selettiva |
| `excalidraw-skill` | creazione/refine di diagrammi su canvas live |
| `lsp-enable` | navigazione codice via LSP (goToDefinition, references, diagnostica) |
| `book-to-skill` | converte libri/documenti in skill strutturate |
| `yt-extract` | estrae e analizza video YouTube (transcript, metadata, screenshot, commenti); solo su richiesta esplicita via `/trinity:yt-extract` |
| `adhd` | ideazione divergente parallela (tree-of-thought con pruning): brainstorm a più frame cognitivi, scoring e approfondimento dei migliori — via `/adhd` o intent di brainstorming; variante CLI in §12.3 |
| `github-pr-release` | workflow Git/GitHub per progetti personali: feature branch, PR con merge commit, changelog curato, release SemVer via `gh` (non per il rilascio del plugin Trinity: quello usa `/trinity:release`) |
| `skill-creator` | crea, modifica e ottimizza skill: eval del triggering, benchmark degli output con variance analysis, ottimizzazione delle `description` |

---

## 6. Comandi inclusi

In `commands/`, invocabili come slash command **namespaced** (`/trinity:<nome>`), così non 
collidono con i comandi locali del progetto:

| Comando | Funzione |
|---|---|
| `/trinity:reflect` | riflessione strategica sulla memoria Hindsight del progetto |
| `/trinity:promote` | promozione curata dei fatti dai bank di progetto al bank core |
| `/trinity:hindsight-create-agent` | crea un subagent con memoria Hindsight isolata per namespace tag |
| `/trinity:nota_del_giorno` | crea/aggiorna la nota del giorno col lavoro della sessione |
| `/trinity:ccr_model` | elenca i modelli configurati in ccr e le route attuali |
| `/trinity:release` | versiona il plugin (bump, commit, tag) e push dopo conferma |
| `/trinity:adhd-cli` | lancia la CLI `adhd-agent` (§12.3) con parametri formali (`--frames`, `--ideas`, `--top`, `--json`, …) |

---

## 7. Server MCP del plugin

Il `.mcp.json` nella root del plugin registra i server MCP che Trinity porta in **ogni**
progetto (sono file del plugin, non del singolo progetto):

| Server | Tipo | Cosa fornisce |
|---|---|---|
| `playwright` | stdio (node) | automazione browser headless (Playwright) |
| `notebooklm` | stdio (python, exe-free) | Google NotebookLM: notebook, sources, chat, artifact, deep research |
| `ticktick` | http (remoto, `mcp.ticktick.com`) | task, liste, abitudini, focus record e countdown di TickTick |
| `excalidraw` | stdio (node) | canvas Excalidraw live — `disabled: true` nel file |
| `obsidian_semantic_notes_vault` | http (`localhost:3002`) | accesso semantico al vault Obsidian — attivo, richiede l'app Obsidian in ascolto su :3002 |
| `debugger` | stdio (node, exe-free) | debug **autonomo** di Claude (mcp-debugger): breakpoint, step, variabili su Python/Ruby/JavaScript, 21 tool |
| `neovim` | stdio (node, exe-free) | pair-debugging sulla sessione **nvim-dap dell'utente** (fork `ichelema/mcp-neovim-server`): 21 tool `dap_*` + 18 `vim_*` |

Il server `hindsight` (memoria persistente, vedi §9) dal 2026-07-10 **non** sta più nel
`.mcp.json`: è registrato a **scope user** (`claude mcp add-json hindsight --scope user`)
come shim stdio `hooks/hindsight/mcp/hindsight-mcp-shim.sh`, che risolve il **bank
per-progetto** con la stessa `resolve_bank` degli hook (slug dal remote origin via
`CLAUDE_PROJECT_DIR`; repo Trinity o fuori git → core `trinity-project`), attende la
readiness del server e fa da ponte verso `http://127.0.0.1:8888/mcp/<bank>/` via
`mcp-remote` (node di mise, `npm install -g mcp-remote`). Non aggiungere una seconda
definizione `hindsight` a scope project: due scope con lo stesso nome generano il warning
"Conflicting scopes" a ogni sessione.

`ticktick` è l'unico server **remoto**: è gestito da TickTick
(`https://mcp.ticktick.com/`, Streamable HTTP), quindi non ha runtime locale né
processo da avviare. Si autentica con un Bearer token letto a runtime da
`${TICKTICK_API_KEY}` — l'espansione delle variabili vale anche nei campi `url` e
`headers`, così il segreto **non** entra nel repo: va definito per-macchina (§10). Il
token si crea dal web di TickTick: avatar in alto a sinistra → *Settings > Account >
API Token*; se un giorno viene revocato o scade, si rigenera da lì (il Bearer non ha
refresh automatico). Copre task, liste, abitudini, focus record e countdown; le funzioni
avanzate di TickTick non sono esposte.

Il runtime di `notebooklm` è **exe-free** e vive fuori dal repo (modulo in
`E:/AI/tools/notebooklm`, launcher con `truststore` per il proxy Eni): i file del plugin
restano il *cervello*, il runtime sta sul sistema (vedi §1). Il solo `excalidraw` è
marcato `disabled: true` nel file. Oltre a questi, Claude Code
espone i propri MCP **built-in** (es. `claude-in-chrome`), non gestiti da Trinity.

### I due server di debug (dal 2026-07-28)

Sono **complementari**, con ruoli precisi:

- **`debugger`** — [mcp-debugger](https://github.com/debugmcp/mcp-debugger) 0.23.0,
  runtime exe-free in `${MCP_DEBUGGER_DIR}` (tarball npm estratto **escludendo**
  `dist/vendor/codelldb` che contiene .exe; debugpy in `pylib/` senza i binari di
  injection — si perde solo l'attach-per-PID Python). Claude debugga **in autonomia**:
  "trovami il bug in questo script" senza che l'utente abbia nulla di aperto. Ruby usa
  la gem `debug`/rdbg del ruby mise del progetto (primo avvio a freddo: può servire un
  retry su `ECONNREFUSED`). Dettagli e procedura di aggiornamento nel
  `README.md` dentro `${MCP_DEBUGGER_DIR}`.
- **`neovim`** — fork [`ichelema/mcp-neovim-server`](https://github.com/ichelema/mcp-neovim-server)
  dell'upstream [`bigcodegen/mcp-neovim-server`](https://github.com/bigcodegen/mcp-neovim-server)
  (dev in `E:/Sviluppo`, runtime in `${MCP_NEOVIM_DIR}`): **pair-debugging** sulla
  sessione nvim-dap che guida l'utente — Claude ispeziona variabili, muove step e
  breakpoint attraverso l'RPC di Neovim, nvim-dap resta l'unico client DAP (zero
  conflitti). Si collega alla named pipe per-progetto
  `\\.\pipe\claude-debug-<basename cwd>` che la config nvim dell'utente crea con un
  autocmd (`VimEnter`+`DirChanged`); nel `.mcp.json` la pipe usa la forma `//./pipe/...`
  (i backslash si perdono al confine MSYS). Gotcha Windows: cwd di nvim, buffer e file
  debuggati devono stare **sullo stesso drive**, altrimenti i breakpoint restano
  pending; se rdbg muore con exit 1 controllare che `HOME` non punti a un drive
  assente (override WezTerm→chiavetta).

**Per esempio di utilizzo vedere il videp youtube**
https://youtu.be/cEPzAwb1ldU?si=YX44a7rfZnbnXM7q



---

## 8. Plugin di terze parti vendorizzati (`vendor/`)

Dal 2026-07-31 i plugin Claude Code di **terze parti** non passano più dal marketplace
(`enabledPlugins` è vuoto): sono **vendorizzati** dentro il repo in `vendor/<nome>/` e
caricati con lo stesso meccanismo skills-dir di Trinity (§2), una junction/symlink per
plugin. Così viaggiano con `git push/pull` e ogni macchina è allineata senza install
per-macchina; ogni plugin conserva il proprio namespace (`ui-craft:*`, `claude-bionify:*`).

| Plugin | Versione | Cosa fa | Upstream |
|---|---|---|---|
| `ui-craft` | 1.0.0 | design engineering per agenti: anti-slop UI, spec-driven design (`/sddesign`), agent design-review + a11y, MCP quality gates | [educlopez/ui-craft](https://github.com/educlopez/ui-craft) |
| `claude-bionify` | 1.0.2 | bionic reading: hook `MessageDisplay` (script Python) che grasseta la parte iniziale delle parole nelle risposte | [abullard1/claude-bionify](https://github.com/abullard1/claude-bionify) |

Com'è fatta una cartella `vendor/<nome>/`:

- **copia snella** dell'upstream: solo `skills/`, `commands/`, `agents/`, `hooks/`,
  `.claude-plugin/plugin.json`, `.mcp.json`, `LICENSE` — niente CLI, e2e, asset;
- **`VENDOR.txt`**: upstream, versione/commit copiati e procedura di aggiornamento
  (ri-copiare le stesse dir dall'upstream — non c'è più `claude plugin update`);
- il server MCP di `ui-craft` (`npx -y ui-craft-mcp`) è dichiarato nel suo `.mcp.json`
  e viene caricato anche via skills-dir;
- l'hook di `claude-bionify` richiede `python3` nel PATH (su Linux: verificare).

> `yt-extract` non è più in questo elenco: dal 2026-07-03 è una **skill** di Trinity
> (`/trinity:yt-extract`, §5); il suo runtime esterno resta in
> `E:/AI/tools/claude-code-youtube-extract` (aggiornamenti: job `yt-check`, §11).

---

## 9. Memoria Hindsight (multi-bank: core + bank per progetto)

La memoria è organizzata a **due livelli** (dal 2026-06-12): un bank **CORE** condiviso
(`trinity-project`, le informazioni trasversali — preferenze utente, vincoli d'ambiente,
procedure di toolchain) e un **bank per progetto** isolato (le informazioni che hanno senso
solo lì e non devono inquinare gli altri progetti). Hindsight non ha ereditarietà nativa tra
bank: l'aggregazione la fanno gli hook client-side.

Il blocco `bank` di `hindsight.config.json` governa tutto:

```json
"bank": {
  "api_base": "http://127.0.0.1:8888/v1/default",
  "core_bank": "trinity-project",
  "retain_bank": "auto",
  "recall_banks": ["auto", "core"],
  "promote_exclude_banks": ["obsidian"]
}
```

- **`retain_bank`** (scalare, la scrittura ha un bersaglio): `auto` = slug del repo corrente
  (nome dal remote `origin`, fallback basename; fuori da git — o dentro il repo del plugin
  stesso — ricade sul core); `core` = il core; altro valore = nome bank letterale. Il bank si
  **auto-crea al primo retain**, zero provisioning.
- **`recall_banks`** (array, la lettura aggrega): fan-out **parallelo** sui bank risolti, fino
  a `recall_per_bank_candidates` candidati per bank (plugin: 6), poi dedup, rerank globale
  **zerank-2** via ZeroEntropy (gli score di bank diversi non sono confrontabili tra loro),
  filtro sotto la soglia `recall_min_rerank_score` (0.5 nel plugin, solo percorso multi-bank),
  taglio finale a `recall_max_results_multibank` risultati iniettati (5 nel plugin). Se
  ZeroEntropy non risponde, fallback a interleaving senza rerank (la soglia non viene
  applicata). Il core entra **solo se listato**: `["auto"]` da solo = progetto totalmente
  isolato. Con un solo bank risolto il percorso è la singola POST di sempre, zero overhead
  multi-bank; la soglia client non si applica, ma i floor `min_scores` server-side sì
  (bullet successivo).
- **Floor per-stadio `min_scores`** (hindsight-api ≥ 0.8.4): le chiavi
  `recall_min_semantic` / `recall_min_keyword` (cutoff retrieval-level, dentro i bracci SQL:
  un risultato tagliato da un braccio può rientrare dall'altro) e `recall_min_reranker` /
  `recall_min_final` (filtri post-rerank applicati dal server) viaggiano nel payload di
  recall e valgono per **entrambi** i percorsi, single- e multi-bank. Tutte `null` = nessun
  filtro; il plugin attiva `recall_min_reranker: 0.15`, tarato su dati reali del bank core
  (rumore fuori dominio < 0.08, risultati legittimi ≥ 0.27). Il debug log riporta per ogni
  memoria i punteggi per-stadio del server (`scores.{final,reranker,semantic,keyword}`)
  accanto allo `score` del rerank client multi-bank.
- **Freshness del ranking**: il server applica una curva di recency exponential con emivita
  60 giorni (`HINDSIGHT_API_RECENCY_DECAY_*` in `mise.toml`, config server-globale): boost
  cappato a ±10%, fatti a 60 giorni neutri — i near-duplicate superati perdono contro la
  versione fresca a parità di rilevanza.
- **Retrocompat**: un `api_url` esplicito in un override (file o env) vince sul blocco bank e
  ripristina il comportamento single-bank. I tag (`claude-code`, `repo:`, `branch:`) restano
  invariati.

Per vedere su quali bank si risolve il progetto corrente (debug):

```bash
python hooks/hindsight/lib/hindsight_config.py --banks   # URL retain + recall risolti
```

**Ricette rapide** (override nel `hindsight.config.json` del progetto):

> **Nota:** la config del plugin ha `retain_enabled: false` — il retain automatico è
> **opt-in per progetto**: ogni progetto che vuole la memoria automatica deve abilitarlo
> esplicitamente con `{ "retain_enabled": true }`.

| Voglio… | Override |
|---|---|
| default (solo recall): legge progetto+core, retain disabilitato | nessuno (eredita il plugin) |
| abilitare il retain automatico (scrive sul bank del progetto) | `{ "retain_enabled": true }` |
| progetto totalmente isolato (non legge nemmeno il core) | `{ "bank": { "recall_banks": ["auto"] } }` |
| progetto che scrive direttamente sul core (niente bank proprio) | `{ "bank": { "retain_bank": "core" } }` |
| leggere anche il bank di un altro progetto | `{ "bank": { "recall_banks": ["auto", "NomeAltroBank", "core"] } }` |

**Promozione progetto → core (curata, mai automatica).** Il funnel è scan → triage LLM
(gpt-4.1-nano: *"resterebbe utile su un progetto completamente diverso?"*) → review umana →
move: comando **`/trinity:promote`**, meccanica in `hooks/hindsight/ops/hindsight-promote.py`.
Il move ritiene l'`original_text` sul core (con strip dei tag `repo:`/`branch:`, che nello
scope all_strict impedirebbero la fusione cross-repo) e cancella il documento dal bank
progetto. Lo stato (revisionati, anche respinti, + cache dei verdetti triage) è in
`logs/promote-state.json`. Il job settimanale `scheduler/promote_scan/` esegue solo
scan+triage e apre un alert se ci sono candidati (vedi il suo README).

La configurazione del servizio (provider LLM/embedding, env TLS, task 
`start/stop-hindsight`, `control-plane`) è in **`mise.toml`**, usato dagli hook via 
`mise -C <plugin_root> run <task>`. È la fonte di verità del runtime Hindsight.

**Override della config per-progetto.** I parametri runtime degli hook (budget, tag, 
`recall/retain_enabled`, timeout, …) stanno in **`hindsight.config.json` nella root del plugin**. 
Un progetto può personalizzarli mettendo un proprio `hindsight.config.json` **nella sua root**: 
il loader fa un **merge a strati** — DEFAULTS → config del plugin → config del progetto → env — 
quindi il file del progetto sovrascrive **solo** le chiavi che contiene (anche una sola riga), 
ereditando il resto dal plugin. I valori **dict** (come `bank`) fanno merge a un livello: un 
override parziale non cancella le chiavi non menzionate. Esempio (`<progetto>/hindsight.config.json`):

```json
{ "retain_enabled": true, "bank": { "recall_banks": ["auto"] } }
```

**Failcheck dei retain falliti.** Il retain è asincrono: Claude Code lo lancia in background
e non aspetta il risultato. Se l'estrazione LLM fallisce (es. credito OpenAI esaurito), la
memoria **non viene salvata** senza che nessuno se ne accorga. L'hook `hindsight-failcheck.sh`
(terzo hook di `UserPromptSubmit`) interroga l'endpoint `/operations?status=failed` su tutti
i bank (retain + recall) a ogni prompt, deduplicando le notifiche via state file in `%TEMP%`
con finestra di 24h. Le failed vengono classificate in due categorie: **retain falliti**
(perdita di memoria — critici) e **task di mantenimento falliti** (consolidation,
refresh_mental_model — si auto-recuperano al ciclo successivo). L'avviso arriva come
`additionalContext` nel contesto del modello. Controllato dal flag `failcheck_enabled` (di
default `true`, indipendente da `recall_enabled`/`retain_enabled`).

**Mental model — iniezione a SessionStart.** Oltre al recall real-time per prompt, Hindsight
inietta a ogni `SessionStart` tre **mental model** sintetici via `hindsight-mm-inject.sh`:
riassunti tematici generati interrogando il bank con query predefinite, che danno al modello
un profilo costante dell'utente e del progetto senza aspettare che il recall lo ricostruisca
dal flusso dei prompt. Configurati in `hindsight.config.json` → `mental_models`:

| id | Cosa sintetizza |
|---|---|
| `user-profile` | ruolo, preferenze strumenti/linguaggi, stile comunicazione, ambiente di lavoro |
| `project-conventions` | shell/path, gestione pacchetti, regole git, sicurezza, posizione file test |
| `recurring-learnings` | bug ricorrenti, workaround, lezioni apprese sul campo, criticità toolchain |

`mental_models_inject_on_start: true` e `mental_models_inject_ids` nel config del plugin
controllano quali vengono caricati. Il token budget è `mental_model_max_tokens` (plugin: 2048).

---

## 10. Setup per-macchina (valori machine-specific)

Il plugin non contiene path hardcoded: i valori che cambiano da macchina a macchina vengono 
da **variabili d'ambiente** nell'env utente di `~/.claude/settings.json`.

Dal 2026-07-31 quel file **non si edita più a mano**: è generato dai file versionati in
`config/claude/` — `settings.shared.json` (preferenze portabili, uguali ovunque) +
`settings.windows.json` / `settings.linux.json` (env e path per OS) — con un merge a tre
strati (locale → shared → overlay OS) che preserva le chiavi solo locali e fa backup `.bak`.
Flusso: modifica in `config/claude/` → push/pull → **`mise run sync-settings`** su ogni
macchina (su Linux lo esegue anche `bootstrap-linux.sh`, sezione 6). `TRINITY_PLUGIN_DIR`
è calcolata dallo script dalla posizione del repo, mai scritta negli overlay.

Le variabili qui sotto vanno quindi nell'**overlay dell'OS** (es.
`config/claude/settings.windows.json`):

```json
{
  "env": {
    "OBSIDIAN_VAULT": "D:/Obsidian/Sinapsi",
    "OBSIDIAN_VAULT_NAME": "Sinapsi",
    "NOTEBOOKLM_DATA": "E:/AI/tools/notebooklm-data",
    "NOTEBOOKLM_LIB": "E:/AI/tools/notebooklm",
    "MCP_EXCALIDRAW_DIR": "E:/msys64/home/Sphynx/.local/opt/mcp_excalidraw",
    "ADHD_LIB": "E:/AI/tools/adhd",
    "MCP_DEBUGGER_DIR": "E:/AI/tools/mcp-debugger",
    "MCP_NEOVIM_DIR": "E:/AI/tools/mcp-neovim-server"
  }
}
```

`NOTEBOOKLM_*` e `MCP_EXCALIDRAW_DIR` servono ai server MCP `notebooklm` ed
`excalidraw`, `ADHD_LIB` alla CLI `adhd` (§12.3): puntano tutte a
strumenti esterni installati **fuori dal repo**: definiscile col path locale
dell'installazione. Su un'altra macchina (o su Linux) i path cambiano — vanno
messi quelli dell'installazione locale di quegli strumenti (vedi
`docs/SETUP-LINUX.md`). Senza queste variabili quei due server non partono (warning
in avvio, resto invariato); `excalidraw` è comunque `disabled` di default.

Su un'altra macchina con lo stesso vault sincronizzato in un path diverso, basta cambiare il 
valore (es. `"/home/sphynx/Obsidian/Sinapsi"`): `core-behavior.md` resta identico, l'iniezione 
lo espande con i valori locali. La versione MSYS del path si ricava con `cygpath -u`, non serve 
una variabile separata.

| Cosa | Come è risolto |
|---|---|
| root del progetto | `${CLAUDE_PROJECT_DIR}` (gli hook la ricevono da Claude Code) — già automatico |
| root del plugin | `${CLAUDE_PLUGIN_ROOT}` — già automatico |
| vault Obsidian | `${OBSIDIAN_VAULT}` / `${OBSIDIAN_VAULT_NAME}` — **da definire per-macchina** |
| root di questo repo | `${TRINITY_PLUGIN_DIR}` (per i comandi delle skill) — **automatica**: la scrive `sync-settings` dalla posizione del repo |
| token TickTick (§7) | `${TICKTICK_API_KEY}` — **da definire per-macchina**, ma nell'**env utente**, non qui: è un segreto (Windows: `SetEnvironmentVariable(…, "User")`; Linux: `~/.profile`, vedi `docs/SETUP-LINUX.md`) |
| server MCP notebooklm | `${NOTEBOOKLM_DATA}` / `${NOTEBOOKLM_LIB}` — **da definire per-macchina** (path dello strumento esterno, non del repo) |
| server MCP excalidraw | `${MCP_EXCALIDRAW_DIR}` — **da definire per-macchina** (path dello strumento esterno; server `disabled` di default) |
| CLI adhd (§12.3) | `${ADHD_LIB}` — **da definire per-macchina** (root dell'installazione di `adhd-agent`, non del repo); se manca, `scripts/bin/adhd` esce con errore esplicito |
| server MCP debugger (§7) | `${MCP_DEBUGGER_DIR}` — **da definire per-macchina** (installazione exe-free di mcp-debugger, fuori dal repo) |
| server MCP neovim (§7) | `${MCP_NEOVIM_DIR}` — **da definire per-macchina** (deploy del fork mcp-neovim-server, fuori dal repo; il sorgente sta in `E:/Sviluppo`) |

> Dipendenza: l'espansione usa `envsubst` (pacchetto `gettext`, presente di default su MSYS2/Linux/Mac). 
> Se manca, lo script ricade su `sed`. Se le env non sono impostate, il testo iniettato mostra un 
> avviso esplicito anziché un valore vuoto.

---

## 11. Job schedulati

Su **Windows** i job girano via **System Scheduler (Splinterware)**; sul **server Linux**
gli stessi job — limitati a quelli sensati sul server — girano via **timer systemd**
(vedi [`scheduler/systemd/README.md`](scheduler/systemd/README.md) e la sottosezione 11.2).

### 11.1 Windows — System Scheduler

Sei job girano in background via **System Scheduler (Splinterware)**, lo scheduler a
icona nella tray di Windows. Non sono hook Claude Code: girano indipendentemente dalla
sessione, secondo una cadenza configurata nella GUI del programma. Ogni job segue la stessa
struttura a tre livelli:

```
System Scheduler (orario programmato)
  └─ <nome>-scheduled.cmd     ponte Windows → MSYS2 (imposta MSYSTEM, HOME, PATH)
       └─ <nome>-scheduled.sh  wrapper: log, gestione alert, exit code
            └─ mise run <task>  dà Ruby/Python giusti + env TLS proxy aziendale
```

Il `.cmd` è necessario perché System Scheduler è un eseguibile Windows puro: non può lanciare
direttamente uno script MSYS2 senza che qualcuno prima imposti l'ambiente UCRT64. Il `.sh`
gestisce log (una riga JSON per run), alert via Notepad e codici d'uscita standard (`0` = OK,
`10` = novità/candidati, `3` = server Hindsight giù — il job salta senza tentare la
connessione).

| Job | Cartella | Cadenza | Cosa fa |
|---|---|---|---|
| `api-check` | `scheduler/check_update_hindsight_api/` | settimanale | Controlla PyPI: nuova versione di `hindsight-api` o `hindsight-api-slim` rispetto a quella installata. Baseline = versione installata (si alza da sola dopo ogni upgrade, niente pin da aggiornare) |
| `cp-check` | `scheduler/check_update_hindsight_control_plane/` | settimanale | Controlla npm: nuova versione di `@vectorize-io/hindsight-control-plane` rispetto al pin nel `mise.toml`. Baseline = pin (va alzato a mano nel `mise.toml` per aggiornare) |
| `promote-scan` | `scheduler/promote_scan/` | settimanale | Scansiona i bank Hindsight di progetto, triage LLM (gpt-4.1-nano) dei fatti candidati alla promozione sul core. Non promuove nulla: apre un alert se ci sono candidati per `/trinity:promote`. Verdetti cachati in `logs/promote-state.json` |
| `nb-auth-refresh` | `scheduler/notebooklm/` | ogni 15–20 min | Rinnova i cookie di sessione di `notebooklm-py` (`__Secure-1PSIDTS`) prima che scadano. Dopo 3 fallimenti consecutivi apre un alert con le istruzioni per rigenerare i cookie SID di base |
| `nb-check` | `scheduler/check_update_notebooklm/` | settimanale | Controlla PyPI: nuova versione di `notebooklm-py` rispetto a quella installata in `E:/AI/tools/notebooklm`. Baseline = versione installata (dal dist-info locale). Nota: la versione corrente viene da GitHub (`main`, exe-free); l'alert si attiverà quando PyPI raggiungerà la stessa versione |
| `yt-check` | `scheduler/check_update_yt_extract/` | settimanale | Controlla GitHub (`/releases/latest`, fallback `/tags`): nuova versione del plugin `yt-extract` rispetto al clone locale `E:/AI/tools/claude-code-youtube-extract`. Baseline = prima riga `## [X.Y.Z]` del `CHANGELOG.md`. Ricorda: dopo ogni `git pull` va riapplicata la patch `run_ytdlp()` (exe-free) |

**Alert**: quando un job trova qualcosa da segnalare, scrive `*-ALERT.txt` nella sua cartella
e lo apre in Notepad. Quando non c'è più nulla, **rimuove** l'alert: la sola presenza del
file è un segnale affidabile. La variabile `*_NO_OPEN=1` evita l'apertura del Notepad nei
test manuali (es. `PROMOTE_NO_OPEN=1 bash scheduler/promote_scan/promote-scan-scheduled.sh`).

**Configurazione comune in System Scheduler:**

| Campo | Valore |
|---|---|
| Event Type | `Run Application` |
| Application | path assoluto al `.cmd` della cartella del job |
| Parameters | *(vuoto)* |
| Working Dir | `E:\AI\Claude\Trinity` |
| State | `Minimized` o `Hidden` |

I dettagli di ogni job (campi esatti, note TLS/proxy, variabili override, test manuali) stanno
nel `README.md` della rispettiva cartella.

### 11.2 Linux (server) — timer systemd

Sul server Linux non c'è System Scheduler: gli `*-scheduled.sh` (già bash portabile) sono
lanciati **direttamente** da timer systemd utente, senza il ponte `.cmd`. Girano solo i 3 job
sensati sul server; `nb-check`, `yt-check` e `nb-auth-refresh` restano Windows-only (dipendono
dagli strumenti exe-free in `E:/AI/tools` e dai cookie del browser dell'utente).

| Unit | Cadenza | Job |
|---|---|---|
| `trinity-promote-scan` | dom 09:00 | scan+triage candidati promozione |
| `trinity-api-check` | dom 09:15 | nuove versioni `hindsight-api`/`-slim` su PyPI |
| `trinity-cp-check` | dom 09:30 | nuova versione Control Plane su npm vs pin `mise.toml` |

Installazione (unit utente, niente root), verifica e gestione: vedi
[`scheduler/systemd/README.md`](scheduler/systemd/README.md).

---

## 12. External Tools

Strumenti di **terze parti** usati accanto a Trinity ma che **non** fanno parte del plugin: vivono
fuori dal repo, si installano per-macchina e — a differenza dei plugin (§8) — non si caricano in
Claude Code, sono processi/proxy esterni.

### 12.1 Headroom (compressione del contesto via proxy)

[Headroom](https://github.com/chopratejas/headroom) comprime il contesto che arriva all'LLM
(output di tool, log, file, RAG, cronologia) — stessi risultati, **meno token**. Si usa come
**proxy locale** davanti all'API Anthropic: zero modifiche al codice.

**Vincolo PC Eni:** l'EDR blocca i `.exe`. Headroom è installato **exe-free** (come `notebooklm-py`
e `yt-extract`): wheel scompattati a mano, mai `pip install`. Il nodo è che la compressione gira in
un **core Rust** (`headroom._core`) e su PyPI **non esiste un wheel Windows** → il core è stato
**compilato in locale** con la toolchain Rust di pacman, senza creare `.exe` nuovi.

| Voce | Valore |
|---|---|
| Repo sorgente | `E:/AI/tools/headroom` (v0.27.0) |
| Pacchetto runtime | `E:/AI/tools/headroom-pkg` (dipendenze + `headroom/` + `_core.pyd`) |
| Python | mise 3.13.13 |
| Toolchain build | `mingw-w64-ucrt-x86_64-rust` (`/ucrt64/bin/cargo`, target gnu, linker gcc) |
| Motore compressione | SmartCrusher (JSON) / CodeCompressor (AST) — algoritmici, locali, lingua-agnostici; **niente** modello ML inglese |

#### Installazione (riepilogo)

Le dipendenze sono scaricate con `pip download` e **scompattate a mano** (mai `pip install`, che
creerebbe i `.exe` dei `console_scripts`). Set minimale: `fastapi`, `uvicorn`, `httpx`, `tiktoken`,
`pydantic`, `click`, `rich`, `tree-sitter`. **Esclusi** gli extra ML (`onnxruntime`, `transformers`,
`torch`, `magika`, `fastembed`) — sono lazy, e il loro modello testo (Kompress/ModernBERT) è tarato
sull'inglese, inutile per la prosa italiana. Escluso anche `ast_grep_cli` (unico wheel con `.exe`
interni); la compressione del codice usa `tree-sitter`.

Ricompilare il core Rust `_core.pyd` (serve solo se aggiorni il repo):

```bash
cd E:/AI/tools/headroom
export PATH="/ucrt64/bin:$PATH"
export CARGO_HTTP_CHECK_REVOKE=false   # il proxy MITM Eni rompe il check di revoca di schannel
cargo build --release -p headroom-py --features extension-module
cp target/release/_core.dll E:/AI/tools/headroom-pkg/headroom/_core.pyd
```

Verifica finale: **nessun `.exe`** nel pacchetto — `find E:/AI/tools/headroom-pkg -iname '*.exe'`
deve essere vuoto.

#### Avvio

Due launcher:

| Launcher | Cosa fa |
|---|---|
| `E:/AI/tools/headroom-pkg/headroom.sh` | base: imposta `PYTHONPATH` + `HEADROOM_BINARIES_OFFLINE=1` (blocca il fetch a runtime di `difft.exe`/`scc.exe`) e lancia `python -m headroom.cli`. Per i comandi statistiche/dashboard. |
| `~/.local/bin/claude-headroom.sh` | integrato: avvia il proxy su `:8787`, punta `ANTHROPIC_BASE_URL` al proxy e lancia `claude`; replica le env dell'alias zsh `claude` (`HOME`/`USERPROFILE`/`CLAUDE_CONFIG_DIR`). Allo stop di Claude ferma il proxy se l'ha avviato lui. |

```bash
claude-headroom.sh            # avvia proxy + Claude attraverso la compressione
```

> ⚠️ Distinto dai launcher LiteLLM (§13): `claude-headroom.sh` punta a Headroom (`:8787`),
> `litellm-*.sh` puntano a LiteLLM (`:4000`). Entrambi impostano `ANTHROPIC_BASE_URL` → non
> mescolarli nella stessa sessione.

#### Monitoraggio (dashboard web)

Con il proxy attivo:

```bash
E:/AI/tools/headroom-pkg/headroom.sh dashboard      # apre http://127.0.0.1:8787/dashboard
```

| Comando / endpoint | Cosa mostra |
|---|---|
| `headroom.sh dashboard` | UI web **live**: risparmi in tempo reale |
| `headroom.sh savings` | riepilogo persistente (ledger `~/.headroom/savings_events.jsonl`) |
| `headroom.sh perf --hours 24` | analisi dai log: token salvati, cache hit, breakdown dei transform |
| `curl http://127.0.0.1:8787/stats` | statistiche grezze (anche `/stats-history`, `/health`) |
| `http://127.0.0.1:8787/dashboard` | nel browser vedo la dashboard |

I **token** risparmiati sono tracciati; il valore in **€** resta `0` perché richiede LiteLLM,
escluso di proposito.

> **Perché il `SAVED` è spesso ~0%?** Headroom preserva il **prompt caching** di Anthropic e
> protegge il contesto recente: su una sessione di coding con cache piena comprime poco (la cache
> fa già il risparmio grosso), mentre rende molto su grossi output di tool / JSON. Per comprimere
> anche le **letture vecchie**, `claude-headroom.sh` imposta
> `HEADROOM_STALE_READ_COMPRESS_AFTER_TURNS=2` (letture più vecchie di 2 turni diventano
> comprimibili; alza il valore per essere più conservativo, `0` disattiva). Trade-off: possibili
> cache miss sul prefix — tieni d'occhio anche la **latenza** in dashboard.

#### Attribuzione per progetto ("Per-Project Savings")

La dashboard ha una sezione **Per-Project Savings** che separa i risparmi per progetto
invece di un unico totale. Il proxy riconosce un prefisso `/p/<nome>` nel path del base
URL (`proxy/project_context.py` → `split_project_path`): il primo segmento dopo `/p/`
viene url-decodato e sanitizzato (solo caratteri stampabili) come nome progetto.

`claude-headroom.sh` accoda automaticamente `/p/<basename della cartella corrente>` a
`ANTHROPIC_BASE_URL` (gli spazi sono encodati `%20`). Esempio: lanciato da
`…/Claude/Trinity` la sessione usa `http://127.0.0.1:8787/p/Trinity` e nella dashboard
compare la riga **`Trinity`** (verificato live). Il nome segue sempre la cartella: nessun
override.

> Il base URL viene letto **all'avvio** di `claude`: una sessione già in corso non cambia
> attribuzione a caldo. Per attivarla apri una **nuova** sessione col launcher dalla cartella
> del progetto — le sessioni Headroom convivono (multi-sessione).

### 12.2 Context Window Dashboard (analisi dei token del contesto)

Web app **locale** che analizza la **context window** di Claude Code: cosa entra in contesto e quanti
token costa, leggendo i **transcript reali** in `.claude/projects` (nessun dato finto). Una sola vista
"ciclo di vita" — la composizione pre-prompt più la timeline di ogni interazione — che si aggiorna
**live** mentre lavori. A differenza di Headroom (proxy che _riduce_ i token), questa solo _analizza_;
gira come processo esterno e non fa parte del plugin.

| Voce | Valore |
|---|---|
| Cartella | `D:/AI/Claude/Dashboard Context Window` |
| Stack | Ruby + Roda + Puma (backend) · Mithril + Vite (frontend) · mise |
| Dati | transcript JSONL in `.claude/projects` (`CLAUDE_DIR`, default `E:/msys64/home/Sphynx/.claude`) |
| Runtime | Ruby 4.0.1 (mise) · Node lts · Mithril 2.3.6 |
| Porte | Puma `:9292` (API + build) · Vite dev `:5173` (proxy `/api` → `:9292`) |

#### Cosa mostra

- **Before you type anything**: composizione del contesto pre-prompt (system prompt, memoria
  `MEMORY.md`, descrizioni skill, tool MCP, `CLAUDE.md`, output hook) — token **misurati** da disco e
  dal transcript, **stimati** ed etichettati dove interni a Claude Code.
- **Per ogni prompt**: timeline reale degli eventi (tool call, file read, output, risposte di Claude,
  subagent, hook), con totali per categoria You/Files/Output/Claude/Hooks/Subagent.
- **Contesto vs limite del modello** (Opus/Sonnet 4.x → 1M, letto da `message.model`), **sparkline**
  dell'andamento, **pannello Inspect** (input/output di ogni elemento) e un **player** che ripercorre la
  sessione dall'avvio con scrub.
- Aggiornamento **live** via polling 2s finché la sessione è viva.

#### Installazione (prima volta)

```bash
cd "D:/AI/Claude/Dashboard Context Window"
mise run setup     # bundle install (gem: roda, puma, rackup, json) + npm --prefix web install (mithril, vite)
```

I task `mise` (in `mise.toml`): `setup` · `dev` · `api` · `web` · `build` · `serve`. Lanciali **dalla
shell con `mise activate`** (lì `ruby` → 4.0.1, `node` → lts).

#### Sviluppo (hot reload)

Due processi: Puma serve le API su `:9292`, Vite serve il frontend su `:5173` con HMR e fa **proxy** di
`/api` verso Puma.

```bash
mise run dev       # avvia Puma :9292 e Vite :5173 insieme → apri http://localhost:5173
# oppure, in due terminali separati:
mise run api       # solo backend  → http://localhost:9292
mise run web       # solo frontend → http://localhost:5173
```

In sviluppo apri sempre **:5173** (non :9292): è Vite che serve i sorgenti non buildati e inoltra le API.

#### Build di produzione (bundle del frontend)

```bash
mise run build     # = npm --prefix web run build  →  vite build
```

Emette il **bundle statico** in `web/dist/`: `index.html` + `assets/index-*.js` e `assets/index-*.css`
(con content-hash, minificati). È ciò che va in produzione; `web/dist/` è git-ignored e si rigenera a ogni
build. Roda lo serve da questa cartella (costante `App::DIST` in `app/app.rb`).

#### Produzione (porta singola)

In produzione **un solo processo** Roda/Puma serve sia la SPA buildata sia le API, sulla stessa origine
`:9292` (niente Vite, niente proxy):

```bash
mise run serve     # = build del frontend + Puma :9292 che serve web/dist + le API
# se web/dist è già buildato, basta avviare Puma:
bundle exec puma -p 9292        # legge config.ru → run App
```

Apri **http://localhost:9292**. Ferma con `Ctrl-C`. Se apri la root **senza** aver fatto la build, Roda
risponde con un avviso _"Frontend non buildato"_ (fallback in `app/app.rb`) invece della pagina.

| | Sviluppo | Produzione |
|---|---|---|
| Comando | `mise run dev` | `mise run serve` |
| Frontend | Vite `:5173` (HMR, sorgenti) | Roda serve `web/dist` |
| API | Puma `:9292` (via proxy) | Puma `:9292` (stessa origine) |
| URL da aprire | `http://localhost:5173` | `http://localhost:9292` |

API esposte: `/api/projects`, `/api/projects/:id/sessions`, `/api/context/:pid/:sid`,
`/api/timeline/:pid/:sid?after=N`, `/api/event/:pid/:sid/:index`.

> **Configurazione:** `CLAUDE_DIR` (in `mise.toml`, sezione `[env]`) decide quale cartella `.claude`
> analizzare. Porta diversa: `bundle exec puma -p 8080` (e in sviluppo aggiorna il `proxy` in
> `web/vite.config.js`).

> ⚠️ **Windows/MSYS2:** i task `web`/`build` usano `npm` e funzionano nella shell con `mise activate`
> (`npm` è quello di Node gestito da mise). Se invece `npm` crasha fuori da mise (il wrapper MSYS2 dà
> `std::bad_weak_ptr` sotto bash), bypassalo lanciando Vite con `node` diretto:
> `node web/node_modules/vite/bin/vite.js build` (dev: senza `build`, con `--root web`). L'anteprima nel
> pannello usa `.claude/launch.json` (config `dashboard`, Roda su `:9292`).

### 12.3 adhd-agent (CLI di ideazione divergente)

[adhd](https://github.com/UditAkhourii/adhd) esiste in due forme: la **skill** `skills/adhd/`
(solo Markdown, viaggia col repo, vedi §5) e la **CLI** `adhd-agent`, che esegue lo stesso
metodo in autonomia via Claude Agent SDK (usa l'autenticazione di `claude` già presente)
e accetta parametri formali: `--frames`, `--ideas`, `--top`, `--context`, `--json`, ….

**Install exe-free (Windows/Eni):** niente npm — tarball scaricati con curl da
`registry.npmjs.org` e scompattati a mano in `${ADHD_LIB}/node_modules/`
(`adhd-agent` 0.1.4 già compilato + `@anthropic-ai/claude-agent-sdk` 0.1.77 +
`p-limit` + `yocto-queue` + `zod`; l'SDK non ha dipendenze runtime obbligatorie).
Su Linux, senza vincolo EDR, basta `npm install adhd-agent` in una cartella locale.

**Invocazione:** il wrapper versionato `scripts/bin/adhd` risolve Node a runtime via
`run-node.sh` (mise → PATH) e legge la root dell'installazione da `${ADHD_LIB}` (§10) —
zero path hardcoded. Da una sessione: `/trinity:adhd-cli "problema" --frames 3`.
Ogni run fa più chiamate LLM (minuti e quota reali: per prove usare
`--frames 1 --ideas 2 --top 1 --model claude-haiku-*`).

---

## 13. Modelli alternativi: LiteLLM e claude-code-router

Claude Code punta di default all'API Anthropic. Per usare altri provider (GPT, DeepSeek, Gemini)
esistono due approcci complementari, entrambi attivi su questa macchina:

| Approccio | Quando usarlo |
|---|---|
| **LiteLLM proxy** | approccio corrente; GPT (ChatGPT Max OAuth) e DeepSeek; più semplice da mantenere |
| **claude-code-router (CCR)** | router con pipeline di transformer per provider; richiede patch e rebuild del bundle |

---

### 13.1 LiteLLM proxy (porta 4000)

LiteLLM espone un endpoint OpenAI-compatible a `http://127.0.0.1:4000`. Claude Code ci punta
tramite launcher shell che impostano le variabili d'ambiente corrette prima di lanciare `claude`.

**File coinvolti** (tutti fuori dal repo Trinity, sulla macchina):

| File | Ruolo |
|---|---|
| `~/.litellm/litellm_config.yaml` | modelli, routing, `reasoning_effort` per tier |
| `~/.litellm/callbacks.py` | hook LiteLLM (pre-call, post-call) |
| `~/.local/bin/litellm-start-proxy.sh` | avvia il proxy via `litellm-proxy-run.py` |
| `~/.local/bin/litellm-gpt.sh` | launcher Claude Code → GPT/ChatGPT Max (OAuth) |
| `~/.local/bin/litellm-deepseek.sh` | launcher Claude Code → DeepSeek (dal 2026-06-19) |

Il DB di LiteLLM usa lo stesso Postgres embedded di Hindsight, ma su un database separato
chiamato `litellm`.

**`callbacks.py` — perché è necessario per il recall Hindsight.**

Quando un hook `UserPromptSubmit` (hindsight-recall, skill-eval) ha qualcosa da dire al modello,
stampa un JSON con `additionalContext`. Claude Code prende quel testo e lo inserisce nella
request come messaggio **`role:system` inline**, mescolato tra i messaggi `user`/`assistant`:

```
request.messages = [
  { role: "user",   content: "domanda utente" },
  { role: "system", content: "## Hindsight persistent memory..." },  ← additionalContext
  { role: "user",   content: "..." },
  ...
]
```

Con **Anthropic diretto** questo funziona: l'API Anthropic accetta `role:system` inline senza
problemi e il modello vede il recall.

Con **ChatGPT via LiteLLM** il problema è a due livelli:

1. La catena interna LiteLLM `anthropic_messages → completion → responses` trasforma il
   formato Anthropic in quello OpenAI, conservando solo ruoli `user` e `assistant` e scartando
   i messaggi `role:system` inline.
2. Anche se passassero, i modelli ChatGPT rifiutano `role:system` inline con **HTTP 400**.

Risultato senza fix: recall Hindsight e skill-eval **sparivano silenziosamente** ogni volta
che si usava un modello ChatGPT.

**Soluzione:** la callback `SystemToInstructions.async_pre_call_hook` in `~/.litellm/callbacks.py`
si attiva prima che la request parta verso ChatGPT e fa questa trasformazione:

```
PRIMA                                    DOPO
─────────────────────────────────────    ────────────────────────────────────
request.system  (top-level)         ┐    request.instructions = <tutto il
request.messages[role:system] ...   ┘ →    contesto system unificato>
request.messages = [user, system,        request.messages = [user, assistant,
                    assistant, ...]                          ...]  ← solo questi
```

ChatGPT accetta `instructions` come campo nativo per il contesto di sistema. Con questo fix
recall Hindsight, skill-eval e qualsiasi altro `additionalContext` degli hook arrivano
correttamente al modello.

> **Dettaglio:** nel pre-call hook il campo `model` è ancora l'**alias** LiteLLM
> (es. `claude-gpt-5-5`), non il nome reale (`chatgpt/gpt-5.5`), perché il routing avviene
> dopo. Il match nella callback copre entrambi i prefissi: `claude-gpt-` e `chatgpt/`.

**Versioning e deploy automatico di `callbacks.py`.** La sorgente è versionata in questo
repo come `scripts/litellm-callbacks.py`. Il file che LiteLLM carica effettivamente è la
copia in `~/.litellm/callbacks.py` (o `$LITELLM_CONFIG_DIR/callbacks.py`).

Per non dover copiare manualmente dopo ogni modifica, il repo usa **git hook versionati**
in `.githooks/`:

| File | Scopo |
|---|---|
| `.githooks/post-commit` | si attiva dopo ogni `git commit` |
| `.githooks/post-merge` | si attiva dopo `git merge` / `git pull` |
| `.githooks/lib/litellm-deploy-common.sh` | logica condivisa: controlla se `scripts/litellm-callbacks.py` è tra i file cambiati; se sì chiama `scripts/deploy-litellm-callback.sh` |
| `scripts/deploy-litellm-callback.sh` | copia la sorgente in `$LITELLM_CONFIG_DIR` (default `~/.litellm/`) e avvisa di riavviare il proxy |

Gli hook si attivano **solo se `scripts/litellm-callbacks.py` è tra i file modificati**,
quindi non c'è overhead su commit normali.

> **Nota path:** gli hook usano il git MSYS2 (`/usr/bin/git`) dove `$HOME` punta a
> `E:\msys64\home\Sphynx`. Con Git-for-Windows `$HOME` sarebbe `C:\Users\EN27553` e il
> deploy finirebbe nel posto sbagliato.

Per attivare gli hook nel clone locale (operazione una tantum):

```bash
git -C "$TRINITY_PLUGIN_DIR" config core.hooksPath .githooks
```

Verifica che sia già impostato:

```bash
git -C "$TRINITY_PLUGIN_DIR" config core.hooksPath
# deve rispondere: .githooks
```

**Variabili d'ambiente comuni nei launcher:**

```bash
ANTHROPIC_BASE_URL="http://127.0.0.1:4000"
ANTHROPIC_AUTH_TOKEN="$LITELLM_MASTER_KEY"          # Bearer richiesto dalla discovery /v1/models
CLAUDE_CODE_ENABLE_GATEWAY_MODEL_DISCOVERY=1        # attiva il picker /model per i modelli gateway
```

> **Gotcha:** Claude Code filtra la discovery mostrando solo modelli il cui id inizia con `claude`
> o `anthropic`. Gli alias LiteLLM devono rispettare questo prefisso (es.
> `claude-deepseek-v4-pro-thinking`, `claude-gpt-5-5-high`) altrimenti non compaiono nel picker
> `/model`. Il nome upstream nel backend può essere qualsiasi (es. `deepseek/deepseek-v4-pro`).

**Gestione dell'effort.** Claude Code invia l'effort via `/effort` nel campo
`request.output_config.effort`, che LiteLLM diretto non mappa automaticamente. Soluzione: un
alias per tier di reasoning per ciascun provider, ognuno con `reasoning_effort` fisso nel
`litellm_config.yaml`, e le variabili `ANTHROPIC_DEFAULT_SONNET/OPUS/HAIKU_MODEL` nel launcher
per mappare i tier di Claude Code ai modelli giusti (`switchModelsOnFlag: true`).

DeepSeek non supporta livelli graduati di effort (solo thinking on/off): due modelli distinti —
`claude-deepseek-v4-pro` (no thinking) e `claude-deepseek-v4-pro-thinking` (thinking abilitato).

---

### 13.2 claude-code-router (CCR)

CCR (`@musistudio/claude-code-router`, comando `ccr`) è un proxy con pipeline di **transformer**
che converte le richieste Claude Code nel formato di ciascun provider. Il fork usato è
`ichelema/claude-code-router` (upstream: `musistudio/claude-code-router`), con patch custom
mantenute nel branch `trinity-patches`.

**Path di configurazione.** Su Windows, `os.homedir()` di Node.js segue `USERPROFILE`
(non `HOME`). Su questa macchina `USERPROFILE` è dirottato alla chiavetta
(`E:\msys64\home\Sphynx`) dal launcher WezTerm e dall'alias `claude`, quindi `os.homedir()`
cade già sulla home MSYS: il config vive in `~/.claude-code-router`
(= `E:\msys64\home\Sphynx\.claude-code-router`). Nessuna junction necessaria — quella
storica `C:\Users\EN27553\.claude-code-router` (target morto `C:\msys64\...`) è stata rimossa.

**File persistenti** (sopravvivono agli aggiornamenti npm, non vanno persi):

| File | Ruolo |
|---|---|
| `~/.claude-code-router/config.json` | routing + ordine transformer per provider |
| `~/.claude-code-router/transformers/skill-rehydrate.js` | skill/Hindsight per provider non-Anthropic |
| `~/.claude-code-router/transformers/effort-transformer.js` | mappa `output_config.effort` → `reasoning.effort` per GPT |

**Transformer chain per provider** (ordine critico — alcuni transformer distruggono `request.messages`):

| Provider | Transformer (in ordine) | Note |
|---|---|---|
| `deepseek` | `deepseek → enhancetool → skill-rehydrate` | skill-rehydrate può stare in fondo: deepseek/enhancetool non toccano messages |
| `openai` | `effort-from-outputconfig → skill-rehydrate → openai-responses` | skill-rehydrate deve precedere openai-responses (che cancella request.messages) |
| `gemini` | `skill-rehydrate → gemini` | skill-rehydrate deve precedere gemini (che restituisce `{body,config}` senza messages) |
| `anthropic` | — | nessun transformer personalizzato |

**skill-rehydrate.js** — perché esiste. Gli hook `UserPromptSubmit` (skill-eval, hindsight-recall)
consegnano il loro `additionalContext` via messaggi `role:system` inline, che il transformer
Anthropic di CCR scartava silenziosamente. Fix a due livelli:

1. **Patch core** (`anthropic.transformer.ts`): rifonde i messaggi `role:system` inline
   nell'ultimo messaggio `user`, avvolti in `<injected-system-context>`.
2. **Transformer esterno** (`skill-rehydrate.js`): per provider non-Anthropic (che non hanno il
   tool meta `Skill`), riscrive l'istruzione `"Invoke the Skill tool"` in `"read the matched
   SKILL.md with the Read tool"`, iniettando `<skill-instructions>` direttamente. Dedup via
   ispezione della history `tool_calls` (self-healing sui compact).

**Patch core — build e deploy.** Le patch si trovano nel branch `trinity-patches` del clone
locale (`/c/Download/claude-code-router`). Dopo ogni reinstall dal registry npm vanno
riapplicate:

```bash
# 1. ferma ccr (file lock su Windows)
# 2. rebuild (node MSYS2 fa crashare tsc — usare il node di mise)
mise exec node@24.16.0 -- pnpm build:core && pnpm build:cli   # NO build:ui

# 3. copia il bundle
cp dist/cli.js \
  ~/.local/share/mise/installs/node/24.16.0/node_modules/@musistudio/claude-code-router/dist/cli.js
```

Il bundle originale va tenuto come `.bak` per rollback rapido. Le patch includono 3 commit:
`anthropic system-inline merge`, `deepseek reasoning_content roundtrip`,
`openai reasoning_effort mapping`.

> **Gotcha chiave:** CCR è installato nel node di mise — un bump della versione Node lo fa
> sparire e richiede reinstallazione. Le API key devono essere nelle env var al momento
> dell'avvio del processo `ccr`; un `export KEY=... && ccr code` non aggiorna le chiavi se il
> server è già in esecuzione.

**Skill correlata:** `/trinity:ccr_model` mostra i modelli configurati in `config.json` con le
route attuali (utile per debug del routing).

---

## Struttura del repo

```
Trinity/
├── core-behavior.md         comportamento iniettato al SessionStart
├── .mcp.json                server MCP (playwright, notebooklm, ticktick; excalidraw/obsidian off — hindsight a scope user, §7)
├── mise.toml                env + task (servizio Hindsight, dashboard, benchmark, check)
├── commands/                slash command (/trinity:*)
├── config/
│   └── claude/              settings.shared.json + overlay per OS → genera ~/.claude/settings.json (mise run sync-settings, §10)
├── vendor/                  plugin terzi vendorizzati: ui-craft · claude-bionify (junction/symlink in ~/.claude/skills/, §8)
├── skills/                  14 skill attive (+ excel-data-analyst disabilitata)
├── hooks/
│   ├── hooks.json           registrazione hook (sostituisce "hooks" di settings.json)
│   ├── skill-eval.*         suggerimento skill
│   ├── windows-toast.sh     toast Windows (entry point hook → chiama il .ps1)
│   ├── windows-toast.ps1    toast Windows (PowerShell, invocato da .sh)
│   └── hindsight/           recall, retain, ensure-up, shutdown, lib, mcp (shim per-progetto), ops, tools
│       ├── benchmark/       benchmark embedding/reranker/recall (sviluppo)
│       └── hindsight-dashboard/  dashboard log Roda/Puma :9292 (sviluppo)
├── scripts/                 script di servizio: setup/ (bootstrap-linux.sh, sync-claude-settings.py) · bin/adhd · deploy litellm
├── scheduler/               6 job Windows schedulati: api-check · cp-check · promote-scan · nb-auth-refresh · nb-check · yt-check
└── sound/                   notifiche audio
```
