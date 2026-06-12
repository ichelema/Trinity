# Trinity Plugin

Il **core dell'agente Trinity** come plugin Claude Code: memoria persistente Hindsight, comportamento 
condiviso, skill, comandi e hook di notifica. Installato a livello utente, è attivo in **ogni** 
progetto della macchina, che ne eredita comportamento e memoria.

> Repo unico: `D:\AI\Claude\Trinity` (dal 2026-06-12 include anche gli ex strumenti di laboratorio).

---

## 1. Architettura: repo unico

```
D:\AI\Claude\Trinity\   ← il core dell'agente: plugin distribuibile + strumenti di sviluppo
```

| Parte | Ruolo |
|---|---|
| **Runtime del plugin** | ciò che i progetti ereditano: hook, skill, comandi, `core-behavior.md`, `mise.toml` di servizio, `.mcp.json`, marketplace |
| **Strumenti di sviluppo** | servono alla manutenzione di Trinity, non ai progetti: benchmark (`hooks/hindsight/benchmark/`), dashboard log (`hooks/hindsight/hindsight-dashboard/`), check aggiornamenti (`scheduler/`) |

La env var **`TRINITY_PLUGIN_DIR`** (definita nell'env utente, vedi §8) punta alla root di 
questo repo: la usano i comandi documentati nelle skill e, come override opzionale, gli script — 
che altrimenti risolvono i path relativamente a sé stessi.

### Cosa è plugin e cosa è ambiente

I **file** del plugin vivono tutti qui dentro. Le **risorse runtime** restano sulla macchina: il 
server Hindsight (`localhost:8888`), il Postgres embedded, i binari (`mise`, `node`, `ffplay`, `pwsh`), 
il CA bundle (`C:/certs/cacert.pem`), le chiavi API (env utente). 
Il plugin è il *cervello*; server, DB e runtime sono il *corpo* installato sul sistema.

---

## 2. Come viene caricato il plugin

Il plugin **non è legato a un progetto**: è abilitato a livello utente, quindi si carica in automatico ovunque apri Claude Code. L'interruttore è in `~/.claude/settings.json`:

```json
"enabledPlugins": { "trinity@trinity-marketplace": true }
```

Sequenza all'avvio, in qualsiasi cartella:

```
1. ~/.claude/settings.json      → enabledPlugins: trinity = true   → "caricalo"
2. ~/.claude/plugins/installed_plugins.json → appartiene a trinity-marketplace
3. ~/.claude/plugins/known_marketplaces.json → directory D:\AI\Claude\Trinity
4. Carica da lì: hooks/, skills/, commands/, .mcp.json, core-behavior.md
```

**Distribuzione** (marketplace locale, già configurato):

```bash
claude plugin marketplace add D:/AI/Claude/Trinity
claude plugin install trinity@trinity-marketplace
```

**Disattivarlo in un singolo progetto** (i settings di progetto vincono su quelli utente):

```json
// .claude/settings.json del progetto
"enabledPlugins": { "trinity@trinity-marketplace": false }
```

**Aggiornare la copia installata** — l'updater confronta la `version` del manifest, non i commit, 
quindi serve il bump:

```bash
# 1. bump "version" in .claude-plugin/plugin.json
# 2.
claude plugin update trinity@trinity-marketplace
```

**Sviluppo senza installare:**

```bash
claude --plugin-dir D:/AI/Claude/Trinity
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

| Evento | Comandi |
|---|---|
| `UserPromptSubmit` | skill-eval (suggerisce skill) · Hindsight **recall** |
| `PreToolUse` | notifica permessi · auto-allow di `git commit` |
| `SessionStart` | avvia server Hindsight · **inietta `core-behavior.md`** · inietta mental model |
| `Stop` | suono di fine · Hindsight **retain** (async) |
| `SessionEnd` | shutdown servizi Hindsight |
| `Notification` | suono + toast Windows sul prompt permessi |

Esempio — un hook del plugin (da `hooks/hooks.json`):

```json
{
  "type": "command",
  "command": "${CLAUDE_PLUGIN_ROOT}/hooks/hindsight/hindsight-recall.sh",
  "timeout": 10
}
```

Gli script `.sh`/`.py` referenziati stanno in `hooks/` e `hooks/hindsight/`; risolvono i propri fratelli 
relativamente alla loro posizione, quindi il plugin è rilocabile.

---

## 4. Iniezione di `core-behavior.md`

`core-behavior.md` (root del plugin) contiene il **comportamento universale** dell'agente: principi, 
"prima la semplicità", modifiche chirurgiche, regole operative shell/path, Nushell, linguaggi. 
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
- I path che cambiano per macchina **non** sono nel file: vengono da variabili d'ambiente (vedi §8).

---

## 5. Skill incluse

In `skills/`, attivate per rilevanza dall'hook skill-eval o a richiesta:

| Skill | Uso |
|---|---|
| `hindsight` | memoria persistente (retain/recall/reflect), banchi |
| `obsidian` / `obsidian-cli` | vault Obsidian: note, Dataview, canvas / operazioni via CLI |
| `mise` | gestione runtime, env e task |
| `nushell` | pipeline su dati strutturati |
| `ruby` | gem per analisi dati in Ruby |
| `excel-data-analyst` | analisi e grafici da file Excel (Python) |
| `excalidraw-skill` | creazione/refine di diagrammi su canvas live |
| `double-commander-docs` | ricerca nella doc locale di Double Commander |
| `book-to-skill` | converte libri/documenti in skill strutturate |

---

## 6. Comandi inclusi

In `commands/`, invocabili come slash command **namespaced** (`/trinity:<nome>`), così non 
collidono con i comandi locali del progetto:

| Comando | Funzione |
|---|---|
| `/trinity:reflect` | riflessione strategica sulla memoria Hindsight del progetto |
| `/trinity:hindsight-create-agent` | crea un subagent con memoria Hindsight isolata per namespace tag |
| `/trinity:audit-plugin-nvim` | audit di un plugin Neovim (report, fix guidati, commit) |

---

## 7. Memoria Hindsight (multi-bank: core + bank per progetto)

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
  "recall_banks": ["auto", "core"]
}
```

- **`retain_bank`** (scalare, la scrittura ha un bersaglio): `auto` = slug del repo corrente
  (nome dal remote `origin`, fallback basename; fuori da git — o dentro il repo del plugin
  stesso — ricade sul core); `core` = il core; altro valore = nome bank letterale. Il bank si
  **auto-crea al primo retain**, zero provisioning.
- **`recall_banks`** (array, la lettura aggrega): fan-out **parallelo** sui bank risolti,
  unione dei candidati e **rerank globale zerank-2** via REST ZeroEntropy (gli score di bank
  diversi non sono confrontabili tra loro; se ZeroEntropy non risponde, fallback a
  interleaving senza rerank). Il core entra **solo se listato**: `["auto"]` da solo = progetto
  totalmente isolato. Con un solo bank risolto il percorso è identico al single-bank storico.
- **Retrocompat**: un `api_url` esplicito in un override (file o env) vince sul blocco bank e
  ripristina il comportamento single-bank. I tag (`claude-code`, `repo:`, `branch:`) restano
  invariati.

Per vedere su quali bank si risolve il progetto corrente (debug):

```bash
python hooks/hindsight/lib/hindsight_config.py --banks   # URL retain + recall risolti
```

**Ricette rapide** (override nel `hindsight.config.json` del progetto):

| Voglio… | Override |
|---|---|
| comportamento di default: scrive sul bank del progetto, legge progetto+core | nessuno (eredita il plugin) |
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

---

## 8. Setup per-macchina (valori machine-specific)

Il plugin non contiene path hardcoded: i valori che cambiano da macchina a macchina vengono 
da **variabili d'ambiente**. Su un nuovo PC, definiscile una volta in `~/.claude/settings.json` 
(env utente, non versionata col plugin):

```json
{
  "env": {
    "OBSIDIAN_VAULT": "D:/Obsidian/Sinapsi",
    "OBSIDIAN_VAULT_NAME": "Sinapsi",
    "TRINITY_PLUGIN_DIR": "D:/AI/Claude/Trinity"
  }
}
```

Su un'altra macchina con lo stesso vault sincronizzato in un path diverso, basta cambiare il 
valore (es. `"/home/sphynx/Obsidian/Sinapsi"`): `core-behavior.md` resta identico, l'iniezione 
lo espande con i valori locali. La versione MSYS del path si ricava con `cygpath -u`, non serve 
una variabile separata.

| Cosa | Come è risolto |
|---|---|
| root del progetto | `${CLAUDE_PROJECT_DIR}` (gli hook la ricevono da Claude Code) — già automatico |
| root del plugin | `${CLAUDE_PLUGIN_ROOT}` — già automatico |
| vault Obsidian | `${OBSIDIAN_VAULT}` / `${OBSIDIAN_VAULT_NAME}` — **da definire per-macchina** |
| root di questo repo | `${TRINITY_PLUGIN_DIR}` (per i comandi delle skill) — **da definire per-macchina** |

> Dipendenza: l'espansione usa `envsubst` (pacchetto `gettext`, presente di default su MSYS2/Linux/Mac). 
> Se manca, lo script ricade su `sed`. Se le env non sono impostate, il testo iniettato mostra un 
> avviso esplicito anziché un valore vuoto.

---

## Struttura del repo

```
Trinity/
├── .claude-plugin/
│   ├── plugin.json          manifest (name, version)
│   └── marketplace.json     marketplace (source ".")
├── core-behavior.md         comportamento iniettato al SessionStart
├── .mcp.json                server MCP Hindsight
├── mise.toml                env + task (servizio Hindsight, dashboard, benchmark, check)
├── commands/                slash command (/trinity:*)
├── skills/                  10 skill
├── hooks/
│   ├── hooks.json           registrazione hook (sostituisce "hooks" di settings.json)
│   ├── skill-eval.*         suggerimento skill
│   ├── pretool-notify.sh    notifica permessi
│   ├── windows-toast.ps1    toast Windows
│   └── hindsight/           recall, retain, ensure-up, shutdown, lib, ops, tools
│       ├── benchmark/       benchmark embedding/reranker/recall (sviluppo)
│       └── hindsight-dashboard/  dashboard log Roda/Puma :9292 (sviluppo)
├── scheduler/               check aggiornamenti via Task Scheduler (api-check, cp-check)
└── sound/                   notifiche audio
```
