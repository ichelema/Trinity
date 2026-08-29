---
name: hindsight
description: Hindsight persistent memory system for AI agents. Use when working with retain/recall/reflect operations, memory banks. In questo progetto Hindsight gira come MCP server locale — vedi "Setup attivo in questo progetto" sotto per le operazioni quotidiane.
---

# Hindsight Memory System

Hindsight è un sistema di memoria persistente per agenti AI che implementa operazioni **retain / recall / reflect**.

Hai una memoria persistente attraverso il server MCP Hindsight.

Utilizza direttamente le chiamate agli strumenti MCP. Non utilizzare comandi shell, non eseguire `uvx hindsight-embed` e non chiamare `hindsight-embed memory`.

Endpoint:

```text
http://localhost:8888/mcp/trinity-project/
```

## Setup attivo in questo progetto

In `E:\AI\Claude\Trinity` Hindsight è installato come **MCP server locale**.

**Stack:**

- Pacchetto Python: `hindsight-api-slim[embedded-db]` (installato via `mise run install-hindsight`; NON il meta-pacchetto `hindsight-api`, alias di `[all]` che tira giù i modelli locali/PyTorch)
- Entry-point: `hindsight-local-mcp` (in `Scripts/` del Python gestito da mise — esposto nel PATH via `[env]` di `.mise.toml`)
- Versione: **0.9.2** (dal 2026-08-29; 0.9.1 dal 2026-08-15); query-analyzer del recall ristretto a `it,en` (`HINDSIGHT_API_QUERY_ANALYZER_LANGUAGES`)
- LLM: **`gpt-5.6-luna`** via provider `openai-responses` per retain/reflect/consolidation (A/B 2026-08-09, ICH-60/62); **`gpt-4.1-mini`** resta LLM globale per il query-analyzer del recall (chiavi da `$OPENAI_API_KEY`; vedi commenti in `mise.toml`)
- Embeddings: **Google `gemini-embedding-001`** (1536d, cloud, multilingue; `$GEMINI_API_KEY`)
- Reranker: **`voyage/rerank-2.5`** via `litellm-sdk` (`$VOYAGE_API_KEY`), cap flat 100 candidati (per-budget spento). **Failover chain fail-open** (ICH-65): `HINDSIGHT_API_RERANKER_1_PROVIDER = "rrf"` — se Voyage non risponde il recall ripiega su RRF invece di dare HTTP 500; la degradazione è segnalata da `hindsight-failcheck.sh` (marker scritto da `hindsight-recall.sh` quando i risultati arrivano senza `scores.reranker`)
- Altre feature 0.9.0 attive: recency decay esponenziale (halflife 60 giorni), audit log server-side (retention 30 giorni), `HINDSIGHT_API_FAIL_ON_EXTRACTION_ERRORS=true` (estrazione fallita dopo i retry → operation `failed`, intercettata da `hindsight-failcheck.sh`)
- Storage: embedded PostgreSQL in `~/.pg0/hindsight-mcp/`
- Endpoint MCP: `http://localhost:8888/mcp/trinity-project/` (bank statico per-progetto)
- Registrato a **scope user** come shim stdio `hooks/hindsight/mcp/hindsight-mcp-shim.sh` (bank risolto per-progetto; vedi sotto)
- **Avvio / stop del server:**

```bash
mise run start-hindsight   # lancia in background, log in /tmp/hs.log
mise run stop-hindsight    # Windows: taskkill | Linux: pkill (branch per-OS in ops/hindsight-stop-services.sh)
```

Verifica veloce che il server risponda:

```bash
curl -fsS -m 3 http://localhost:8888/ -o /dev/null -w "%{http_code}\n"  # 404 = up
```

### Multi-bank: core + bank per progetto

Dal 2026-06-12 la memoria è a due livelli: il bank **CORE** `trinity-project`
(informazioni trasversali) + un **bank per progetto** isolato, governati dal
blocco `bank` di `hindsight.config.json`:

- `retain_bank: "auto"` → il retain automatico scrive sul bank del progetto
  corrente (slug dal remote `origin`, fallback basename; fuori da git o nel
  repo Trinity stesso → core). Il bank si auto-crea al primo retain.
