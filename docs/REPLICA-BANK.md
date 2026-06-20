# Replicare il bank Hindsight `trinity-project` su un altro PC

Procedura per ricreare su una macchina diversa il bank di memoria persistente
Hindsight `trinity-project` (il **core_bank** del plugin, vedi `hindsight.config.json`).

Due approcci, con garanzie diverse:

- **(A) `pg_dump` / `pg_restore`** — copia **identica** (embedding, observation, entità,
  proof count, freshness, tutto). Vincolata alla stessa versione di schema e allo
  stesso modello di embedding.
- **(B) export + re-retain** (`hindsight_export.py` → JSON → `hindsight_import.py`) —
  **portabile** attraverso cambi di modello/versione, ma **ricostruisce** observation
  ed embedding da zero: non è identica.

Tutti i path usano `<USER>` come placeholder dell'username Windows (in shell MSYS2:
`${USERNAME}`). **Non** sostituirli con valori reali nei comandi che committi.

---

## 1. Quando serve replicare il bank (e quando no)

**Serve** quando:

- migri lo sviluppo Trinity su un **nuovo PC** e vuoi portarti dietro la memoria accumulata;
- vuoi un **backup off-site** ripristinabile del bank;
- vuoi un **clone identico** per esperimenti distruttivi (test di rebuild, cambio reranker)
  senza rischiare il bank di produzione.

**NON serve** (o non basta) quando:

- vuoi solo **cambiare il modello di embedding** sulla *stessa* macchina: quello è un
  *rebuild in-place* (export → wipe → cambio provider → re-retain), documentato nel
  `mise.toml` e nello `skills/hindsight/README.md` §14, non una replica.
- ti interessa solo il **testo sorgente** dei fatti: l'approccio B (export JSON) è già un
  backup leggibile e versionabile di tutto `original_text`.

> Stato attuale del bank sorgente (rilevato il 2026-06-20): `trinity-project` contiene
> **176 documenti** (`GET /v1/default/banks/trinity-project/documents` → `total`).
> hindsight-api in esecuzione: **0.8.3** (da `GET http://127.0.0.1:8888/openapi.json`).

---

## 2. Approccio A — `pg_dump` (replica identica)

Hindsight tiene **tutto** in un Postgres **embedded** sotto la home Windows dell'utente:
embedding vettoriali, documenti, entità, memory_units/observation, mental model, audit log.
Copiare quel database = copiare il bank bit per bit.

### 2.1 Prerequisiti (entrambe le macchine)

| Requisito | Valore (sorgente, verificato) | Note |
| --- | --- | --- |
| Postgres embedded | istanza `hindsight-mcp`, **18.1.0** | path: `C:/Users/<USER>/.pg0` |
| DB / user / pass | `hindsight` / `hindsight` / `hindsight` | credenziali **locali di default** (da `instances/hindsight-mcp/instance.json`) |
| Porta | `5432` | idem |
| Binari PG | `C:/Users/<USER>/.pg0/installation/18.1.0/bin/{pg_dump,pg_restore,psql}.exe` | la sottocartella è la **versione**: rilevala con il glob qui sotto |
| `hindsight_api` | **stessa versione** sorgente↔destinazione (0.8.3) | schema DB legato alla versione → vedi gotcha |
| Provider embedding | **zeroentropy / zembed-1 / 1280 dim** | obbligatorio per fare nuovi retain/recall sul clone → vedi gotcha |

La sottocartella `installation/<versione>/bin` cambia con gli upgrade del Postgres embedded.
Il repo la deriva sempre via glob (vedi `hooks/hindsight/ops/hindsight-stop-services.sh:15`).
Per ricavare il path dei binari sulla macchina corrente:

```bash
PGBIN="$(ls -d /c/Users/"${USERNAME}"/.pg0/installation/*/bin 2>/dev/null | sort -V | tail -1)"
echo "$PGBIN"
```

### 2.2 Dump sul PC SORGENTE

Il DB Postgres **sopravvive al crash/stop dell'API**: per un dump pulito e coerente
**ferma prima il server MCP** ma lascia **acceso Postgres** (`pg_dump` ha bisogno che il
server DB risponda sulla 5432; ferma solo `hindsight-local-mcp`, non Postgres).

