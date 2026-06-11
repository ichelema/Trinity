# Trinity Plugin

Il **core dell'agente Trinity** come plugin Claude Code: memoria persistente Hindsight, comportamento condiviso, skill, comandi e hook di notifica. Installato a livello utente, è attivo in **ogni** progetto della macchina, che ne eredita comportamento e memoria.

> Versione: `0.1.1` · Repo prodotto, separato dal laboratorio (`D:\AI\Claude\Trinity`).

---

## 1. Architettura: due repo sorelle

```
D:\AI\Claude\Trinity-plugin\   ← PRODOTTO (questo repo): il plugin distribuibile
D:\AI\Claude\Trinity\          ← LABORATORIO: benchmark, dashboard, scheduler, memoria
```

| Repo | Ruolo |
|---|---|
| **Trinity-plugin** | ciò che installi e che gira in produzione: hook, skill, comandi, `core-behavior.md`, `mise.toml` di servizio, `.mcp.json`, marketplace |
| **Trinity** | dove si sviluppa e si testa il plugin (benchmark del recall, check aggiornamenti) |

Il laboratorio raggiunge il plugin tramite la env var **`TRINITY_PLUGIN_DIR`** (default `D:/AI/Claude/Trinity-plugin`), così i due repo restano indipendenti ma comunicanti.

### Cosa è plugin e cosa è ambiente

I **file** del plugin vivono tutti qui dentro. Le **risorse runtime** restano sulla macchina: il server Hindsight (`localhost:8888`), il Postgres embedded, i binari (`mise`, `node`, `ffplay`, `pwsh`), il CA bundle (`C:/certs/cacert.pem`), le chiavi API (env utente). Il plugin è il *cervello*; server, DB e runtime sono il *corpo* installato sul sistema.

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
3. ~/.claude/plugins/known_marketplaces.json → directory D:\AI\Claude\Trinity-plugin
4. Carica da lì: hooks/, skills/, commands/, .mcp.json, core-behavior.md
```

**Distribuzione** (marketplace locale, già configurato):

```bash
claude plugin marketplace add D:/AI/Claude/Trinity-plugin
claude plugin install trinity@trinity-marketplace
```

**Disattivarlo in un singolo progetto** (i settings di progetto vincono su quelli utente):

```json
// .claude/settings.json del progetto
"enabledPlugins": { "trinity@trinity-marketplace": false }
```

**Aggiornare la copia installata** — l'updater confronta la `version` del manifest, non i commit, quindi serve il bump:

```bash
# 1. bump "version" in .claude-plugin/plugin.json
# 2.
claude plugin update trinity@trinity-marketplace
```

**Sviluppo senza installare:**

```bash
claude --plugin-dir D:/AI/Claude/Trinity-plugin
```

---

## 3. Hook: come vengono caricati

Gli hook non stanno in `settings.json`: vivono nel file dedicato **`hooks/hooks.json`**, che Claude Code cerca per convenzione in `<plugin>/hooks/hooks.json`. Il formato è identico alla sezione `"hooks"` di `settings.json`; cambia solo la variabile di path: **`${CLAUDE_PLUGIN_ROOT}`** al posto di `${CLAUDE_PROJECT_DIR}`.

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

Gli script `.sh`/`.py` referenziati stanno in `hooks/` e `hooks/hindsight/`; risolvono i propri fratelli relativamente alla loro posizione, quindi il plugin è rilocabile.

---

## 4. Iniezione di `core-behavior.md`

`core-behavior.md` (root del plugin) contiene il **comportamento universale** dell'agente: principi, "prima la semplicità", modifiche chirurgiche, regole operative shell/path, Nushell, linguaggi. Non è un file di sistema speciale: viene iniettato come **contesto** a ogni sessione da un hook `SessionStart` che lo stampa, e il suo stdout entra nel contesto del modello.

```json
// hooks/hooks.json → SessionStart
{
  "type": "command",
  "command": "/usr/bin/bash -c \"cat \\\"$(cygpath -u \\\"${CLAUDE_PLUGIN_ROOT}\\\")/core-behavior.md\\\"\"",
  "timeout": 5
}
```

Conseguenze pratiche:

- Vale in **ogni** progetto col plugin attivo, senza bisogno di un `CLAUDE.md`.
- Il `CLAUDE.md` locale di un progetto ha **precedenza** in caso di conflitto (è più specifico).
- Per modificare il comportamento dell'agente si edita **questo file**, non i singoli progetti.

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

In `commands/`, invocabili come slash command **namespaced** (`/trinity:<nome>`), così non collidono con i comandi locali del progetto:

| Comando | Funzione |
|---|---|
| `/trinity:reflect` | riflessione strategica sulla memoria Hindsight del progetto |
| `/trinity:hindsight-create-agent` | crea un subagent con memoria Hindsight isolata per namespace tag |
| `/trinity:audit-plugin-nvim` | audit di un plugin Neovim (report, fix guidati, commit) |

---

## 7. Memoria Hindsight (multi-progetto)

`.mcp.json` registra il server Hindsight su un **bank unico condiviso** (`trinity-project`); le memorie sono ricondivise tra progetti via tag `claude-code`, e ogni fatto viene marcato col tag `repo:<nome-progetto>` derivato dalla directory. Quindi un fatto utile imparato in un progetto è richiamabile dagli altri.

La configurazione del servizio (provider LLM/embedding, env TLS, task `start/stop-hindsight`, `control-plane`) è in **`mise.toml`**, usato dagli hook via `mise -C <plugin_root> run <task>`. È la fonte di verità del runtime Hindsight.

---

## Struttura del repo

```
Trinity-plugin/
├── .claude-plugin/
│   ├── plugin.json          manifest (name, version)
│   └── marketplace.json     marketplace (source ".")
├── core-behavior.md         comportamento iniettato al SessionStart
├── .mcp.json                server MCP Hindsight
├── mise.toml                env + task di servizio Hindsight
├── commands/                slash command (/trinity:*)
├── skills/                  10 skill
├── hooks/
│   ├── hooks.json           registrazione hook (sostituisce "hooks" di settings.json)
│   ├── skill-eval.*         suggerimento skill
│   ├── pretool-notify.sh    notifica permessi
│   ├── windows-toast.ps1    toast Windows
│   └── hindsight/           recall, retain, ensure-up, shutdown, lib, ops, tools
└── sound/                   notifiche audio
```