- `recall_banks: ["auto", "core"]` → il recall fa fan-out parallelo su
  progetto+core e fonde i risultati con un rerank globale voyage/rerank-2.5
  (fallback interleaving se Voyage non risponde). Il core entra solo se listato.
- URL risolti per il cwd corrente: `python hooks/hindsight/lib/hindsight_config.py --banks`

**Tool MCP `hindsight/*` — quale bank vedono** (dal 2026-07-10, MCP per-progetto):
il server "hindsight" è definito SOLO a scope user (`claude mcp add-json
hindsight --scope user`) come shim stdio
`hooks/hindsight/mcp/hindsight-mcp-shim.sh`, unico per tutti i progetti (una
seconda definizione nel `.mcp.json` di Trinity causava il warning "Conflicting
scopes" ed è stata rimossa). Lo shim risolve il bank con la stessa
`resolve_bank` degli hook (slug dal remote origin via `CLAUDE_PROJECT_DIR`;
repo Trinity o fuori-git → core `trinity-project`), attende la readiness del
server e fa da ponte via `mcp-remote` sul node di mise.

I tool MCP parlano comunque con UN solo bank per sessione: il fan-out
progetto+core (`recall_banks: ["auto", "core"]`) resta esclusivo degli hook
REST. Per accedere a un bank arbitrario usa l'API REST
(`http://127.0.0.1:8888/v1/default/banks/<nome>/...`).

**Promozione progetto → core**: comando `/trinity:promote` (curata, mai
automatica: scan → triage gpt-4.1-nano → review umana → move con strip dei tag
`repo:`/`branch:`). Meccanica in `hooks/hindsight/ops/hindsight-promote.py`
(`--scan/--triage/--move/--reject/--status`); job settimanale
`scheduler/promote_scan/` che genera `logs/promote-candidates.json`.

### Mental model: knowledge page iniettate a inizio sessione

Tre mental model definiti nel blocco `mental_models` di `hindsight.config.json` —
`user-profile`, `project-conventions`, `recurring-learnings` — vengono iniettati
come `additionalContext` a ogni SessionStart dall'hook `hindsight-mm-inject.sh`
(gated da `mental_models_inject_on_start: true`, ids in `mental_models_inject_ids`).

- **refresh** rigenera il contenuto dal bank; **inject** mostra solo il contenuto già esistente.
- Refresh manuale immediato (necessario dopo aver cancellato/corretto un fatto):
  `bash hooks/hindsight/ops/hindsight-mental-models.sh refresh --all`

### Hook di sessione e strumenti operativi

| Componente | Trigger/uso | Cosa fa |
| ---------- | ----------- | ------- |
| `hindsight-ensure-up.sh` | SessionStart | Avvia il server se giù e attende la readiness dell'endpoint MCP (elimina la race "tool `hindsight/*` non registrati") |
| `hindsight-mm-inject.sh` | SessionStart | Inietta i mental model (vedi sopra) |
| `hindsight-failcheck.sh` | UserPromptSubmit | Segnala operation async `failed` lato server (retain accettato ma estrazione fallita) e la degradazione del reranker; de-dup via state file |
| `hindsight-sentinel.sh` | detached da ensure-up | Sostituisce l'hook SessionEnd (che Claude Code cancella, issue #32712): quando l'ultimo processo claude termina drena la coda del retain (`hindsight-retain-worker.py --drain`: valuta le entry accodate dagli Stop non ancora consumate, force e senza domande), attende i retain in volo e spegne server + Postgres |
| `ops/hindsight-drain-retain.py` | pre-stop | Attende che i retain in volo raggiungano stato terminale prima dello shutdown (mediana estrazione 32s: uno stop cieco perderebbe la memoria senza errori) |
| `mise run db-dump` / `db-restore` | manuale | `pg_dump`/restore del DB Hindsight per il sync tra macchine (`tools/hs-db-dump.sh`, `hs-db-restore.sh` con guardrail anti-perdita) |
| `tools/hindsight_export.py` / `hindsight_import.py` | cambio provider embedding | Export dei documenti → re-retain sul nuovo embedding (il cambio di dimensione obbliga al rebuild del bank) |
| `mise run api-check` / `cp-check` | scheduler | Segnalano nuove release di `hindsight-api(-slim)` su PyPI e del Control Plane su npm (exit 10 se disponibili; cp-check usa lo state file `cp-last-seen.state`) |

### Interfaccia web: Control Plane

Una UI **opzionale**, indipendente dal server MCP, via task mise e **in foreground** (Ctrl-C per fermarla, a differenza di `start-hindsight` che è daemon):

| UI                                             | Porta | Avvio                    | Stop                          | A cosa serve                                                                                                    |
| ---------------------------------------------- | ----- | ------------------------ | ----------------------------- | --------------------------------------------------------------------------------------------------------------- |
| **Control Plane** (Web UI ufficiale Hindsight) | 9999  | `mise run control-plane` | `mise run stop-control-plane` | Sfogliare bank/agent, entità e relazioni, storico operations, testare query di recall. Si collega all'API :8888 |

```bash
mise run control-plane    # → http://localhost:9999  (bind 127.0.0.1)
```

- **Control Plane**: app Next.js scaricata via `npx @vectorize-io/hindsight-control-plane` (non nel repo). Gira sul **Node gestito da mise** (`[tools] node`), perché l'`npx` del Node MSYS2 (`/ucrt64/bin`) crasha. È legato a `127.0.0.1` (no LAN; non ha API key — `HINDSIGHT_CP_ACCESS_KEY` la protegge se la esponi).
- Stop affidabile via `$TRINITY_PLUGIN_DIR/hooks/hindsight/ops/kill-port.sh <porta>` (su Windows usa `Get-NetTCPConnection` perché il netstat MSYS non vede sempre i processi nativi; su Linux usa `lsof`/`fuser`).
- Per analizzare `hindsight-debug.log` (JSONL) non serve una UI: `nu -c "open logs/hindsight-debug.log | lines | each { from json } | where event == 'recall'"`.

> Dettagli e gotcha d'ambiente (npx MSYS2 rotto, bind `HOSTNAME`): vedi `README.md` §16.

### Operazioni di memoria via MCP

Quando il server è up, in una sessione Claude Code questo progetto espone 29 tool MCP con prefisso `hindsight/`. I tre principali sono:

| Tool                | Quando usarlo                                                                                                                                                                                                  | Esempio di invocazione                                                                                                                          |
| ------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------- |
| `hindsight/retain`  | Memorizzare informazioni nuove (preferenze, decisioni, lezioni). Passa **contesto ricco e crudo**, non frasi pre-digerite: l'LLM estrae meglio i fatti dal testo originale. Asincrono: ritorna `operation_id`. | `retain(content="L'utente Ichelema preferisce Ruby per gli script e usa MSYS2 su Windows 11. Ha appena configurato Hindsight con gpt-5.6-luna.")` |
| `hindsight/recall`  | Recuperare memorie semanticamente rilevanti per una query. Sincrono.                                                                                                                                           | `recall(query="quali preferenze ha Ichelema per gli script?")`                                                                                    |
| `hindsight/reflect` | Sintesi disposition-aware su una domanda usando le memorie come contesto.                                                                                                                                      | `reflect(query="Come dovrei impostare un nuovo script per Ichelema?")`                                                                            |

Tool ausiliari più usati:

- `hindsight/list_memories` — elenca tutte le memorie di un bank (debug)
- `hindsight/get_memory` — recupera una memoria per id
- `hindsight/get_operation` — verifica stato di un retain async (`accepted` → `completed`)
- `hindsight/list_documents` / `get_document` — gruppi di memorie (un retain = un document)
- `hindsight/get_bank` / `update_bank` — gestione bank
- `hindsight/clear_memories` / `delete_bank` — distruttive, chiedere conferma all'utente prima
- `hindsight/delete_document`- Cancella un document

### Come Hindsight processa un retain

1. Il client (Claude Code) chiama `retain(content=...)`
2. Il server accetta sincrono → `{status: "accepted", operation_id: "..."}` e mette in coda
3. Worker async chiama `gpt-5.6-luna` (provider `openai-responses`) per estrarre:
   - **observation facts** (fatti atomici, es. "Ichelema prefers Ruby for scripting")
   - **world facts** (versione timestamped + entity-linked, es. "Ichelema prefers Ruby for scripting | When: 2026-05-23 | Involving: Ichelema")
4. Entrambi i tipi vengono indicizzati con embeddings nel bank `trinity-project`
5. `recall` cerca semanticamente su observation + world, restituisce ranked

### Quando usare retain proattivamente

Alla fine di un task significativo, salva informazioni persistenti e durevoli.

Usa `mcp__hindsight__retain` per memorizzare informazioni utili a lungo termine.

Argomenti:

```json
{
  "content": "L'utente preferisce TypeScript con strict mode",
  "context": "preferenze di linguaggio e stile TypeScript del progetto",
  "tags": ["claude-code", "repo:<nome-repo>"]
}
```

Altri esempi:

```json
{
  "content": "Eseguire i test in questo progetto richiede NODE_ENV=test",
  "context": "esecuzione test e configurazione d'ambiente del progetto",
  "tags": ["claude-code", "repo:<nome-repo>"]
}
```

```json
{
  "content": "La build è fallita usando Node 18, ma funziona con Node 20",
  "context": "build del progetto e compatibilità versioni Node",
  "tags": ["claude-code", "repo:<nome-repo>"]
}
```

Salva:

- decisioni architetturali
- modifiche alle convenzioni
- risultati di debugging non ovvi
- vincoli specifici del progetto
- preferenze utente
- lavoro irrisolto o follow-up futuri

Non salvare:

- API key
- password
- token
- segreti
- dati personali sensibili senza richiesta esplicita
- log rumorosi
- stack trace completi salvo root cause importanti

**Non** memorizzare:

- Cose già nel codice o nel git history
- Stato effimero della sessione corrente
- Documentazione duplicata (es. CLAUDE.md è già caricato)

### Quando usare recall proattivamente

All’inizio di un nuovo task, dopo un reset del contesto, oppure quando l’utente fa riferimento a lavoro precedente, usa Hindsight recall.

Utilizza `mcp__hindsight__recall` prima di iniziare il lavoro per recuperare il contesto pertinente.

Argomenti:

```json
{
  "query": "preferenze dell'utente e procedure di progetto pertinenti a questo compito",
  "budget": "high",
  "tags": ["claude-code"]
}
```

Altri esempi:

```json
{
  "query": "preferenze dell'utente per questo progetto",
  "budget": "high",
  "tags": ["claude-code"]
}
```

```json
{
  "query": "problemi precedenti, soluzioni alternative e procedure per questo repository",
  "budget": "high",
  "tags": ["claude-code", "repo:<nome-repo>"],
  "tags_match": "any"
}
```

> I tag nel bank reale sono SOLO quelli universali (`claude-code`, `repo:<nome>`, `branch:<nome>`): filtrare per tag semantici come `project` o `preferences` non matcherebbe nulla. La selettività la fa la **query semantica**, non il filtro tag.

Usa recall per recuperare:

- convenzioni del progetto
- decisioni architetturali precedenti
- bug ricorrenti
- preferenze utente
- TODO irrisolti
- vincoli implementativi

Considera la memoria richiamata come contesto consultivo, non come fonte di verità assoluta. Verifica sempre i fatti mutabili direttamente nel repository.

# Quando usare reflect proattivamente

Utilizza `mcp__hindsight__reflect` quando è necessaria una sintesi o un giudizio, non solo il recupero di informazioni.

Argomenti:

```json
{
  "query": "Come dovrei approcciare questo compito basandomi sulle esperienze dei progetti passati?",
  "context": "Prima di prendere decisioni implementative, sintetizza le preferenze pertinenti, le procedure e i fallimenti precedenti.",
  "budget": "mid",
  "tags": ["claude-code"]
}
```

Usa reflect solo quando serve sintesi o ragionamento strategico, ad esempio:

- tradeoff architetturali
- pattern ricorrenti
- “basandoti sul lavoro precedente”
- “cosa dovremmo fare adesso”
- “perché continuiamo ad avere questo problema”

Impostazioni consigliate per reflect:

```text
budget: mid
max_tokens: 2000
tags: claude-code (eventualmente + repo:<nome> per scoping di progetto)
tags_match: any
```

## IMPORTANTE: Quando Memorizzare le Informazioni

Memorizza sempre le informazioni durature e utili dopo averle apprese.

### Preferenze dell'Utente

- Stile di codifica: indentazione, convenzioni di denominazione, preferenze linguistiche
- Preferenze degli strumenti: gestori di pacchetti, editor, linter, formattatori
- Preferenze di comunicazione
- Convenzioni del progetto
- Preferenze architettoniche

### Risultati delle Procedure

- Passaggi che hanno completato con successo un'attività
- Comandi che hanno funzionato o fallito e perché
- Soluzioni alternative (workaround) scoperte
- Configurazioni che hanno risolto problemi
- Flussi di debug affidabili

### Apprendimenti dalle Attività

- Bug riscontrati e relative soluzioni
- Ottimizzazioni delle prestazioni che hanno funzionato
- Decisioni architettoniche e relative motivazioni
- Requisiti di dipendenza o di versione
- Incompatibilità, casi limite e criticità (gotchas)

## IMPORTANTE: Quando Richiamare le Informazioni

Richiamale sempre prima di:

- Iniziare qualsiasi attività non banale
- Prendere decisioni implementative o architettoniche
- Suggerire strumenti, librerie o flussi di lavoro
- Risolvere problemi (troubleshooting)
- Lavorare su codice, configurazione o infrastruttura precedentemente discussi
- Effettuare il refactoring di codice esistente
- Modificare test, CI, build, deploy o configurazione delle dipendenze

## Il campo `context`: descrittivo, non strutturale

Il `context` del retain entra SOLO nel prompt dell'LLM estrattore come cornice
interpretativa: non partecipa al recall filtering, alle relazioni (= entità) né
allo scope di consolidation (= tag). Verificato sul sorgente di hindsight-api
(`entity_processing.py`, `consolidator.py`) il 2026-05-31.

Conseguenza: una categoria secca ("tooling", "preferences") è il valore meno
utile possibile — non descrive nulla. Usa una **descrizione del dominio del
task**, come fa il gate del retain worker automatico (che produce il `context`
insieme al verdetto):

| ❌ Categoria secca | ✅ Dominio descrittivo                                                               |
| ----------------- | ----------------------------------------------------------------------------------- |
| `tooling`         | `git/github del progetto Trinity: hosting, autenticazione SSH, convenzioni di push` |
| `learnings`       | `compilazione gemme native Ruby su Windows UCRT64 con GCC 16`                       |
| `preferences`     | `preferenze di scripting dell'utente: linguaggi e shell su MSYS2`                   |

Regola pratica: il context deve rispondere a "*in quale dominio l'estrattore
deve interpretare questo testo?*" — max 1 riga, specifica, coi nomi propri.

## Regole di Tagging

I tag hanno DUE lavori: filtro di recall E recinto di consolidation — le
observation si fondono SOLO tra memorie con lo stesso identico set di tag
(`tags_match: all_strict` nel consolidator). Un tag in più non arricchisce:
**frammenta** (esperimento 2026-05-31: tag semantici liberi → 71 partizioni su
72 documenti, consolidation morta).

Usa SOLO i tag universali, identici a quelli del retain worker automatico
(`build_tags()` in `hindsight-retain-worker.py`):

- `claude-code` — sempre (ancora di recall del bank)
- `repo:<nome>` — scoping di progetto (nome dal remote origin, stabile)
- `branch:<nome>` — solo se il fatto è davvero specifico del branch

NON aggiungere tag semantici (`project`, `preferences`, `learning`, linguaggi,
sottosistemi…): la selettività del recall la fa la query semantica; il dominio
lo porta il `context`; le connessioni le fanno le entità estratte. Per un fatto
intenzionalmente globale (valido su tutti i progetti), usa solo `claude-code`.

## Migliori Pratiche

1. Sii specifico: archivia informazioni concrete e attuabili.
2. Includi il contesto: menziona progetti, strumenti, versioni, percorsi o comandi quando pertinenti.
3. Richiama prima di agire: controlla i ricordi prima di fare supposizioni.
4. Archivia i risultati: ricorda cosa ha funzionato e cosa è fallito.
5. Usa tag mirati: preferisci pochi tag utili a molti tag generici.
6. Usa `reflect` solo quando una risposta sintetizzata è migliore di un recupero diretto.
7. Non archiviare segreti, token, password, chiavi private o credenziali sensibili.

## Esempi

Dopo che l'utente corregge una preferenza, chiama `mcp__hindsight__retain`:

```json
{
  "content": "L'utente preferisce pnpm rispetto a npm per la gestione dei pacchetti",
  "context": "preferenze dell'utente per la gestione pacchetti JavaScript",
  "tags": ["claude-code"]
}
```

Dopo aver risolto un bug, chiama `mcp__hindsight__retain`:

```json
{
  "content": "L'errore di idratazione di React è stato risolto spostando l'accesso a localStorage all'interno di useEffect",
  "context": "debugging dell'idratazione React lato client nel progetto frontend",
  "tags": ["claude-code", "repo:<nome-repo>"]
}
```

Dopo aver trovato un comando o una procedura funzionante, chiama `mcp__hindsight__retain`:

```json
{
  "content": "Esegui i test con: pnpm test -- --runInBand per la compatibilità CI",
  "context": "esecuzione test del progetto in CI: comandi e flag funzionanti",
  "tags": ["claude-code", "repo:<nome-repo>"]
}
```

Prima di iniziare il lavoro, chiama `mcp__hindsight__recall`:

```json
{
  "query": "preferenze, procedure, fallimenti precedenti e vincoli noti per questo progetto",
  "budget": "high",
  "tags": ["claude-code", "repo:<nome-repo>"],
  "tags_match": "any"
}
```

Quando devi decidere tra diversi approcci, chiama `mcp__hindsight__reflect`:

```json
{
  "query": "Quale approccio di implementazione corrisponde meglio alle preferenze passate dell'utente e ai vincoli di questo progetto?",
  "context": "Usa i ricordi relativi a preferenze, decisioni precedenti, fallimenti, strumenti e architettura.",
  "budget": "mid",
  "tags": ["claude-code"],
  "tags_match": "any"
}
```

### Troubleshooting rapido

| Sintomo                                                   | Causa probabile                                          | Fix                                                                           |
| --------------------------------------------------------- | -------------------------------------------------------- | ----------------------------------------------------------------------------- |
| Tool `hindsight/*` non visibile in sessione               | Server giù o sessione aperta prima dell'hook di start    | `mise run start-hindsight`, poi nuova sessione Claude Code                    |
| Server crash all'avvio con `UnicodeEncodeError 'charmap'` | `PYTHONUTF8` non esportato                               | Verifica `[env]` di `.mise.toml` (vedi memory `feedback-python-utf8-windows`) |
| `recall` torna vuoto subito dopo un `retain`              | Estrazione fatti ancora in corso, perché è async         | Polla `get_operation(operation_id)` finché `completed`, poi ricalla           |
| `OPENAI_API_KEY not set` nel log del server               | Variabile non esportata nella shell che lancia il server | Verifica con `mise env`                                                       |

## Sicurezza

La memoria non è la source of truth. Repository, file, test, lockfile, configurazioni e documentazione corrente hanno sempre priorità rispetto alla memoria persistente.

## Quale sub-skill caricare

Leggi la sub-skill appropriata in base al contesto:

| Scenario                                                                                   | Sub-skill da leggere                         |
| ------------------------------------------------------------------------------------------ | -------------------------------------------- |
| Progettare l'architettura memory per un'applicazione, pianificare bank config e tag schema | `@references/hindsight-architect/SKILL.md`   |
| Usare Hindsight Cloud (memoria condivisa col team)                                         | `@references/hindsight-cloud/SKILL.md`       |
| Usare Hindsight locale con `hindsight-embed` (preferenze personali)                        | `@references/hindsight-local/SKILL.md`       |
| Usare un server Hindsight self-hosted                                                      | `@references/hindsight-self-hosted/SKILL.md` |
| Consultare documentazione API, configurazione, SDK, retrieval strategies                   | `@references/hindsight-docs/SKILL.md`        |

## Routing rapido per keyword

- **"memory architecture"**, **"bank config"**, **"tag schema"**, **"design memory"** → `hindsight-architect`
- **"hindsight cloud"**, **"team memory"**, **"shared memory"**, **"vectorize.io"** → `hindsight-cloud`
- **"hindsight local"**, **"hindsight-embed"**, **"daemon"**, **"local memory"** → `hindsight-local`
- **"self-hosted"**, **"hindsight server"**, **"docker hindsight"** → `hindsight-self-hosted`
- **"retain"**, **"recall"**, **"reflect"**, **"API"**, **"SDK"**, **"configurazione"**, **"retrieval"** → `hindsight-docs`

## Se il contesto non è chiaro

Carica `@references/hindsight-docs/SKILL.md` come punto di partenza: contiene l'intera documentazione tecnica e i casi d'uso.
