# Hindsight hooks — note di sessione

Riepilogo di quanto appreso/modificato lavorando sugli hook Hindsight di Claude Code
in `E:\AI\Claude\Trinity\hooks\hindsight\`. Documento operativo, non sostituisce
`SKILL.md` (che resta la guida alle operazioni MCP retain/recall/reflect).

> Sessione del 2026-05-25.

---

## 1. Mappa dei file

| File                                                 | Ruolo                                                                                                                                              |
| ---------------------------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------- |
| `hindsight.config.json` (root del plugin)            | Config tunabile (URL bank, parametri recall/retain/reflect). Base; un `<progetto>/hindsight.config.json` ne sovrascrive le chiavi (merge a strati) |
| `hindsight_config.py`                                | Loader: `DEFAULTS` hardcoded → file JSON → override env (`HS_CFG_<CHIAVE>`). Le liste accettano JSON o CSV                                         |
| `hindsight-recall.sh`                                | Hook **UserPromptSubmit**: lato retain delegato al worker (`retain_at_prompt`: pickup dell'esito del gate precedente, consenso retain pending, poi gate differito del turno accodato in un processo detached **parallelo** al recall) → recupera memorie e le inietta come `additionalContext`, fondendo l'esito del gate all'emit (attesa max 6 s, altrimenti raccolto al prompt dopo). Sincrono |
| `hindsight_recall_lib.py`                            | Helper del recall (`build_recall_payload`, `last_assistant_text`, `strip_memory_block`)                                                                          |
| `hindsight-retain.sh` + `hindsight-retain-worker.py` | Hook **Stop** (sincrono, solo enqueue in `hs-retain-queue/`); il worker valuta l'entry al prompt successivo (da `hindsight-recall.sh`) o nel `--drain` della sentinella e salva un riassunto del turno nel bank (ICH-86) |
| `hindsight_debug.py`                                 | Logging JSONL opzionale (recall/retain)                                                                                                            |
| `hindsight-check.sh`                                 | **Suite di test/diagnostica** (vedi §9)                                                                                                            |
| `logs/tail-hindsight.nu`                             | Viewer Nushell del debug log                                                                                                                       |
| `benchmark/hindsight_bench.rb`                       | **Benchmark velocità/qualità provider LLM** (retain+recall su corpus dedicato). Vedi §13                                                           |

---

## 2. Config attuale (snapshot)

```jsonc
"recall_budget": "mid",          // sforzo retrieval server: low | mid | high
"recall_max_tokens": 2048,       // tetto token dei fatti restituiti (governa il CONTEGGIO)
"recall_max_results": 3,         // slice CLIENT: quanti fatti iniettati nel prompt
"recall_types": ["observation", "world", "experience"], // filtro CATEGORIA ([] = tutti)
"recall_timeout": 10,            // timeout sincrono della chiamata di rete (s)
"recall_min_prompt_chars": 20,   // gate: prompt più corti saltano il recall
"recall_result_filter_model": "gpt-5.6-luna", // classificatore post-recall
"recall_result_filter_threshold": 0.8,          // bypass su scores.reranker >= soglia
"recall_pending_ttl": 900,                      // validità del consenso medium (s)
"recall_debug_in_context": false,               // mostra route + memorie iniettate
"retain_enabled": false,         // MASTER SWITCH: retain automatico (Stop → coda → valutazione al prompt successivo) SPENTO — si salva solo via retain MCP
"retain_every_n_turns": 3        // throttling retain: salva 1 turno accodato ogni N (inattivo finché retain_enabled è false)
```

---

## 3. Debug log

- **Abilitazione**: `debug_log_enabled: true`. È OFF nei `DEFAULTS` spediti (best-effort, costo ~0 da spento).
- **Path quando `debug_log_file` è vuoto**: `<plugin>/logs/hindsight-debug.log` (es. `E:\AI\Claude\Trinity\logs\`).
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
| `source` | `fresh` (ogni recall normale interroga il server)                 | solo `recall`        |
| `n`      | `n_results` (conteggio GREZZO del server, **prima** dello slice) | solo `recall`        |
| `doc`    | `doc_id`                                                         | `retain*`            |
| `level`  | derivata (ERROR/SKIP/OK/INFO), non è un campo del log            | tutti                |

---

## 4. Recall — come funziona

Flusso di un prompt:

```
prompt → [pending medium?] → consenso sì: consuma e inietta una volta
                    │ nessun pending / nuovo prompt
                    ↓
   POST recall fresco {query, budget, max_tokens, tags, tags_match, [types]}
                    ↓
   scores.reranker >= 0.8 → high; altri → Luna low/medium/high
                    ↓
   high: inietta │ low: scarta │ solo medium: salva e chiede consenso