```bash
# 1) Ferma SOLO il server MCP (lascia vivo Postgres) per evitare scritture durante il dump.
#    NB: `mise run stop-hindsight` ferma ANCHE il Postgres (hindsight-stop-services.sh):
#    NON usarlo qui. Termina solo il launcher MCP:
/c/Windows/System32/taskkill.exe //F //T //IM hindsight-local-mcp.exe

# 2) Path dei binari Postgres (glob sulla versione installata)
PGBIN="$(ls -d /c/Users/"${USERNAME}"/.pg0/installation/*/bin 2>/dev/null | sort -V | tail -1)"

# 3) Dump del database 'hindsight' in formato custom (compresso, ripristinabile selettivamente)
PGPASSWORD=hindsight "$PGBIN/pg_dump.exe" \
  -h 127.0.0.1 -p 5432 -U hindsight \
  -d hindsight -Fc -f "D:/tmp/hindsight-$(date +%Y%m%dT%H%M%S).dump"

echo "dump in D:/tmp/"
```

Note:

- `-Fc` = formato *custom* (compresso). In alternativa `-Fp` per un `.sql` testuale
  ispezionabile (più grande). Il custom è preferibile per il restore.
- Il dump contiene **tutti i bank** presenti nel DB, non solo `trinity-project`
  (Hindsight è multi-bank in un'unica istanza Postgres). Per il solo `trinity-project`
  servirebbe un filtro per-bank a livello applicativo che `pg_dump` non conosce → in
  pratica si dumpa l'intero DB e, se serve, si potano i bank estranei sul clone con
  `DELETE FROM public.banks WHERE bank_id = '<altro>'` **[DA VERIFICARE]** la cascata
  esatta delle FK per una potatura pulita.
- Se preferisci non fermare nulla: `pg_dump` su Postgres prende uno snapshot transazionale
  coerente anche con l'API attiva; il rischio è solo catturare un retain a metà. Per una
  **replica identica e riproducibile** conviene comunque fermare l'MCP.

### 2.3 Trasferimento

Copia il file `.dump` sul PC destinazione (chiavetta, scp, share di rete…). È un singolo
file binario; nessuna conversione EOL.

### 2.4 Restore sul PC DESTINAZIONE

Prerequisito: sul PC destinazione Hindsight dev'essere già stato installato e avviato
**almeno una volta** (`mise run install-hindsight` poi `mise run start-hindsight` dal repo),
così che esistano l'istanza Postgres `hindsight-mcp`, il DB `hindsight` e lo schema della
**stessa** versione di `hindsight_api`.

```bash
# 0) Ferma il server MCP sul PC destinazione (lascia Postgres acceso)
/c/Windows/System32/taskkill.exe //F //T //IM hindsight-local-mcp.exe

PGBIN="$(ls -d /c/Users/"${USERNAME}"/.pg0/installation/*/bin 2>/dev/null | sort -V | tail -1)"

# 1) Restore: --clean azzera gli oggetti prima di ricrearli, --if-exists evita errori
#    se non esistono ancora. Su DB già inizializzato dalla migrazione, questo
#    sovrascrive il contenuto col bank sorgente.
PGPASSWORD=hindsight "$PGBIN/pg_restore.exe" \
  -h 127.0.0.1 -p 5432 -U hindsight \
  -d hindsight --clean --if-exists --no-owner \
  "C:/percorso/hindsight-XXXX.dump"

# 2) Riavvia il server MCP (dal repo Trinity)
mise run start-hindsight
```

Note:

- `--no-owner` evita errori se l'utente DB differisce (qui è sempre `hindsight`, ma è
  innocuo tenerlo).
- Eventuali WARNING di `pg_restore` su estensioni/oggetti di sistema già presenti sono
  benigni; conta che le tabelle `public.*` vengano popolate.
- Se il restore lamenta tabelle mancanti, lo schema sul clone non è stato creato:
  avvia almeno una volta l'API **prima** del restore (la migrazione Alembic crea lo schema).

### 2.5 Gotcha dell'approccio A

1. **Versione di `hindsight_api` identica.** Lo schema del DB è gestito da migrazioni
   (Alembic, tabella `alembic_version`). Ripristinare un dump preso con la 0.8.3 dentro
   uno schema creato da una versione diversa può fallire o lasciare il DB incoerente.
   Installa sul clone la **stessa** versione (`pip install hindsight-api==<X.Y.Z>` via
   `mise run install-hindsight`, eventualmente pinnando la versione).
