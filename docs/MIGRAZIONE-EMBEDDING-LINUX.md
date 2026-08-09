# Allineamento del PC Linux dopo la migrazione ZeroEntropy → Voyage/Gemini

> Procedura una tantum, da eseguire **sul server Linux**. Scritta il 2026-07-27 subito
> dopo aver completato la migrazione sul PC Windows (PR #4, merge commit `79a6e62`).
> Dopo averla eseguita questo file può essere cancellato.

## Contesto: perché serve

ZeroEntropy è stata acquisita da Notion e spegne i servizi il **4 settembre 2026**.
Forniva sia l'embedding (`zembed-1`, 1280 dim) sia il reranker (`zerank-2`) di Hindsight.
Sul PC Windows sono stati sostituiti con:

| componente | prima | adesso |
|---|---|---|
| embedding | zembed-1 (ZeroEntropy), 1280 dim | **gemini-embedding-001 (Google), 1536 dim** |
| reranker server | zerank-2 (ZeroEntropy) | **voyage/rerank-2.5** via provider `litellm-sdk` |
| rerank globale multi-bank | `zerank_rerank()` su api.zeroentropy.dev | **`global_rerank()`** su api.voyageai.com |

**Il punto critico**: la dimensione del vettore è una proprietà della **tabella**, non del
bank. Il DB di questa macchina ha ancora vettori a 1280 dimensioni; appena il codice
aggiornato chiederà 1536, `_migrate_table_embedding_dimension` solleverà un errore e
**il server non partirà**:

```
RuntimeError: ... table contains N rows with embeddings.
  1. Re-embed all data: DELETE FROM <schema>.<table>; then restart
```

Quindi non basta il `git pull`: serve anche il restore del dump prodotto su Windows,
che contiene già i vettori Gemini a 1536.

**NON rifare la migrazione export/import su questa macchina.** Sarebbe lavoro inutile e
produrrebbe un database divergente da quello Windows. Il flusso corretto è solo:
codice aggiornato + restore del dump.

---

## Prerequisito: il dump giusto

Serve il dump **post-migrazione** prodotto su Windows:

```
hindsight-20260727T012341Z.dump    56 MB    watermark 2026-07-27 00:36:29 UTC
```

Va copiato nella directory di backup di questa macchina (su Linux `~/backups/hindsight/`,
vedi `hooks/hindsight/tools/hs-db-lib.sh`).

⚠️ **Non usare** `hindsight-20260726T230713Z.dump` (45 MB): è il backup *pre*-migrazione,
ha i vettori a 1280 e riporterebbe tutto indietro.

---

## Passo 1 — Aggiornare codice e configurazione

```bash
cd <root del repo Trinity>
git switch master
git pull --ff-only origin master
```

Verifica che siano arrivate le modifiche giuste:

```bash
grep -nE '^HINDSIGHT_API_(EMBEDDINGS_PROVIDER|RERANKER_PROVIDER|RERANKER_LITELLM_SDK_MODEL)' mise.toml
grep -nE 'recall_min_rerank_score|recall_min_reranker' hindsight.config.json
grep -c 'global_rerank\|VOYAGE_RERANK_URL' hooks/hindsight/lib/hindsight_multibank.py
```

Atteso:

```
HINDSIGHT_API_EMBEDDINGS_PROVIDER = "google"
HINDSIGHT_API_RERANKER_PROVIDER = "litellm-sdk"
HINDSIGHT_API_RERANKER_LITELLM_SDK_MODEL = "voyage/rerank-2.5"
"recall_min_rerank_score": 0.6
"recall_min_reranker": 0.4
5      <- occorrenze di global_rerank/VOYAGE_RERANK_URL
```

Se `git pull` fallisce per modifiche pendenti (tipicamente i log degli scheduler),
usare `git stash push`, poi il pull, poi `git stash pop`. **Non** scartare le
modifiche locali senza aver guardato cosa sono.

## Passo 2 — Verificare le due API key

`VOYAGE_API_KEY` è nuova. Ma va controllata **anche `GEMINI_API_KEY`**: era il provider
di embedding fino a maggio 2026, poi sostituito da ZeroEntropy, quindi su questa macchina
potrebbe non esserci più.

```bash
mise env | grep -cE 'VOYAGE_API_KEY|GEMINI_API_KEY'   # atteso: 2
```

Entrambe sono dichiarate nel `mise.toml` con `default(value='')`, quindi **se mancano il
server parte comunque** e fallisce al primo embedding o rerank: un guasto silenzioso.
Vanno impostate nell'ambiente **prima** di riavviare, con il meccanismo già usato su
questa macchina per le altre chiavi (vedi `docs/SETUP-LINUX.md`).

Prova diretta delle chiavi, se serve conferma:

```bash
# Voyage
curl -sS -X POST https://api.voyageai.com/v1/rerank \
  -H "Authorization: Bearer $VOYAGE_API_KEY" -H "Content-Type: application/json" \
  -d '{"model":"rerank-2.5","query":"test","documents":["a","b"]}' \
  -o /dev/null -w '%{http_code}\n'      # atteso: 200

# Gemini
curl -sS -X POST "https://generativelanguage.googleapis.com/v1beta/models/gemini-embedding-001:embedContent?key=$GEMINI_API_KEY" \
  -H "Content-Type: application/json" -d '{"content":{"parts":[{"text":"test"}]}}' \
  -o /dev/null -w '%{http_code}\n'      # atteso: 200
```

## Passo 3 — Controllare il guardrail PRIMA del restore

`hs-db-restore.sh` confronta il `MAX(created_at)` del DB locale con quello del dump e
rifiuta il restore se il database locale è più recente. Il dump ha watermark
**2026-07-27 00:36:29 UTC**.

**Se dopo quel momento sono state fatte sessioni su questa macchina, quelle memorie non
sono nel dump e il restore le cancellerebbe.** Verificare prima:

```bash
PGBIN=$(echo "$HOME"/.pg0/installation/*/bin)
"$PGBIN/psql" "postgresql://hindsight:hindsight@127.0.0.1:5432/hindsight" -tAc \
  "SELECT bank_id, max(created_at) FROM public.memory_units GROUP BY 1 ORDER BY 2 DESC;"
```

- se il massimo è **anteriore** al 2026-07-27 00:36 UTC → procedere tranquillamente
- se è **posteriore** → **fermarsi e segnalarlo all'utente**. Non usare `--force`: si
  perderebbero le memorie create qui. Va prima esportato il delta
  (`hindsight-admin export-bank`) per reinserirlo dopo il restore.

## Passo 4 — Restore

```bash
mise run stop-hindsight
mise run db-restore          # se il dump non è l'ultimo: mise run db-restore -- <file.dump>
```

Lo script fa già un dump di sicurezza del DB locale prima di sovrascrivere, e lavora su
un database temporaneo con swap per rinomina.

## Passo 5 — VACUUM ANALYZE (non saltarlo)

Dopo un restore le statistiche del planner Postgres sono vuote. Su Windows, senza questo
passaggio, il recall stava a **4-9 secondi** contro i 10 di timeout dell'hook: non per
colpa di embedding o reranker, ma del braccio graph a 1,87s. Sei secondi di `ANALYZE`
lo hanno riportato a 0,55s.

```bash
PGBIN=$(echo "$HOME"/.pg0/installation/*/bin)
"$PGBIN/psql" "postgresql://hindsight:hindsight@127.0.0.1:5432/hindsight" -c "VACUUM ANALYZE;"
```

## Passo 6 — Riavviare e verificare la configurazione attiva

```bash
mise run start-hindsight
# attendere che risponda
curl -sS -m 3 -o /dev/null -w '%{http_code}\n' http://127.0.0.1:8888/health   # atteso: 200
grep -aE 'Embeddings: provider=|Embeddings: initializing|Reranker: initializing' /tmp/hs.log | tail -3
```

Atteso nel log:

```
Embeddings: provider=google
Embeddings: initializing Gemini provider with model gemini-embedding-001
Reranker: initializing LiteLLM SDK provider with model voyage/rerank-2.5
```

Se compare `Altering memory_units.embedding column dimension from 1280 to 1536` significa
che il restore **non** ha portato i vettori nuovi: fermarsi e rileggere il Passo 1 sul
dump usato.

## Passo 7 — Verifiche funzionali

Dimensione della colonna e assenza di vettori nulli:

```bash
PGBIN=$(echo "$HOME"/.pg0/installation/*/bin)
URL="postgresql://hindsight:hindsight@127.0.0.1:5432/hindsight"
"$PGBIN/psql" "$URL" -c "
SELECT c.relname, format_type(a.atttypid,a.atttypmod)
FROM pg_attribute a JOIN pg_class c ON c.oid=a.attrelid JOIN pg_namespace n ON n.oid=c.relnamespace
WHERE n.nspname='public' AND c.relkind='r' AND format_type(a.atttypid,a.atttypmod) LIKE 'vector%';"
# atteso: memory_units = vector(1536), mental_models = vector(1536)

"$PGBIN/psql" "$URL" -c "
SELECT bank_id, count(*) AS unita, count(*) FILTER (WHERE embedding IS NULL) AS nulli,
       min(vector_dims(embedding)) AS dim
FROM public.memory_units GROUP BY 1 ORDER BY 1;"
# atteso: nulli=0 e dim=1536 per ogni bank
```

Conteggi attesi per bank (stato del dump):

| bank | documenti | nodi |
|---|---|---|
| trinity-project | 245 | ~2.961 |
| Obsidian_Sinapsi | 49 | ~2.181 |
| Remit_Mappa | 9 | 66 |

I nodi possono crescere leggermente: la consolidation gira in background e crea
observation nuove. `PluginPilot` non c'è più, è stato eliminato durante la migrazione.

Prova di recall reale:

```bash
curl -sS -m 60 -X POST \
  http://127.0.0.1:8888/v1/default/banks/trinity-project/memories/recall \
  -H 'Content-Type: application/json' \
  -d '{"query":"come si avvia e si ferma il server Hindsight","budget":"mid","max_tokens":1500}' \
  | head -c 400
```

Atteso: risultati pertinenti, e nel log del server le fasi con
`[1] Generate query embedding` intorno a 0,25s e `[4] Reranking` intorno a 0,5s.

Suite di diagnostica del progetto:

```bash
PYTHONUTF8=1 bash hooks/hindsight/tools/hindsight-check.sh
# atteso: tutti i check passati (su Windows: 58/58)
```

## Se qualcosa va storto

Il rollback è il restore del dump di sicurezza creato automaticamente al Passo 4, oppure
del proprio backup precedente. Attenzione: tornare a un dump a **1280 dimensioni**
richiede anche di rimettere la configurazione vecchia nel `mise.toml`
(`HINDSIGHT_API_EMBEDDINGS_PROVIDER = "zeroentropy"`), altrimenti il server non parte —
le due cose vanno insieme. NB: la configurazione ZeroEntropy (embedding e reranker) è
stata rimossa del tutto dal `mise.toml` (ICH-64): un rollback richiederebbe di
recuperarla dalla history git, e dopo il 4 settembre 2026 il servizio non esiste più.

## Nota sulle soglie

`recall_min_rerank_score` (0.6) e `recall_min_reranker` (0.4) sono tarate sulla scala di
Voyage, misurata sul bank reale: query pertinenti fra 0.762 e 0.938, query deboli fra
0.447 e 0.563, fuori dominio fra 0.297 e 0.375. Non vanno cambiate senza rifare la
misura, e non sono confrontabili con i valori usati per zerank-2.

`HINDSIGHT_API_SEMANTIC_MIN_SIMILARITY` resta 0.4: con Gemini è di fatto inerte (il
peggior risultato che entra nel recall sta a 0.5087) e alzarla non porta vantaggi
misurabili. Motivazione completa nei commenti del `mise.toml`.
