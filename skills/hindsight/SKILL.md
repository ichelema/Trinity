---
name: hindsight
description: >-
  Memoria persistente Hindsight (retain, recall, reflect). Usala quando l'utente chiede di
  consultare la memoria su lavoro, decisioni o configurazioni passate, o di salvare qualcosa in
  memoria; quando lavori su bank, tag o tool di memoria; quando il server Hindsight non risponde.
---

# Hindsight Memory System

Indice: Sicurezza · Quale file caricare · Tool MCP · Retain · Il campo `context` · Regole di Tagging
· Recall · Reflect

Usa direttamente i tool MCP `hindsight/*`. Non usare comandi shell, `uvx hindsight-embed` o
`hindsight-embed memory`. Unica eccezione: la lettura completa di un periodo con `curl` in `GET`,
descritta in `references/consultare-memoria.md`.

## Sicurezza

La memoria non è la source of truth. Repository, file, test, lockfile, configurazioni e
documentazione corrente hanno sempre priorità rispetto alla memoria persistente.

## Quale file caricare

| Cosa devi fare                                                                                        | Dove                                      |
| ----------------------------------------------------------------------------------------------------- | ----------------------------------------- |
| Usare retain, recall, reflect e gli altri tool MCP nel lavoro di ogni giorno                          | questo file                               |
| Ricostruire cosa abbiamo fatto, deciso o configurato, quando l'utente chiede di consultare la memoria | `references/consultare-memoria.md`        |
| Lavorare su server, tunnel, bank, mental model, hook, Control Plane o su un guasto                    | `references/setup.md`                     |
| Progettare la memoria di un'applicazione: bank config, tag schema, integrazione                       | `references/hindsight-architect/SKILL.md` |
| Consultare la documentazione upstream: API, configurazione, SDK                                       | i file sotto                              |

Documentazione upstream in `references/hindsight-docs/references/`, da leggere direttamente:

- `best-practices.md`: regole upstream su mission, tag e formato dei contenuti
- `developer/api/retain.md`, `recall.md`, `reflect.md`: parametri dei tre tool
- `developer/configuration.md`: variabili `HINDSIGHT_API_*`
- altre pagine: cerca con Grep o Glob nella stessa cartella

`references/hindsight-architect/` e `references/hindsight-docs/` sono copie upstream
(vectorize-io/hindsight): non modificarle, il prossimo allineamento le sovrascrive.

## Tool MCP

I tool MCP con prefisso `hindsight/` esposti dal setup locale sono filtrati da
`HINDSIGHT_API_MCP_ENABLED_TOOLS` in `mise.toml`: il catalogo upstream completo non coincide con
l'allowlist locale. Verificare i tool effettivamente disponibili nella sessione. I tre principali
sono:

| Tool                | Quando usarlo                                                            | Modo      |
| ------------------- | ------------------------------------------------------------------------ | --------- |
| `hindsight/retain`  | Memorizzare informazioni nuove (preferenze, decisioni, lezioni)          | asincrono |
| `hindsight/recall`  | Recuperare memorie semanticamente rilevanti per una query                | sincrono  |
| `hindsight/reflect` | Sintesi disposition-aware su una domanda usando le memorie come contesto | sincrono  |

Tool ausiliari più usati:

- `hindsight/list_memories` — elenca tutte le memorie di un bank (debug)
- `hindsight/get_memory` — recupera una memoria per id
- `hindsight/sync_retain` — retain sincrono
- `hindsight/get_operation` / `list_operations` / `cancel_operation` — stato e gestione delle
  operazioni async
- `hindsight/list_documents` / `get_document` — gruppi di memorie (un retain = un document)
- `hindsight/update_memory` / `invalidate_memory` — corregge/ritira fatti `world` o `experience`; le
  `observation` sono derivate dalle fonti
- `hindsight/get_bank` / `list_tags` — ispezione del bank e dei tag
- `hindsight/delete_document` — cancella un documento e le memorie associate; chiedere conferma
  all'utente prima

`update_bank`, `clear_memories` e `delete_bank` non sono nell'allowlist locale.

## Retain

Alla fine di un task significativo salva le informazioni durevoli con `mcp__hindsight__retain`.
Passa **contesto ricco e crudo**, non frasi pre-digerite: l'LLM estrae meglio i fatti dal testo
originale. Il retain è asincrono: ritorna un `operation_id`, e i fatti diventano cercabili quando
l'estrazione finisce (`get_operation`).