2. **Stesso provider/modello/dimensioni di embedding.** Gli embedding salvati sono
   `vector(1280)` prodotti da **ZeroEntropy zembed-1** (`mise.toml`:
   `HINDSIGHT_API_EMBEDDINGS_PROVIDER=zeroentropy`, `..._ZEROENTROPY_MODEL=zembed-1`,
   `..._ZEROENTROPY_DIMENSIONS=1280`). Il restore copia quei vettori così come sono.
   Per fare **nuovi** retain/recall sul clone che siano confrontabili con i vecchi
   embedding, il server del clone deve usare lo **stesso** provider/modello/dimensioni:
   altrimenti i nuovi vettori vivrebbero in uno spazio diverso e il recall sarebbe
   incoerente (e se le dimensioni differiscono, il server **rifiuta di partire**:
   `Cannot change embedding dimension from X to Y`). → Replica anche il blocco
   `HINDSIGHT_API_EMBEDDINGS_*` del `mise.toml` e imposta `ZEROENTROPY_API_KEY`
   nell'ambiente del clone.
3. **Reranker.** `zerank-2` (ZeroEntropy) agisce a *query-time*, non è memorizzato nel DB:
   non incide sul dump, ma per recall identici serve la stessa config reranker + chiave
   (`HINDSIGHT_API_RERANKER_*`).
4. **Server fermo durante il dump?** Non obbligatorio (snapshot transazionale), ma
   consigliato fermare l'MCP per una replica riproducibile. **Mai** fermare Postgres con
   `mise run stop-hindsight` *prima* del dump: quel task ferma anche il DB e `pg_dump`
   non avrebbe a chi connettersi.
5. **Le mission/config del bank viaggiano nel dump.** `retain_mission`,
   `observations_mission`, ecc. impostate sul bank (PATCH `/config`) vivono in Postgres →
   il clone le eredita. Non vanno re-impostate a mano.

---

## 3. Approccio B — export + re-retain (portabile cross-modello)

Riepilogo di cosa fanno i due tool (sorgenti letti in `hooks/hindsight/tools/`):

- **`hindsight_export.py`** — pagina `GET <bank>/documents` (a pagine da 100), per ogni
  documento fa `GET <bank>/documents/{id}` e ne estrae **solo il contenuto grezzo**.
  Ogni item esportato contiene: `document_id` (l'`id` del documento, per l'upsert
  idempotente), `content` (= `original_text`), `context`, `timestamp` (= `event_date`),
  `metadata`, `tags`. Salta i documenti senza testo. Scrive un JSON
  `{exported_at, source_api_url, document_count, skipped_ids, items}` in
  `hooks/hindsight/data/exports/hindsight-export-<UTC>.json`.
  **Non** esporta embedding, observation, entità, proof count: solo la sorgente.
- **`hindsight_import.py`** — rilegge il JSON e per ogni item fa
  `POST <bank>/memories` (un retain). Il server **ri-estrae i fatti via LLM** e
  **ri-genera gli embedding col modello attivo in quel momento**. Omette i campi `None`
  dal payload. È **idempotente**: ogni item porta il suo `document_id` → il server fa
  *upsert*, quindi re-importare non duplica.

### 3.1 Firma reale e argomenti

`hindsight_export.py`:

```
python hindsight_export.py [--api-url URL] [--out FILE] [--page 100] [--timeout 20]
```

- `--api-url` default: `api_url` da `hindsight.config.json` risolto dal loader
  (`hindsight_config.load_config`) → il **core_bank**, cioè
  `http://127.0.0.1:8888/v1/default/banks/trinity-project`.
- `--out` default: `hooks/hindsight/data/exports/hindsight-export-<UTC>.json`
  (la cartella viene creata se manca).
- Path nei flag in **stile Windows** (`C:/...`), non MSYS (`/c/...`).

`hindsight_import.py`:

```
python hindsight_import.py [--in FILE] [--api-url URL] [--dry-run] [--async] [--timeout 90] [--sleep SEC]
```

- `--in` default: l'export **più recente** in `hooks/hindsight/data/exports/`.
- `--api-url` default: come sopra (core bank).
- `--dry-run`: valida il file e stampa cosa farebbe, **senza** inviare nulla.
- `--async`: retain accodato lato server (non attende l'estrazione; utile per molti doc).
- `--sleep`: pausa fra un retain e l'altro (rate-limit verso LLM/embedder).

### 3.2 Chiavi API necessarie

Il re-import gira **attraverso il server**, che per ogni retain chiama:

- l'**LLM** di estrazione/consolidation → `OPENAI_API_KEY` (il `mise.toml` usa OpenAI
  `gpt-4.1-mini` per LLM e consolidation);
