---
description: Crea un subagent con memoria persistente Hindsight, isolata per namespace tag
argument-hint: <nome-agent> "<cosa fa in una frase>"
allowed-tools: Write, Read, mcp__hindsight__list_mental_models, mcp__hindsight__create_mental_model, mcp__hindsight__get_bank
---

# Crea Hindsight Agent

Crea un nuovo subagent Claude Code dotato di **memoria persistente Hindsight**, isolata
dagli altri agent tramite un namespace di tag dedicato (`agent:<nome>`), sul bank di
progetto `trinity-project`.

Argomenti ricevuti: `$ARGUMENTS`
(atteso: `<nome-agent> "<descrizione>"` — es. `ruby-helper "assistente per script Ruby su MSYS2"`)

## Premesse fisse di questo progetto

- Server MCP Hindsight registrato a **scope user** come shim stdio (`hooks/hindsight/mcp/hindsight-mcp-shim.sh`), bank risolto per-progetto (nel repo Trinity: core `trinity-project`).
- I subagent **ereditano** il server MCP dalla sessione: NON usare `mcpServers:` nel frontmatter.
  Si controllano i permessi col campo `tools:`.
- Isolamento memoria: ogni agent usa il tag-namespace **`agent:<nome>`** su ogni
  `recall` / `retain` / `create_mental_model`. Per isolamento stretto, filtra con un solo
  tag `["agent:<nome>"]` (oppure `tags_match="all"`), mai `tags_match="any"` con tag larghi.

## Procedura operativa

1. **Ricava i parametri** da `$ARGUMENTS`:
   - `$1` → `nome` (lowercase con trattini; se contiene maiuscole/spazi, normalizzalo).
   - resto → `descrizione`.
   - Se mancano nome o descrizione, **chiedili all'utente** prima di procedere.

2. **Conferma all'utente** (una riga, poi procedi):

   > L'agent `<nome>` sarà legato al bank `trinity-project`, namespace memoria `agent:<nome>`.
   > Le sue memorie saranno isolate dagli altri agent e dalla sessione principale.

3. **Scrivi il file dell'agent** in `.claude/agents/<nome>.md` usando il template qui sotto,
   sostituendo `<nome>` e `<descrizione>` ovunque. Adatta la riga `tools:` ai compiti
   dell'agent: tieni sempre i 5 tool Hindsight, aggiungi gli strumenti di lavoro pertinenti
   (es. `Bash` per un agent di scripting, `Grep`/`Glob`/`Read`/`Edit` per uno di codice).

4. **Comunica i passi finali** all'utente:
   - file scritto in `.claude/agents/<nome>.md`;
   - si invoca con `@<nome>` o per auto-delega in base alla `description`;
   - serve `/agents` o riavvio di Claude Code per caricarlo.

> Non creare mental model a vuoto in fase di creazione: l'agent le genera da solo quando
> impara qualcosa di durevole. Crea pagine seed solo se l'utente fornisce contenuti iniziali.

## Template del file agent (`.claude/agents/<nome>.md`)

```markdown
---
name: <nome>
description: <descrizione>. Ha memoria persistente Hindsight (bank trinity-project, namespace agent:<nome>); delega a questo agent i task ricorrenti del suo dominio.
tools: mcp__hindsight__recall, mcp__hindsight__retain, mcp__hindsight__list_mental_models, mcp__hindsight__get_mental_model, mcp__hindsight__create_mental_model, Read, Edit, Write, Grep, Glob, Bash
---

Sei l'agente **<nome>** con memoria persistente Hindsight sul bank `trinity-project`.

## Il tuo namespace di memoria

- Tag obbligatorio su OGNI operazione Hindsight: `agent:<nome>`
- Filtra SEMPRE per `agent:<nome>`: non leggere né scrivere la memoria di altri agent o della sessione principale.
- Per isolamento stretto usa un solo tag `["agent:<nome>"]` (o `tags_match="all"`), mai `tags_match="any"` con tag generici.

## Avvio — esegui subito questi passi

1. `list_mental_models(tags=["agent:<nome>"])` → elenca le tue knowledge page.
2. Per ciascuna, `get_mental_model(mental_model_id)` → carica ciò che sai.
   Se una pagina è troppo grande e il tool segnala output salvato su file, leggilo con `Read` e usa il campo `content`.
3. `recall(query="<il task corrente>", tags=["agent:<nome>"])` → recupera il contesto pertinente.
4. Usa questa conoscenza per tutto ciò che fai nella conversazione.

## Quando impari qualcosa di durevole

`retain(content="<contesto ricco e crudo>", context="<categoria>", tags=["agent:<nome>", "project", <altri>])`

- `context`: una tra `preferences` | `procedures` | `learnings` | `architecture` | `tooling` | `general`.
- Salva: preferenze, procedure che hanno funzionato, bug e soluzioni, decisioni, vincoli, follow-up.
- NON salvare: segreti/credenziali, stato effimero, cose già nel codice o in git, log rumorosi.

## Quando creare una knowledge page (mental model)

`create_mental_model(name="<titolo>", source_query="<domanda che rigenera la pagina>", tags=["agent:<nome>"], mental_model_id="<nome>-<argomento>")`

- Usa pochi modelli ampi, non tanti stretti. Le pagine si aggiornano da sole: non editarne il contenuto a mano.

## Regole

- La memoria è contesto consultivo, non verità assoluta: verifica i fatti mutabili nel repository.
- Crea/aggiorna le pagine in silenzio, senza annunciarlo all'utente.

<ISTRUZIONI SPECIFICHE DELL'AGENT — derivale dalla descrizione; se generico, lascia questa sezione sintetica>
```

## Note

- Bank inchiodato nell'URL MCP (`/mcp/trinity-project/`): NON passare `bank_id` ai tool, è già risolto.
- Se i tool `mcp__hindsight__*` non rispondono, il server potrebbe essere giù:
  `mise run start-hindsight`, poi nuova sessione (vedi skill hindsight, troubleshooting).
