# Hindsight hooks — note di sessione

Riepilogo di quanto appreso/modificato lavorando sugli hook Hindsight di Claude Code
in `D:\AI\Claude\Trinity\.claude\hooks\hindsight\`. Documento operativo, non sostituisce
`SKILL.md` (che resta la guida alle operazioni MCP retain/recall/reflect).

> Sessione del 2026-05-25.

---

## 1. Mappa dei file

| File                                                 | Ruolo                                                                                                      |
| ---------------------------------------------------- | ---------------------------------------------------------------------------------------------------------- |
| `hindsight.config.json` (root del plugin)           | Config tunabile (URL bank, parametri recall/retain/reflect). Base; un `<progetto>/hindsight.config.json` ne sovrascrive le chiavi (merge a strati) |
| `hindsight_config.py`                                | Loader: `DEFAULTS` hardcoded → file JSON → override env (`HS_CFG_<CHIAVE>`). Le liste accettano JSON o CSV |
| `hindsight-recall.sh`                                | Hook **UserPromptSubmit**: recupera memorie e le inietta come `additionalContext`. Sincrono                |
| `hindsight_recall_lib.py`                            | Logica pura testabile del recall (compose query + `build_recall_payload`)                                  |
| `hindsight-retain.sh` + `hindsight-retain-worker.py` | Hook **Stop** (async): salva un riassunto del turno nel bank                                               |
| `hindsight_debug.py`                                 | Logging JSONL opzionale (recall/retain)                                                                    |
| `hindsight-check.sh`                                 | **Suite di test/diagnostica** (vedi §9)                                                                    |
| `logs/tail-hindsight.nu`                             | Viewer Nushell del debug log                                                                               |
| `benchmark/hindsight_bench.rb`                       | **Benchmark velocità/qualità provider LLM** (retain+recall su corpus dedicato). Vedi §13                   |

---

## 2. Config attuale (snapshot)

```jsonc
"recall_budget": "mid",          // sforzo retrieval server: low | mid | high
"recall_max_tokens": 1024,       // tetto token dei fatti restituiti (governa il CONTEGGIO)
"recall_max_results": 3,         // slice CLIENT: quanti fatti iniettati nel prompt
"recall_types": ["observation"], // filtro CATEGORIA: world | experience | observation ([] = tutti)
"recall_timeout": 10,            // timeout sincrono della chiamata di rete (s)
"recall_min_prompt_chars": 20,   // gate: prompt più corti saltano il recall
"recall_cache_ttl": 300,         // validità cache client (s)
"retain_every_n_turns": 3        // throttling retain: salva 1 Stop ogni N
```

---

## 3. Debug log

- **Abilitazione**: `debug_log_enabled: true`. È OFF nei `DEFAULTS` spediti (best-effort, costo ~0 da spento).
- **Path quando `debug_log_file` è vuoto**: `<plugin>/logs/hindsight-debug.log` (es. `D:\AI\Claude\Trinity\logs\`).
  Calcolato in `hindsight_debug.py::_log_path()` relativo al modulo (risale 3 livelli da
  `hooks/hindsight/lib/`), quindi è portabile se sposti il plugin.
- **Formato**: JSONL, un evento per riga. Rotazione automatica a 5 MB → `.log.1`.
- **Viewer**: `nu logs/tail-hindsight.nu --events recall,recall_error,recall_skip`.

### Colonne del viewer (`tail-hindsight.nu`)

Sono ricostruite dai campi JSONL; vuote se l'evento non ha quel campo.

| Colonna  | Campo                                                            | Su quali eventi      |
| -------- | ---------------------------------------------------------------- | -------------------- |
| `event`  | tipo evento                                                      | tutti                |
| `status` | codice HTTP della POST                                           | solo `retain_result` |
| `cache`  | `cache` (hit) / `fresh` (miss)                                   | solo `recall`        |
| `n`      | `n_results` (conteggio GREZZO del server, **prima** dello slice) | solo `recall`        |
| `doc`    | `doc_id`                                                         | `retain*`            |
| `level`  | derivata (ERROR/SKIP/OK/INFO), non è un campo del log            | tutti                |

---

## 4. Recall — come funziona

Flusso di un prompt:

```
prompt → [min_prompt_chars?] → [cache fresh?] ──hit──→ riusa (~500ms)
                                     │ miss
                                     ↓
   POST {query, budget, max_tokens, tags, tags_match, [types]}  (timeout=10s)
                                     ↓ salva in cache
                      inietta primi [recall_max_results] risultati