```

- **Server-side** (nel payload): `budget`, `max_tokens`, `tags`, `tags_match`, `types`.
- **Client-side**: `min_prompt_chars`, `timeout`, `recall_max_results`, filtro post-recall e pending medium.
- **Nessuna cache**: ogni prompt normale richiama il server e riclassifica i risultati.
- **Fail-open del filtro**: timeout, chiave mancante o JSON invalido → risultati originali iniettati.

### `n_results` ≠ risultati iniettati

`n_results` nel log è il conteggio **grezzo** del server (`hindsight-recall.sh:102`), loggato
**prima** dello slice. Quelli realmente iniettati sono `recall_max_results` (oggi 3). Vedere 35
nel log non significa ricevere 35 fatti.

---

## 5. Timeout (`recall_error: "timed out"`)

- Il recall è **LLM-backed** (query-analyzer sul LLM globale, oggi `gpt-4.1-mini`): latenza variabile, ~3,9s per query brevi,
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

## 8. Stato pending delle memorie medium

Le memorie `medium` non sono una cache: durano soltanto in attesa del consenso e non vengono
riutilizzate da altri prompt. Il file è identificato da hash di `session_id + cwd`, vive nella
directory per-utente `recall_pending_dir`, ha TTL configurabile e viene consumato una sola volta.
La directory e i file usano rispettivamente permessi `0700` e `0600` sui sistemi POSIX.
Su Windows/NTFS `chmod` è un no-op: la riservatezza dei testi salvati nel pending
dipende dalle ACL della directory cache per-utente (`%LOCALAPPDATA%`-equivalente),
che di default non è leggibile da altri utenti della macchina.

---

## 9. Retain — throttling

> ⚠️ Oggi il retain automatico è **spento** (`retain_enabled: false` in `hindsight.config.json`):
> l'hook Stop accoda comunque il payload, il worker lo scarta senza valutarlo e si salva solo via
> retain MCP. Il resto della sezione descrive la meccanica quando l'interruttore è attivo.

`should_retain_now()` salva 1 turno ogni `retain_every_n_turns` (3): turni 1-2 → `retain_skip`
`reason=throttling`, turno 3 → salva. Contatore `stop_count` per sessione in
`%TEMP%\hs-retain-state.json`: da ICH-86 avanza una volta per **ogni Stop realmente avvenuto**
— l'entry di coda valutata a UserPromptSubmit più le entry più vecchie della stessa sessione
scartate dal dequeue (`queued_skipped`), e salva quando l'avanzamento attraversa un multiplo di
N — stessa cadenza di prima; **non** avanza nel drain. **Eccezione**: il `--drain` della
sentinella (e `HS_RETAIN_FORCE`) forzano sempre il salvataggio, per catturare la coda della
sessione.

Altri `retain_skip.reason`: `no_transcript`, `no_content`, `gate_uncertain_drain` e
`gate_error_drain` (in drain non c'è nessuno a cui chiedere: uncertain ed errore del gate si
lasciano cadere), `queue_stale` (entry di coda più vecchia di 24 h mai valutata: rimossa con
marker in `hs-retain-failed.log`). Il gate differito gira in un processo detached
(`--queued`) e scrive un outbox: se non finisce entro il budget di pickup dell'hook (6 s) non
si perde nulla — eventi debug `retain_deferred` `carried_over` (l'hook è uscito senza
aspettarlo) e `picked_up` (il prompt successivo ha raccolto l'esito).

---

## 10. Test — `hindsight-check.sh`

La suite diagnostica è `hindsight-check.sh`; `test_hindsight_recall_filter.py` copre inoltre
routing, fail-open, consenso e stato pending senza richiedere il server.

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

# Benchmark provider LLM (retain+recall su corpus dedicato) — vedi §13
ruby hooks/hindsight/benchmark/hindsight_bench.rb
BENCH_ONLY=openai-nano,groq-gptoss20b ruby hooks/hindsight/benchmark/hindsight_bench.rb
```

