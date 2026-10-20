---
name: hindsight
description: Memoria persistente Hindsight, server MCP sulla VPS raggiunto via tunnel SSH. Usala ogni volta che l'utente chiede di cercare o consultare la memoria, chiede cosa abbiamo fatto, deciso o configurato in passato ("ti ricordi…", "cosa sai di…", "cerca in memoria…") o chiede di salvare qualcosa in memoria. Usala anche per lavorare con retain, recall, reflect, memory bank e tag, e per i problemi del server Hindsight.
---

# Hindsight Memory System

Indice: Sicurezza · Quale sub-skill caricare · Operazioni di memoria via MCP ·
Quando usare retain, recall e reflect · Il campo `context` · Regole di Tagging · Esempi ·
Setup attivo in questo progetto · Troubleshooting rapido

Hindsight è un sistema di memoria persistente per agenti AI che implementa operazioni **retain / recall / reflect**.

Hai una memoria persistente attraverso il server MCP Hindsight.

Utilizza direttamente le chiamate agli strumenti MCP. Non utilizzare comandi shell, non eseguire `uvx hindsight-embed` e non chiamare `hindsight-embed memory`. Unica eccezione: la lettura completa di un periodo con `curl` in `GET`, descritta in `references/consultare-memoria.md`.

Endpoint:

```text
http://localhost:8888/mcp/trinity-project/
```

## Sicurezza

La memoria non è la source of truth. Repository, file, test, lockfile, configurazioni e documentazione corrente hanno sempre priorità rispetto alla memoria persistente.

## Quale sub-skill caricare

| Cosa devi fare | Dove |
| --- | --- |
| Usare retain, recall, reflect e gli altri tool MCP nel lavoro di ogni giorno | questo file |
| Ricostruire cosa abbiamo fatto, deciso o configurato, quando l'utente chiede di consultare la memoria | `references/consultare-memoria.md` |
| Progettare la memoria di un'applicazione: bank config, tag schema, integrazione | `references/hindsight-architect/SKILL.md` |
| Consultare la documentazione upstream: API, configurazione, SDK | i file sotto |

Documentazione upstream in `references/hindsight-docs/references/`, da leggere direttamente:

- `best-practices.md`: regole upstream su mission, tag e formato dei contenuti
- `developer/api/retain.md`, `recall.md`, `reflect.md`: parametri dei tre tool
- `developer/configuration.md`: variabili `HINDSIGHT_API_*`
- altre pagine: cerca con Grep o Glob nella stessa cartella

`references/hindsight-architect/` e `references/hindsight-docs/` sono copie upstream
(vectorize-io/hindsight): non modificarle, il prossimo allineamento le sovrascrive.

## Operazioni di memoria via MCP

I tool MCP con prefisso `hindsight/` esposti dal setup locale sono filtrati da
`HINDSIGHT_API_MCP_ENABLED_TOOLS` in `mise.toml`: il catalogo upstream completo non
coincide con l'allowlist locale. Verificare i tool effettivamente disponibili nella
sessione. I tre principali sono:

| Tool                | Quando usarlo                                                                                                                                                                                                  | Esempio di invocazione                                                                                                                          |
| ------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------- |
| `hindsight/retain`  | Memorizzare informazioni nuove (preferenze, decisioni, lezioni). Passa **contesto ricco e crudo**, non frasi pre-digerite: l'LLM estrae meglio i fatti dal testo originale. Asincrono: ritorna `operation_id`. | `retain(content="L'utente Ichelema preferisce Ruby per gli script e usa MSYS2 su Windows 11. Ha appena configurato Hindsight con gpt-5.6-luna.")` |
| `hindsight/recall`  | Recuperare memorie semanticamente rilevanti per una query. Sincrono.                                                                                                                                           | `recall(query="quali preferenze ha Ichelema per gli script?")`                                                                                    |
| `hindsight/reflect` | Sintesi disposition-aware su una domanda usando le memorie come contesto.                                                                                                                                      | `reflect(query="Come dovrei impostare un nuovo script per Ichelema?")`                                                                            |

Tool ausiliari più usati:

- `hindsight/list_memories` — elenca tutte le memorie di un bank (debug)
- `hindsight/get_memory` — recupera una memoria per id
- `hindsight/sync_retain` — retain sincrono
- `hindsight/get_operation` / `list_operations` / `cancel_operation` — stato e gestione delle operazioni async
- `hindsight/list_documents` / `get_document` — gruppi di memorie (un retain = un document)
- `hindsight/update_memory` / `invalidate_memory` — corregge/ritira fatti `world` o `experience`; le `observation` sono derivate dalle fonti
- `hindsight/get_bank` / `list_tags` — ispezione del bank e dei tag
- `hindsight/delete_document` — cancella un documento e le memorie associate; chiedere conferma all'utente prima

`update_bank`, `clear_memories` e `delete_bank` non sono nell'allowlist locale.

### Come Hindsight processa un retain