```json
{
  "content": "L'errore di idratazione di React è stato risolto spostando l'accesso a localStorage all'interno di useEffect",
  "context": "debugging dell'idratazione React lato client nel progetto frontend",
  "tags": ["claude-code", "repo:<nome-repo>"]
}
```

Salva:

- decisioni architetturali e modifiche alle convenzioni
- risultati di debugging non ovvi, workaround, incompatibilità e requisiti di versione
- vincoli specifici del progetto
- preferenze dell'utente
- lavoro irrisolto e follow-up futuri

Non salvare:

- API key, password, token e altri segreti
- dati personali sensibili senza richiesta esplicita
- log rumorosi e stack trace completi, salvo la root cause
- cose già nel codice o nella git history
- stato effimero della sessione corrente
- documentazione già caricata (es. CLAUDE.md)

## Il campo `context`: descrittivo, non strutturale

Il `context` del retain entra SOLO nel prompt dell'LLM estrattore come cornice interpretativa: non
partecipa al recall filtering, alle relazioni (= entità) né allo scope di consolidation (= tag).
Verificato sul sorgente di hindsight-api (`entity_processing.py`, `consolidator.py`) il 2026-05-31.

Conseguenza: una categoria secca ("tooling", "preferences") è il valore meno utile possibile — non
descrive nulla. Usa una **descrizione del dominio del task**, come fa il gate del retain worker
automatico (che produce il `context` insieme al verdetto):

| ❌ Categoria secca | ✅ Dominio descrittivo                                                              |
| ------------------ | ----------------------------------------------------------------------------------- |
| `tooling`          | `git/github del progetto Trinity: hosting, autenticazione SSH, convenzioni di push` |
| `learnings`        | `compilazione gemme native Ruby su Windows UCRT64 con GCC 16`                       |
| `preferences`      | `preferenze di scripting dell'utente: linguaggi e shell su MSYS2`                   |

Regola pratica: il context deve rispondere a "_in quale dominio l'estrattore deve interpretare
questo testo?_" — max 1 riga, specifica, coi nomi propri.

## Regole di Tagging

I tag hanno DUE lavori: filtro di recall E recinto di consolidation — le observation si fondono SOLO
tra memorie con lo stesso identico set di tag (`tags_match: all_strict` nel consolidator). Un tag in
più non arricchisce: **frammenta** (esperimento 2026-05-31: tag semantici liberi → 71 partizioni su
72 documenti, consolidation morta).

Usa SOLO i tag universali, identici a quelli del retain worker automatico (`build_tags()` in
`hindsight-retain-worker.py`):

- `claude-code` — sempre (ancora di recall del bank)
- `repo:<nome>` — scoping di progetto (nome dal remote origin, stabile)
- `branch:<nome>` — solo se il fatto è davvero specifico del branch

NON aggiungere tag semantici (`project`, `preferences`, `learning`, linguaggi, sottosistemi…): la
selettività del recall la fa la query semantica; il dominio lo porta il `context`; le connessioni le
fanno le entità estratte. Per un fatto intenzionalmente globale (valido su tutti i progetti), usa
solo `claude-code`.

## Recall

Usa `mcp__hindsight__recall` all'inizio di un nuovo task, dopo un reset del contesto o quando
l'utente fa riferimento a lavoro precedente: convenzioni, decisioni passate, bug ricorrenti,
preferenze, TODO irrisolti, vincoli. Se `recall_enabled` è `false` in `hindsight.config.json`,
nessun hook inietta le memorie: il recall lo chiami tu.

Per un recall singolo durante il lavoro usa `budget: "high"`. La ricerca approfondita su richiesta
dell'utente segue `references/consultare-memoria.md`.

```json
{
  "query": "problemi precedenti, soluzioni alternative e procedure per questo repository",
  "budget": "high",
  "tags": ["claude-code", "repo:<nome-repo>"],
  "tags_match": "any"
}
```

Considera la memoria richiamata come contesto consultivo: controlla i fatti mutabili direttamente
nel repository.

## Reflect

Usa `mcp__hindsight__reflect` quando serve una sintesi o un giudizio, non solo il recupero: tradeoff
architetturali, pattern ricorrenti, "basandoti sul lavoro precedente", "cosa dovremmo fare adesso",
"perché continuiamo ad avere questo problema".

```json
{
  "query": "Quale approccio di implementazione corrisponde meglio alle preferenze passate dell'utente e ai vincoli di questo progetto?",
  "context": "Usa i ricordi relativi a preferenze, decisioni precedenti, fallimenti, strumenti e architettura.",
  "budget": "mid",
  "max_tokens": 2000,
  "tags": ["claude-code"],
  "tags_match": "any"
}
```