```

- **Server-side** (nel payload): `budget`, `max_tokens`, `tags`, `tags_match`, `types`.
- **Client-side**: `min_prompt_chars` (gate), `cache_ttl`/`cache_dir`, `timeout`, `recall_max_results` (slice).
- **Fail-soft**: timeout/errore/cache corrotta → nessun contesto iniettato, il prompt prosegue.

### `n_results` ≠ risultati iniettati

`n_results` nel log è il conteggio **grezzo** del server (`hindsight-recall.sh:102`), loggato
**prima** dello slice. Quelli realmente iniettati sono `recall_max_results` (oggi 3). Vedere 35
nel log non significa ricevere 35 fatti.

---

## 5. Timeout (`recall_error: "timed out"`)

- Il recall è **LLM-backed** (OpenAI `gpt-4.1-nano`): latenza variabile, ~3,9s per query brevi,
  **~8,5s per query lunghe/dense** (misurato).
- Con `recall_timeout: 6` quelle query sforavano in modo riproducibile → `recall_error`,
  prompt gestito senza memoria (fail-soft).
- **Fix applicato**: `recall_timeout` 6 → **10**. Trade-off: è attesa _sincrona_ prima dell'avvio
  del turno; se ricompaiono timeout su query molto pesanti, salire a 12-15.

---

## 6. Niente `top_k`/`limit` lato server — è una scelta di design

La doc API (`references/.../api/recall.md`) è esplicita: Hindsight ragiona in **token, non in
conteggi**. I risultati non espongono nemmeno uno score numerico; conta solo l'ordine.

→ Per ridurre **quanti** risultati: abbassa `max_tokens` (server) e/o `recall_max_results` (client).
→ Non esiste un parametro "dammi N risultati".

---

## 7. `recall_types` (filtro per categoria, opzione B)

Implementato in questa sessione. Valori: `world` (fatti oggettivi), `experience` (eventi/
conversazioni), `observation` (credenze consolidate e deduplicate). `[]` = tutti (default API).

**Cosa NON fa**: ridurre il conteggio. Test live: `["observation"]` ha dato **più** risultati
(34) del default (14), perché il numero dipende da `max_tokens` e gli `observation` sono fatti
corti → ne entrano di più nel budget token. `types` sceglie _quale tipo_ recuperare, non _quanti_.

**Implementazione**: payload costruito da `build_recall_payload()` in `hindsight_recall_lib.py`.
Il campo `types` è incluso solo se contiene valori validi; gli invalidi sono filtrati
silenziosamente (no 400 dal server).

---

## 8. Cache del recall — GOTCHA path

- **Posizione reale**: `D:\tmp\hs-recall-cache` (MSYS: `/d/tmp/hs-recall-cache`), **non** il
  `/tmp` di MSYS (`C:\msys64\tmp`).
- **Perché**: la config dice `recall_cache_dir: "/tmp/hs-recall-cache"`, ma il Python del hook è
  nativo Windows (ucrt64): `os.path.abspath("/tmp/...")` risolve sul **drive corrente** → `D:`.
  È drive-dependent.
- **Conseguenza pratica**: per svuotarla da bash, `rm /tmp/hs-recall-cache/*` NON funziona;
  usare `rm -f /d/tmp/hs-recall-cache/*.json`.
- **Chiave**: SHA-256 (primi 32 char) del prompt normalizzato (lowercase, whitespace collassato).
  **Non** include `budget`/`max_tokens`/`tags`/`types` → dopo un cambio di questi parametri la
  cache può servire risultati stale fino a `cache_ttl` (300s).

---

## 9. Retain — throttling

`should_retain_now()` salva 1 Stop ogni `retain_every_n_turns` (3): turni 1-2 → `retain_skip`
`reason=throttling`, turno 3 → salva. Contatore `stop_count` per sessione in
`%TEMP%\hs-retain-state.json`. **Eccezione**: `SessionEnd` (e `HS_RETAIN_FORCE`) forzano sempre
il salvataggio, per catturare la coda della sessione.

Altri `retain_skip.reason`: `no_transcript`, `no_content`.

---

## 10. Test — `hindsight-check.sh`

**Questa è la suite di test** (non ci sono `test_*.py`). Diagnostica completa, 18 sezioni / 45 check.

```bash
PYTHONUTF8=1 bash "$TRINITY_PLUGIN_DIR/hooks/hindsight/tools/hindsight-check.sh"
# exit 0 = tutto OK, 1 = problemi. Richiede il server up.
```

Pattern dei test unit: importa i moduli via `importlib` e chiama le funzioni pure
(`git_info`, `compute_document_id`, `should_retain_now`, `strip_memory_block`, `load_config`,
`build_recall_payload`). La **sezione 18** (aggiunta in sessione) copre `recall_types` +
`build_recall_payload`.

---

## 11. Comandi utili

```bash
# Avvio/stop server
mise run start-hindsight ; mise run stop-hindsight

# Server up? (404 = up)
curl -fsS -m 3 http://127.0.0.1:8888/ -o /dev/null -w "%{http_code}\n"

# Suite di test
PYTHONUTF8=1 bash "$TRINITY_PLUGIN_DIR/hooks/hindsight/tools/hindsight-check.sh"

# Tail del debug log
nu logs/tail-hindsight.nu --events recall,recall_error,recall_skip

# Leggere un valore di config
PYTHONUTF8=1 python "$TRINITY_PLUGIN_DIR/hooks/hindsight/lib/hindsight_config.py" --get recall_timeout

# Svuotare la cache recall (path Windows-resolved!)
rm -f /d/tmp/hs-recall-cache/*.json

# Benchmark provider LLM (retain+recall su corpus dedicato) — vedi §13
ruby .claude/hooks/hindsight/benchmark/hindsight_bench.rb
BENCH_ONLY=openai-nano,groq-gptoss20b ruby .claude/hooks/hindsight/benchmark/hindsight_bench.rb
```

---

## 12. Memorie MCP salvate in sessione

Nel bank `trinity-project`:

- **(procedures)** Il file di test è `hindsight-check.sh`, non un `test_*.py`.
- **(learnings)** La cache recall è in `D:\tmp\hs-recall-cache`, non nel `/tmp` di MSYS.
- **(procedures)** Il benchmark provider è in `.claude/hooks/hindsight/benchmark/` (spostato da `test/` il 2026-05-25).

---

## 13. Benchmark provider LLM (velocità/qualità)

**Posizione**: `D:\AI\Claude\Trinity\.claude\hooks\hindsight\benchmark\` — spostato da `test/` il 2026-05-25. I path interni sono relativi a `__dir__`, quindi lo script è rilocabile (corpus e risultati vivono accanto al `.rb`).

| File                     | Ruolo                                                                                                                                                                                                                                   |
| ------------------------ | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `hindsight_bench.rb`     | Orchestratore: per ogni provider riavvia il server, fa retain del corpus, recall delle query, misura latenza/token/fatti/hit-rate. Verifica il provider attivo dal log (`verify_active_provider`) e ripristina la produzione a fine run |
| `bench_corpus.json`      | 10 documenti + 6 query (con `expected`/`min_hits` per l'hit-rate)                                                                                                                                                                       |
| `bench_results/<runid>/` | JSON per provider + `summary.csv` + `server_logs/`                                                                                                                                                                                      |

**Lancio**:

```bash
cd .claude/hooks/hindsight/benchmark && ruby hindsight_bench.rb
# o limitato ad alcuni provider:
BENCH_ONLY=openai-nano,groq-gptoss20b ruby hindsight_bench.rb
```

Ripristina automaticamente la produzione (`openai gpt-4.1-nano`) alla fine.

**Config Groq nel benchmark** (free tier 8000 TPM): `max_ctok: 4000` — **deve** essere > `RETAIN_CHUNK_SIZE` (default 3000) o il server non parte; `pace_s: 10` — attesa tra chiamate per simulare un uso ravvicinato (sul free tier riattiva di proposito il rate-limit). Su **Dev Tier** rimuovere `pace_s`; `max_ctok` resta 4000.

**Esito chiave (2026-05-25)** — resta `gpt-4.1-nano` in produzione:

| Metrica                         | gpt-4.1-nano | Groq gpt-oss-20b (free tier) |
| ------------------------------- | ------------ | ---------------------------- |
| retain medio (effettivo)        | **4,53s**    | 6,96s (con throttle)         |
| retain "pulito" (no rate-limit) | 4,53s        | ~2,8s (più veloce)           |
| fatti/doc                       | **2,9**      | 2,0 (+2 doc persi)           |
| hit-rate recall                 | **100%**     | 89%                          |
| affidabilità                    | 0 errori     | estrazioni perse per 429     |

Groq ha inferenza grezza più veloce (~2,8s), ma sul free tier ogni chiamata prenota `input + max_completion_tokens` (~4.700 tok) contro 8.000 TPM → throttling a ~1,7 retain/min, latenza reale 7-10s e perdita di fatti. **Conviene solo con Groq Dev Tier.** Un reasoning model (gpt-oss) spreca output in ragionamento (8.979 vs 3.381 token) → per fact-extraction un modello non-reasoning veloce come nano è la scelta giusta.

---

## 14. Configurazione multilingua (italiano)

I default di Hindsight sono **solo-inglese**: embedding `bge-small-en-v1.5` (384d) e reranker `cross-encoder/ms-marco-MiniLM-L-6-v2`. Per l'italiano si è prima provato `bge-m3` locale (1024d), poi si è scelta la config **finale** (2026-05-25) in `.mise.toml [env]` — embedding **cloud Google Gemini**:

```toml
HINDSIGHT_API_EMBEDDINGS_PROVIDER                     = "google"
HINDSIGHT_API_EMBEDDINGS_GEMINI_MODEL                 = "gemini-embedding-001"
HINDSIGHT_API_EMBEDDINGS_GEMINI_OUTPUT_DIMENSIONALITY = 1536
HINDSIGHT_API_RERANKER_LOCAL_MODEL                    = "BAAI/bge-reranker-v2-m3"
```

Gemini (1536d, cloud, multilingue) evita il modello di embedding pesante in locale; richiede `GEMINI_API_KEY` nell'env. Il reranker resta locale. L'embedding multilingue permette comunque il match cross-lingua (query IT → fatti EN/IT). Verificato end-to-end.

### 14a. Lingua dei fatti generati — servono DUE mission (verificato 2026-05-25)

I fatti escono in inglese anche con input italiano? È colpa delle **mission**, non dell'embedding. Il retain ha **due pipeline distinte** che generano testo, ciascuna con la sua mission (config del bank, impostate da `hindsight-set-mission.sh` via PATCH `/config`):

| Pipeline      | File del pacchetto                 | Genera                 | Mission che la guida   | Direttiva lingua nel prompt?                         |
| ------------- | ---------------------------------- | ---------------------- | ---------------------- | ---------------------------------------------------- |
| Extraction    | `engine/retain/fact_extraction.py` | `world` / `experience` | `retain_mission`       | ✅ sì, `LANGUAGE: MANDATORY` (mantieni lingua input) |
| Consolidation | `engine/consolidation/prompts.py`  | `observation`          | `observations_mission` | ❌ **no**                                            |

**Causa del mix EN/IT che si vedeva**: la `retain_mission` era in inglese (bias verso EN su `gpt-4.1-nano`, modello piccolo) e la `observations_mission` era **vuota** → la consolidation usava il suo `_DEFAULT_MISSION` inglese, senza direttiva di lingua → observation sempre in inglese.

**Fix applicata**: entrambe le mission riscritte in italiano in `hindsight-set-mission.sh` (più `observations_mission` aggiunta al PATCH), con direttiva di lingua esplicita. Test A/B live:

- solo `retain_mission` IT → world IT ✅, observation ancora EN ❌
- `retain_mission` + `observations_mission` IT → **tutti i fatti in italiano** ✅✅

NB: è config del bank (DB Postgres), quindi **sopravvive ai `pip upgrade`** del pacchetto. Da rieseguire solo se il bank viene ricostruito.

**GOTCHA — cambiare l'embedding obbliga a ricostruire il bank.** La dimensione dei vettori cambia (es. 384→1024→1536) e il server **rifiuta di partire** se il bank ha dati: `Cannot change embedding dimension from X to Y: memory_units contains N rows`. Rebuild:

1. Postgres embedded in `C:/Users/EN27553/.pg0` — db `hindsight`, user/pass `hindsight`/`hindsight`, porta 5432, `psql.exe` in `installation/18.1.0/bin/` (credenziali in `instances/hindsight-mcp/instance.json`).
2. `TRUNCATE public.memory_units, public.mental_models, public.documents, public.entities, public.entity_cooccurrences, public.memory_links, public.unit_entities, public.chunks, public.async_operations, public.audit_log CASCADE;` (preserva `banks` e `alembic_version`).
3. Riavvia → la migrazione fa `ALTER` della colonna a `vector(<nuova dim>)` sul bank vuoto. Bank benchmark orfani: `DELETE FROM public.banks WHERE bank_id LIKE 'bench-%'`.

Il rebuild **azzera il bank Hindsight** (la memoria file-based è separata e resta intatta).

---

## 15. Command `/hindsight-create-agent` — subagent con memoria isolata

**File**: `.claude/commands/hindsight-create-agent.md` (slash command, accanto a `reflect.md`).
Crea un subagent in `.claude/agents/<nome>.md` con memoria persistente Hindsight sul bank
`trinity-project`. Adattato dalla skill esterna `create-agent` del plugin marketplace, traducendo
i tool `agent_knowledge_*` nei tool locali `mcp__hindsight__*`.

**Uso**:

```bash
/hindsight-create-agent ruby-helper "assistente per script Ruby su MSYS2"
```

**Scelte di design** (specifiche di questo setup):

| Aspetto              | Scelta                                                                                                 |
| -------------------- | ------------------------------------------------------------------------------------------------------ |
| Server MCP           | Ereditato dalla sessione (`hindsight` in `.mcp.json`). Frontmatter usa `tools:`, **non** `mcpServers:` |
| Bank                 | Inchiodato nell'URL MCP (`/mcp/trinity-project/`) → non passare `bank_id` ai tool                         |
| Isolamento per-agent | Tag-namespace **`agent:<nome>`** su ogni `recall`/`retain`/`create_mental_model`                       |
| Knowledge page       | = mental model. Id prefissato `<nome>-<argomento>`, taggato `agent:<nome>`                             |
| Startup dell'agent   | `list_mental_models(tags=[agent:<nome>])` → `get_mental_model` → `recall(tags=[agent:<nome>])`         |

**GOTCHA isolamento — verificato con collaudo live (2026-05-25):**

- ✅ Il filtro per tag **isola** le memorie taggate: un fatto `agent:X` NON è visibile da un
  `recall(tags=["agent:Y"])`. (Test: keyword `ZARQUON-7742` taggata `agent:test-isolation`,
  invisibile da un namespace estraneo.)
- ⚠️ I fatti **senza tag** (`tags: []`) restano **globali**: vengono restituiti a _qualsiasi_
  namespace anche con `tags_match="any"`. Il filtro esclude i fatti con _altri_ tag, non quelli
  non taggati.
- → L'isolamento è **protettivo a senso unico**: un agent non inquina gli altri (se tagga sempre),
  ma vede comunque il pool comune non taggato del progetto. Dipende dalla **disciplina di tagging**:
  per questo il template impone il tag obbligatorio su ogni operazione.

---

## 16. Interfacce web (Control Plane + dashboard log) — task mise

> Sessione del 2026-05-26.

Due UI **opzionali** e indipendenti dal server MCP, avviate via task mise, **in foreground**
(Ctrl-C; a differenza di `start-hindsight` che è daemon `setsid nohup`).

| UI                | Porta | Avvio                    | Stop                          | Cos'è                                                                                                           |
| ----------------- | ----- | ------------------------ | ----------------------------- | --------------------------------------------------------------------------------------------------------------- |
| **Control Plane** | 9999  | `mise run control-plane` | `mise run stop-control-plane` | Web UI ufficiale Hindsight (Next.js via npx, **non nel repo**). Sfoglia bank/entità/operations, testa recall    |
| **Dashboard log** | 9292  | `mise run dashboard`     | `mise run stop-dashboard`     | App Roda/Puma nel repo (`hindsight-dashboard/`). Analizza `hindsight-debug.log`: tail SSE, color-coding, filtri |

Prerequisito dashboard (una tantum): `mise run install-dashboard`.

### Architettura Hindsight: 3 servizi

Hindsight è composto da tre servizi (vedi `references/hindsight-docs/.../developer/services.md`):

- **API service** (`hindsight-api`, :8888) — il motore retain/recall/reflect. È quello che avviamo con `start-hindsight`. È il "data plane".
- **Worker** — processore task in background; qui è interno all'API (default, ok per uso singolo).
- **Control Plane** (:9999) — solo la UI. Non ha dati propri: si collega all'API. ≠ dalla dashboard log (che legge i _log_ degli hook, non l'API).

### Gotcha d'ambiente Windows/MSYS2 (tutti risolti in `.mise.toml`)

1. **npx del Node MSYS2 è rotto.** `/ucrt64/bin/npx` crasha su qualsiasi pacchetto
   (segfault/`std::bad_weak_ptr`), mentre `node -e` funziona. → Installato Node nativo Windows via
   mise (`[tools] node = "lts"`); dentro un task mise `npx` risolve a quello. Niente Docker su questa
   macchina, quindi l'immagine `hindsight-control-plane` Docker non è un'alternativa.

2. **Bind di Next.js sull'hostname.** Il Control Plane eredita la env `HOSTNAME` (sotto MSYS2 = nome
   macchina, es. `ENWS27719997`) e vi si lega → risponde su `http://ENWS27719997:9999` ma non su
   `localhost`. → Il task forza `HOSTNAME=127.0.0.1 ... --hostname 127.0.0.1` (anche per non esporlo
   in LAN: la UI non ha API key di default, vedi `HINDSIGHT_CP_ACCESS_KEY`).

3. **Trappola doppio-Ruby.** `bundle install` lanciato a mano (shell senza mise attivo) usa il Ruby
   MSYS2 (`/ucrt64/bin/ruby`), ma `mise run` attiva il Ruby mise (`[tools] ruby = "4.0.1"`): le gem
   installate per uno non esistono per l'altro (`Bundler::GemNotFound`). → Installare SEMPRE via
   `mise run install-dashboard`, così usa lo stesso Ruby del task `dashboard`. NB: il `.ruby-version`
   della dashboard (3.3.8) è stale rispetto al pin mise.

4. **Hook `mise reshim`.** Il Ruby mise, dopo `bundle install`, chiama `mise reshim` per gli shim
   degli eseguibili gem (puma); ma `mise` non è nel PATH MSYS2 → bundler aborta con
   `No such file or directory - mise reshim`. → Aggiunto `C:/msys64/home/EN27553/.local/bin` a
   `_.path` in `[env]` di `.mise.toml`.

5. **Stop dei processi nativi Windows.** Node e Puma sono processi Windows nativi: il `netstat` MSYS
   non vede sempre le loro porte. → I task `stop-*` usano `$TRINITY_PLUGIN_DIR/hooks/hindsight/ops/kill-port.sh
<porta> [label]`, che risolve il PID via `Get-NetTCPConnection` (PowerShell 7,
   `C:/Appl/PowerShell/pwsh.exe`) e fa `Stop-Process -Force`.

### Comandi

```bash
# Control Plane (Web UI, :9999)
mise run control-plane          # foreground; → http://localhost:9999
mise run stop-control-plane

# Dashboard log (:9292)
mise run install-dashboard      # una tantum (bundle install sotto Ruby mise 4.0.1)
mise run dashboard              # foreground; → http://localhost:9292
mise run stop-dashboard

# Stop manuale di una porta qualsiasi
bash "$TRINITY_PLUGIN_DIR/hooks/hindsight/ops/kill-port.sh" 9999 control-plane
```

Nota benigna: durante `bundle install` compare `C:/msys64/home/EN27553 is not writable` → bundler
ripiega su una temp dir e completa comunque.