- l'**embedder** ZeroEntropy `zembed-1` → `ZEROENTROPY_API_KEY`.

Quindi il server del PC destinazione dev'essere **avviato dal repo** (`mise run start-hindsight`)
con quelle variabili nell'ambiente, altrimenti i retain falliscono.
I tool export/import **non** leggono chiavi: parlano solo HTTP col server.

### 3.3 Procedura

**Sul PC sorgente** (server up):

```bash
cd "$TRINITY_PLUGIN_DIR"            # o il repo D:/AI/Claude/Trinity
mise exec -- python hooks/hindsight/tools/hindsight_export.py
# → hooks/hindsight/data/exports/hindsight-export-<UTC>.json
```

Trasferisci il JSON sul PC destinazione (è testo UTF-8, versionabile).

**Sul PC destinazione** (server up, chiavi nell'env, bank vuoto o esistente):

```bash
cd "$TRINITY_PLUGIN_DIR"
# Validazione a secco prima di scrivere:
mise exec -- python hooks/hindsight/tools/hindsight_import.py --in "C:/percorso/hindsight-export-XXXX.json" --dry-run
# Import reale (sincrono, con piccola pausa anti rate-limit):
mise exec -- python hooks/hindsight/tools/hindsight_import.py --in "C:/percorso/hindsight-export-XXXX.json" --sleep 0.3
```

> Nota: `mise exec --` garantisce l'`[env]` del plugin (Python 3.13, `PYTHONUTF8=1`,
> CA bundle). In alternativa, da una shell con quell'env già attivo, `python ...` diretto.
> Il `python` richiesto è quello del runtime mise (gli entry-point e l'UTF-8 dipendono da `[env]`).

### 3.4 Cosa si perde / cosa si ricostruisce

- **Si conserva**: il testo sorgente di ogni documento (`original_text`), il suo
  `document_id`, `context`, `event_date`, `metadata`, `tags`.
- **Si ricostruisce da zero**: i fatti estratti (`world`/`experience`), le **observation**
  consolidate, gli **embedding**, le **entità** e relazioni, i **proof count** e la
  **freshness**. Dipendono dal LLM e dall'embedder attivi al momento dell'import →
  l'esito **non è identico** all'originale (diverso modello, diverso ordine di
  consolidation, conteggi ricostruiti).
- I documenti **senza testo sorgente** (es. mental model puri, o doc con solo derivati)
  vengono **saltati** dall'export (`skipped_ids`) → non attraversano questo canale.
  **[DA VERIFICARE]** se i **mental model** definiti in `hindsight.config.json`
  (`user-profile`, `project-conventions`, `recurring-learnings`) vengano ricreati: sono
  rigenerati on-demand dalle loro `source_query` (non sono documenti con `original_text`),
  quindi via approccio B vanno **ri-creati/rinfrescati** separatamente
  (`refresh_mental_model` / inject on start), non li porta l'import.

---

## 4. Confronto A vs B

| Criterio | A — `pg_dump`/`pg_restore` | B — export + re-retain |
| --- | --- | --- |
| **Identità** | Identica (embedding, observation, entità, proof, freshness, mission) | Approssimata: testo sorgente identico, derivati **ricostruiti** |
| **Mental model** | Inclusi nel dump | Da ri-creare/rinfrescare a parte |
| **Dipende dalla versione `hindsight_api`** | Sì — schema DB deve combaciare | No — passa solo testo via API stabile |
| **Dipende dal modello di embedding** | Vettori legati a zembed-1/1280; nuovi retain richiedono lo stesso provider | No — ri-embedda col modello attivo all'import |
| **Chiavi API necessarie al trasferimento** | Nessuna per il restore (servono dopo, per usare il bank) | **Sì**: `OPENAI_API_KEY` + `ZEROENTROPY_API_KEY` (server attivo) |
| **Server attivo durante l'operazione** | MCP fermo, **Postgres acceso** (dump/restore) | **Server up** su entrambi i lati |
| **Costo** | Nessuna chiamata a pagamento | Paga LLM (estrazione) + embedder per ogni documento |
| **Dimensione artefatto** | Dump binario (vettori inclusi, più grande) | JSON di solo testo (più piccolo, versionabile) |
| **Quando usarlo** | "Voglio lo **stesso** bank su un altro PC", backup ripristinabile, clone per test | Migrazione **cross-modello/versione**, backup leggibile del solo contenuto |

**Regola pratica**: per "replica identica su un altro PC con la stessa toolchain" usa **A**.
Usa **B** se sul clone cambi modello di embedding/versione, o se vuoi un backup del solo
testo indipendente dall'infrastruttura.

---

## 5. Checklist di verifica post-replica

Su entrambi gli approcci, dopo il restore/import e con il server riavviato
(`mise run start-hindsight`):

```bash
# 0) Server up? (404 sulla root = up; /health = healthy)
curl -fsS -m 3 http://127.0.0.1:8888/ -o /dev/null -w "root=%{http_code}\n"
curl -fsS -m 3 http://127.0.0.1:8888/health   # {"status":"healthy","database":"connected"}

# 1) Conteggio documenti del bank: deve coincidere con la sorgente
#    (sorgente al 2026-06-20: total = 176). Per l'approccio B può differire leggermente
#    se alcuni doc senza testo erano stati saltati (skipped_ids nell'export).
curl -fsS -m 5 "http://127.0.0.1:8888/v1/default/banks/trinity-project/documents?limit=1&offset=0" \
  | python -c "import sys,json;print('total=',json.load(sys.stdin)['total'])"

# 2) Suite di diagnostica completa del plugin (richiede server up)
PYTHONUTF8=1 bash "$TRINITY_PLUGIN_DIR/hooks/hindsight/tools/hindsight-check.sh"
```

Verifiche dai tool MCP Hindsight (dalla sessione Claude Code sul clone):

- `list_documents` sul bank `trinity-project` → conteggio coerente col punto 1.
- `recall` con una query nota (es. *"dove sono i binari Postgres del bank"*) → deve
  restituire fatti pertinenti. Per l'approccio **A** ci si attende lo stesso ranking
  della sorgente; per **B** i fatti pertinenti ci sono ma observation/ordine possono
  differire.
- `list_tags` → presenza del tag `claude-code` (tag di recall di default).
- (solo per chi vuole confronto fine) `list_memories` e raffronto a campione dei testi.

Controllo lato Postgres (approccio A, conteggio righe vettoriali):

```bash
PGBIN="$(ls -d /c/Users/"${USERNAME}"/.pg0/installation/*/bin 2>/dev/null | sort -V | tail -1)"
PGPASSWORD=hindsight "$PGBIN/psql.exe" -h 127.0.0.1 -p 5432 -U hindsight -d hindsight \
  -c "SELECT count(*) FROM public.documents; SELECT count(*) FROM public.memory_units;"
```

> **[DA VERIFICARE]** i nomi esatti delle tabelle vettoriali sul clone: lo
> `skills/hindsight/README.md` §14 elenca `memory_units, mental_models, documents,
> entities, entity_cooccurrences, memory_links, unit_entities, chunks, async_operations,
> audit_log` per la versione documentata; con `hindsight_api` 0.8.3 lo schema potrebbe
> aver aggiunto/rinominato tabelle. Per l'approccio A non serve conoscerle (il dump le
> copia tutte); serve solo se vuoi contare a mano.

---

## Riferimenti nel repo

- `hooks/hindsight/tools/hindsight_export.py` — export del testo sorgente.
- `hooks/hindsight/tools/hindsight_import.py` — re-retain idempotente.
- `hooks/hindsight/lib/hindsight_config.py` — risoluzione di `api_url`/bank (core = `trinity-project`).
- `hooks/hindsight/ops/hindsight-stop-services.sh` — stop MCP + Postgres (glob versione bin).
- `hindsight.config.json` — blocco `bank` (`api_base`, `core_bank`, `retain_bank`, `recall_banks`), mental model.
- `mise.toml` — `[env]` con `HINDSIGHT_API_EMBEDDINGS_*` (zeroentropy/zembed-1/1280),
  `HINDSIGHT_API_RERANKER_*` (zerank-2), task `install-hindsight`/`start-hindsight`/`stop-hindsight`.
- `skills/hindsight/README.md` §14 — Postgres embedded, credenziali, procedura di rebuild.