---

## 12. Memorie MCP salvate in sessione

Nel bank `trinity-project`:

- **(procedures)** La diagnostica end-to-end è `hindsight-check.sh`; i test puri del filtro sono in `test_hindsight_recall_filter.py`.
- **(procedures)** Il benchmark provider è in `hooks/hindsight/benchmark/` (spostato da `test/` il 2026-05-25).

---

## 13. Benchmark provider LLM (velocità/qualità)

**Posizione**: `E:\AI\Claude\Trinity\hooks\hindsight\benchmark\` — spostato da `test/` il 2026-05-25. I path interni sono relativi a `__dir__`, quindi lo script è rilocabile (corpus e risultati vivono accanto al `.rb`).

| File                     | Ruolo                                                                                                                                                                                                                                   |
| ------------------------ | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `hindsight_bench.rb`     | Orchestratore: per ogni provider riavvia il server, fa retain del corpus, recall delle query, misura latenza/token/fatti/hit-rate. Verifica il provider attivo dal log (`verify_active_provider`) e ripristina la produzione a fine run |
| `bench_corpus.json`      | 10 documenti + 6 query (con `expected`/`min_hits` per l'hit-rate)                                                                                                                                                                       |
| `bench_results/<runid>/` | JSON per provider + `summary.csv` + `server_logs/`                                                                                                                                                                                      |
| `hindsight_embed_bench.py` | Benchmark **embedding** (Gemini vs candidati remoti vs bge-m3 locale) a livello vettoriale puro su corpus sintetico IT/EN (MRR, recall@k). NON tocca il bank né Postgres. Lancio: `mise run embed-bench`                              |
| `hindsight_rerank_bench.rb` | Benchmark **reranker** su corpus rank-aware (MRR, recall@k). Ferma/riavvia il server :8888 più volte e lo ripristina alla fine (~5-10 min). Lancio: `mise run rerank-bench`                                                          |
| `hindsight_recall_quality_bench.py` | **Qualità del recall** end-to-end su un bank reale con gold set (`gold_questions.json`): MRR, R@1, R@3. Lancio a mano da `hooks/hindsight/benchmark/`                                                                       |

**Lancio**:

```bash
cd hooks/hindsight/benchmark && ruby hindsight_bench.rb
# o limitato ad alcuni provider:
BENCH_ONLY=openai-nano,groq-gptoss20b ruby hindsight_bench.rb
```

Ripristina automaticamente la produzione alla fine (`openai gpt-4.1-mini`, il LLM globale — solo le variabili LLM; per l'env completo rilanciare `mise run stop-hindsight && mise run start-hindsight`).

**Config Groq nel benchmark** (free tier 8000 TPM): `max_ctok: 4000` — **deve** essere > `RETAIN_CHUNK_SIZE` (default 3000) o il server non parte; `pace_s: 10` — attesa tra chiamate per simulare un uso ravvicinato (sul free tier riattiva di proposito il rate-limit). Su **Dev Tier** rimuovere `pace_s`; `max_ctok` resta 4000.

**Esito chiave (2026-05-25)** — all'epoca restò `gpt-4.1-nano` in produzione (storico: dal 2026-08-09 il retain di produzione è `gpt-5.6-luna` via `openai-responses`, A/B ICH-62):

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

Gemini (1536d, cloud, multilingue) evita il modello di embedding pesante in locale; richiede `GEMINI_API_KEY` nell'env. Il reranker all'epoca era locale; dal 2026-07-27 (sunset ZeroEntropy) in produzione è **`voyage/rerank-2.5`** via provider `litellm-sdk` (`VOYAGE_API_KEY`), con failover RRF (`HINDSIGHT_API_RERANKER_1_PROVIDER = "rrf"`); la riga `RERANKER_LOCAL_MODEL` resta in `mise.toml` ma non è il provider attivo. L'embedding multilingue permette comunque il match cross-lingua (query IT → fatti EN/IT). Verificato end-to-end.

### 14a. Lingua dei fatti generati — servono DUE mission (verificato 2026-05-25)

I fatti escono in inglese anche con input italiano? È colpa delle **mission**, non dell'embedding. Il retain ha **due pipeline distinte** che generano testo, ciascuna con la sua mission (config del bank, impostate da `hindsight-set-mission.sh` via PATCH `/config`):

| Pipeline      | File del pacchetto                 | Genera                 | Mission che la guida   | Direttiva lingua nel prompt?                        |
| ------------- | ---------------------------------- | ---------------------- | ---------------------- | --------------------------------------------------- |
| Extraction    | `engine/retain/fact_extraction.py` | `world` / `experience` | `retain_mission`       | ✅ sì, `LANGUAGE: MANDATORY` (mantieni lingua input) |
| Consolidation | `engine/consolidation/prompts.py`  | `observation`          | `observations_mission` | ❌ **no**                                            |

**Causa del mix EN/IT che si vedeva**: la `retain_mission` era in inglese (bias verso EN su `gpt-4.1-nano`, modello piccolo) e la `observations_mission` era **vuota** → la consolidation usava il suo `_DEFAULT_MISSION` inglese, senza direttiva di lingua → observation sempre in inglese.

**Fix applicata**: entrambe le mission riscritte in italiano in `hindsight-set-mission.sh` (più `observations_mission` aggiunta al PATCH), con direttiva di lingua esplicita. Test A/B live:

- solo `retain_mission` IT → world IT ✅, observation ancora EN ❌
- `retain_mission` + `observations_mission` IT → **tutti i fatti in italiano** ✅✅

NB: è config del bank (DB Postgres), quindi **sopravvive ai `pip upgrade`** del pacchetto. Da rieseguire solo se il bank viene ricostruito.

**GOTCHA — cambiare l'embedding obbliga a ricostruire il bank.** La dimensione dei vettori cambia (es. 384→1024→1536) e il server **rifiuta di partire** se il bank ha dati: `Cannot change embedding dimension from X to Y: memory_units contains N rows`. Rebuild:

1. Postgres embedded in `$HOMEDRIVE$HOMEPATH/.pg0` (drive del profilo Windows, es. C: o D:) — db `hindsight`, user/pass `hindsight`/`hindsight`, porta 5432, `psql.exe` in `installation/18.1.0/bin/` (credenziali in `instances/hindsight-mcp/instance.json`).
2. `TRUNCATE public.memory_units, public.mental_models, public.documents, public.entities, public.entity_cooccurrences, public.memory_links, public.unit_entities, public.chunks, public.async_operations, public.audit_log CASCADE;` (preserva `banks` e `alembic_version`).
3. Riavvia → la migrazione fa `ALTER` della colonna a `vector(<nuova dim>)` sul bank vuoto. Bank benchmark orfani: `DELETE FROM public.banks WHERE bank_id LIKE 'bench-%'`.

Il rebuild **azzera il bank Hindsight** (la memoria file-based è separata e resta intatta).

---

## 15. Command `/hindsight-create-agent` — subagent con memoria isolata

**File**: `commands/hindsight-create-agent.md` (slash command, accanto a `reflect.md`).
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
| Bank                 | Inchiodato nell'URL MCP (`/mcp/trinity-project/`) → non passare `bank_id` ai tool                      |
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

## 16. Interfaccia web (Control Plane) — task mise

> Sessione del 2026-05-26.

Una UI **opzionale** e indipendente dal server MCP, avviata via task mise, **in foreground**
(Ctrl-C; a differenza di `start-hindsight` che è daemon `setsid nohup`).

| UI                | Porta | Avvio                    | Stop                          | Cos'è                                                                                                           |
| ----------------- | ----- | ------------------------ | ----------------------------- | --------------------------------------------------------------------------------------------------------------- |
| **Control Plane** | 9999  | `mise run control-plane` | `mise run stop-control-plane` | Web UI ufficiale Hindsight (Next.js via npx, **non nel repo**). Sfoglia bank/entità/operations, testa recall    |

Per analizzare `hindsight-debug.log` (JSONL) non serve una UI, basta una riga di Nushell:
`nu -c "open logs/hindsight-debug.log | lines | each { from json } | where event == 'recall'"`.

### Architettura Hindsight: 3 servizi

Hindsight è composto da tre servizi (vedi `references/hindsight-docs/.../developer/services.md`):

- **API service** (`hindsight-api`, :8888) — il motore retain/recall/reflect. È quello che avviamo con `start-hindsight`. È il "data plane".
- **Worker** — processore task in background; qui è interno all'API (default, ok per uso singolo).
- **Control Plane** (:9999) — solo la UI. Non ha dati propri: si collega all'API.

### Gotcha d'ambiente Windows/MSYS2 (tutti risolti in `.mise.toml`)

1. **npx del Node MSYS2 è rotto.** `/ucrt64/bin/npx` crasha su qualsiasi pacchetto
   (segfault/`std::bad_weak_ptr`), mentre `node -e` funziona. → Installato Node nativo Windows via
   mise (`[tools] node = "lts"`); dentro un task mise `npx` risolve a quello. Niente Docker su questa
   macchina, quindi l'immagine `hindsight-control-plane` Docker non è un'alternativa.

2. **Bind di Next.js sull'hostname.** Il Control Plane eredita la env `HOSTNAME` (sotto MSYS2 = nome
   macchina, es. `ENWS27719997`) e vi si lega → risponde su `http://ENWS27719997:9999` ma non su
   `localhost`. → Il task forza `HOSTNAME=localhost ... --hostname localhost` (anche per non esporlo
   in LAN: la UI non ha API key di default, vedi `HINDSIGHT_CP_ACCESS_KEY`).