1. Il client (Claude Code) chiama `retain(content=...)`
2. Il server accetta sincrono → `{status: "accepted", operation_id: "..."}` e mette in coda
3. Worker async chiama `gpt-5.6-luna` (provider `openai-responses`) per estrarre:
   - **observation facts** (fatti atomici, es. "Ichelema prefers Ruby for scripting")
   - **world facts** (versione timestamped + entity-linked, es. "Ichelema prefers Ruby for scripting | When: 2026-05-23 | Involving: Ichelema")
4. Entrambi i tipi vengono indicizzati con embeddings nel bank `trinity-project`
5. `recall` cerca semanticamente su observation + world, restituisce ranked

## Quando usare retain proattivamente

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
- workaround, incompatibilità e requisiti di versione

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

## Quando usare recall proattivamente

Se `recall_enabled` è `false` in `hindsight.config.json`, nessun hook fa il recall: chiama `recall` a mano, secondo la sezione «Recall a inizio task» di `core-behavior.md`.

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

## Quando usare reflect proattivamente

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

## Setup attivo in questo progetto

In questo progetto Hindsight gira **solo sulla VPS `infomaniak`** (servizi `systemd --user`); i PC sono client e lo raggiungono con un tunnel SSH.

**Stack:**

- Pacchetto Python: `hindsight-api-slim[embedded-db]` (installato via `mise run install-hindsight`; NON il meta-pacchetto `hindsight-api`, alias di `[all]` che tira giù i modelli locali/PyTorch)
- Entry-point: `hindsight-local-mcp` (sulla VPS, lanciato dal servizio via `mise exec`)
- Versione verificata: **1.0.0** (2026-10-14, PC Windows; la VPS va verificata a parte); query-analyzer del recall ristretto a `it,en` (`HINDSIGHT_API_QUERY_ANALYZER_LANGUAGES`)
- LLM: **`gpt-5.6-luna`** via provider `openai-responses` per retain/reflect/consolidation (A/B 2026-08-09, ICH-60/62); **`gpt-4.1-mini`** resta LLM globale per il query-analyzer del recall (chiavi da `$OPENAI_API_KEY`; vedi commenti in `mise.toml`)
- Retain automatico: attivo solo se `retain_enabled` è `true` in `hindsight.config.json`; con `false` si salva solo con `retain` MCP. Il gate: **`gpt-5.6-luna`** decide, **TypeSafe `jev-latest`** (`$TYPESAFE_API_KEY`) conferma come secondo filtro i soli `retain` (F1 ≥ `retain_jev_threshold`, ICH-163); errore di Jev = nessun salvataggio
- Embeddings: **Google `gemini-embedding-001`** (1536d, cloud, multilingue; `$GEMINI_API_KEY`)
- Reranker: **`voyage/rerank-3`** via `litellm-sdk` (`$VOYAGE_API_KEY`), cap flat 100 candidati (per-budget spento). **Failover chain fail-open** (ICH-65): `HINDSIGHT_API_RERANKER_1_PROVIDER = "rrf"` — se Voyage non risponde il recall ripiega su RRF invece di dare HTTP 500; la degradazione è segnalata da `hindsight-failcheck.sh` (marker scritto da `hindsight-recall.sh` quando i risultati arrivano senza `scores.reranker`)
- Altre feature 0.9.0 attive: recency decay esponenziale (halflife 60 giorni), audit log server-side (retention 30 giorni), `HINDSIGHT_API_FAIL_ON_EXTRACTION_ERRORS=true` (estrazione fallita dopo i retry → operation `failed`, intercettata da `hindsight-failcheck.sh`)
- Storage: embedded PostgreSQL in `~/.pg0/` sulla VPS
- Endpoint MCP: `http://localhost:8888/mcp/trinity-project/` (bank statico per-progetto)
- Registrato a **scope user** come shim stdio `hooks/hindsight/mcp/hindsight-mcp-shim.sh` (bank risolto per-progetto; vedi sotto)
- **Server (VPS):** `hindsight.service`, `hindsight-cp.service` e `hindsight-backup.timer` (`systemd --user`). Gestione: `systemctl --user status|restart hindsight`, log `journalctl --user -u hindsight`. Backup: gli ultimi 5 dump in `~/backups/hindsight`.
- **Client (PC):** env `HINDSIGHT_SSH_TUNNEL=hindsight-vps` (in `~/.claude/settings.json`, generato da chezmoi): `hindsight-ensure-up.sh` apre il tunnel che porta `127.0.0.1:8888` (API+MCP) e `localhost:9999` (Control Plane) in locale. Chiave SSH dedicata e ristretta (`restrict,port-forwarding,permitopen="127.0.0.1:8888",permitopen="localhost:9999",command="/bin/false"`). Nessun avvio locale e nessun fallback.
- **Restore del DB (VPS):** `systemctl --user stop hindsight-cp hindsight` → `mise run db-restore` → `systemctl --user start hindsight hindsight-cp`.
- **Upgrade Python (VPS):** dopo `mise upgrade python` serve `mise run install-hindsight` e `systemctl --user restart hindsight`.

Verifica veloce che il server risponda:

```bash
curl -fsS -m 3 http://localhost:8888/ -o /dev/null -w "%{http_code}\n"  # 404 = up
```

### Multi-bank: core + bank per progetto

Dal 2026-06-12 la memoria è a due livelli: il bank **CORE** `trinity-project`
(informazioni trasversali) + un **bank per progetto** isolato, governati dal
blocco `bank` di `hindsight.config.json`:

- `retain_bank: "auto"` → il retain automatico (se `retain_enabled` è `true`) scrive sul bank del progetto
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
(`--scan/--triage/--move/--reject/--status`); lo scan+triage si lancia a mano
e genera `logs/promote-candidates.json`.

### Mental model: knowledge page iniettate a inizio sessione

Tre mental model sono definiti nel blocco `mental_models` di `hindsight.config.json`:
`user-profile`, `project-conventions`, `recurring-learnings`. I primi due vengono iniettati
come `additionalContext` all'avvio di una sessione nuova (`startup`) dall'hook `hindsight-mm-inject.sh`
(gated da `mental_models_inject_on_start: true`, ids in `mental_models_inject_ids`);
`recurring-learnings` resta nel bank ma non viene iniettato.

- **refresh** rigenera il contenuto dal bank; **inject** mostra solo il contenuto già esistente.
- Refresh manuale immediato (necessario dopo aver cancellato/corretto un fatto):
  `bash hooks/hindsight/ops/hindsight-mental-models.sh refresh --all`

### Hook di sessione e strumenti operativi

| Componente | Trigger/uso | Cosa fa |
| ---------- | ----------- | ------- |
| `hindsight-ensure-up.sh` | SessionStart | Attende la readiness dell'endpoint MCP, aprendo prima il tunnel SSH se `HINDSIGHT_SSH_TUNNEL` è impostata (elimina la race "tool `hindsight/*` non registrati") |
| `hindsight-mm-inject.sh` | SessionStart | Inietta i mental model (vedi sopra) |
| `hindsight-failcheck.sh` | UserPromptSubmit | Segnala operation async `failed` lato server (retain accettato ma estrazione fallita) e la degradazione del reranker; de-dup via state file |
| `mise run db-dump` / `db-restore` | manuale | `pg_dump`/restore del DB Hindsight, solo sulla VPS (`tools/hs-db-dump.sh`, `hs-db-restore.sh` con guardrail anti-perdita) |
| `tools/hindsight_export.py` / `hindsight_import.py` | cambio provider embedding | Export dei documenti → re-retain sul nuovo embedding (il cambio di dimensione obbliga al rebuild del bank) |

### Interfaccia web: Control Plane

Una UI **opzionale**, indipendente dal server MCP, servita sulla VPS da `hindsight-cp.service` e raggiunta via tunnel su `http://localhost:9999`:

| UI                                             | Porta | Avvio                    | A cosa serve                                                                                                    |
| ---------------------------------------------- | ----- | ------------------------ | --------------------------------------------------------------------------------------------------------------- |
| **Control Plane** (Web UI ufficiale Hindsight) | 9999  | `hindsight-cp.service` (VPS; a mano `mise run control-plane`) | Sfogliare bank/agent, entità e relazioni, storico operations, testare query di recall. Si collega all'API :8888 |

- **Control Plane**: app Next.js scaricata via `npx @vectorize-io/hindsight-control-plane` (non nel repo). Gira sul **Node gestito da mise** (`[tools] node`), perché l'`npx` del Node MSYS2 (`/ucrt64/bin`) crasha. È legato a `localhost` con `HOSTNAME=localhost` e `--hostname localhost` (no LAN; configurazione conservata dal workaround storico dell'origin mismatch). URL consigliato: `http://localhost:9999`. Non ha API key — `HINDSIGHT_CP_ACCESS_KEY` la protegge se la esponi.
- Per analizzare `hindsight-debug.log` (JSONL) non serve una UI: `nu -c "open logs/hindsight-debug.log | lines | each { from json } | where event == 'recall'"`.

> Note operative in `README.md` (stessa cartella): «Mappa dei file», «Debug log»,
> «Recall — come funziona», «Test», «Interfaccia web (Control Plane)».
> Dettagli di avvio e bind `HOSTNAME`: task `control-plane` in `mise.toml`.

## Troubleshooting rapido

| Sintomo                                                   | Causa probabile                                          | Fix                                                                           |
| --------------------------------------------------------- | -------------------------------------------------------- | ----------------------------------------------------------------------------- |
| Tool `hindsight/*` non visibile in sessione               | Tunnel SSH non attivo o servizio giù sulla VPS           | Verifica `HINDSIGHT_SSH_TUNNEL`, poi `systemctl --user status hindsight` (VPS) e nuova sessione                    |
| `recall` torna vuoto subito dopo un `retain`              | Estrazione fatti ancora in corso, perché è async         | Polla `get_operation(operation_id)` finché `completed`, poi ricalla           |
| `OPENAI_API_KEY not set` nel log del server               | Variabile non disponibile al servizio sulla VPS          | Verifica con `mise env` e `journalctl --user -u hindsight`                                                       |