3. **Stop dei processi nativi Windows.** Node è un processo Windows nativo: il `netstat` MSYS
   non vede sempre la sua porta. → Il task `stop-control-plane` usa `$TRINITY_PLUGIN_DIR/hooks/hindsight/ops/kill-port.sh
   <porta> [label]`, che risolve il PID via `Get-NetTCPConnection` (PowerShell 7,
   `C:/Appl/PowerShell/pwsh.exe`) e fa `Stop-Process -Force`.

### Comandi

```bash
# Control Plane (Web UI, :9999)
mise run control-plane          # foreground; → http://localhost:9999
mise run stop-control-plane

# Stop manuale di una porta qualsiasi
bash "$TRINITY_PLUGIN_DIR/hooks/hindsight/ops/kill-port.sh" 9999 control-plane
```

---

## 17. Gate pre-recall (ICH-66) — misurato e scartato

> Valutazione del 2026-08-10 su 100 prompt reali; benchmark rimossi con ICH-97
> (il write-up completo era `hooks/hindsight/benchmark/RECALL_GATE_EVALUATION.md`).

Domanda: conviene un gate LLM prima del recall automatico, per saltare Hindsight
quando il prompt è autosufficiente? **No, non è viabile.**

- Baseline: solo il 47% dei recall restituiva memoria concretamente utile;
  risparmio teorico best-case ~2 s per prompt.
- Gate binario: il candidato migliore (`gpt-5.6-luna` + contesto) perdeva 11
  richiami utili su 47 (~23%) ed era più lento del recall che doveva evitare;
  i modelli veloci ne perdevano 20-38 su 47 (43-81%), l'euristica locale 43 su 47.
- Variante prudente a tre esiti (`recall`/`uncertain`/`skip`): falsi negativi
  quasi azzerati (1 su 47), ma evitava solo l'1% dei recall e aumentava il tempo
  medio del 70% — nessun vantaggio reale.
- Strada promettente alternativa: classificare i risultati DOPO il recall
  (0 utili persi, rumore automatico 4,6%) — è il filone di
  `hindsight_recall_result_filter_bench.py`, che resta in `benchmark/`.
