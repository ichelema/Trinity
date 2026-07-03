# Piano — Adozione `min_scores` / `RecallScores` (hindsight-api 0.8.4) nel recall di Trinity

> Destinatario: modello esecutore. Il piano è ordinato per fasi incrementali e
> indipendentemente verificabili. Ogni modifica cita file:line reali (verificati il
> 2026-07-02 contro il codice installato/nel repo). **Mostrare il diff proposto e
> farlo validare dall'utente prima di ogni Edit/Write** (regola di progetto).

---

## 0. Contesto verificato (NON dare per scontato, è già stato controllato)

### 0.1 La feature è già disponibile
`hindsight-api` **0.8.4** è installato e include la feature (`pip show hindsight-api`
→ 0.8.4). Classi presenti in:
`E:/msys64/home/Sphynx/.local/share/mise/installs/python/3.13.13/Lib/site-packages/hindsight_api/`
- `engine/response_models.py:175-196` → `class RecallScores` (campi `final`, `reranker`, `semantic`, `keyword`).
- `engine/response_models.py:199-213` → `class MinScores` (campi `semantic`, `keyword`, `reranker`, `final`, tutti `float|None`, default `None`).
- `api/http.py:317-325` → `RecallRequest.min_scores: MinScores | None`.
- Endpoint reale: **`POST /v1/default/banks/{bank_id}/memories/recall`** (`api/http.py:3815`).
- Ogni risultato torna con campo `scores` (`api/http.py:381`; JSON: `results[i]["scores"]["reranker"]`).

### 0.2 Come funziona OGGI il recall in Trinity
- HTTP via **stdlib `urllib.request`** (non MCP, non requests).
- Payload costruito da `build_recall_payload` — `hooks/hindsight/lib/hindsight_recall_lib.py:134-161`.
- **Due rami** in `hooks/hindsight/hindsight-recall.sh`:
  - **single-bank** (`len(bank_urls) == 1`, righe 96-109): POST inline diretta; **nessun rerank client, nessuna soglia**.
  - **multi-bank** (`else`, righe 110-114): `multi_recall(...)` → fan-out → dedup → rerank **globale** ZeroEntropy `zerank-2` client-side (`hindsight_multibank.py:107-151`) con soglia `recall_min_rerank_score`.
- Config attuale (`hindsight.config.json:13-27`): `recall_min_rerank_score: 0.5` ATTIVO (agisce solo nel ramo multi-bank).
- Whitelist config = le chiavi presenti in `DEFAULTS` (`hindsight_config.py:35-168`); il merge applica solo chiavi già note (`hindsight_config.py:231-237`). **Per aggiungere una chiave config basta aggiungerla ai DEFAULTS.**

### 0.3 Il server Trinity rerankea già con zerank-2
`mise.toml` configura il reranker del server: `HINDSIGHT_API_RERANKER_PROVIDER = "zeroentropy"`,
`HINDSIGHT_API_RERANKER_ZEROENTROPY_MODEL = "zerank-2"`. Quindi il server, per ogni recall
single-bank, **già fa un rerank cross-encoder** e può filtrarlo con `min_scores.reranker`.
Nel ramo multi-bank Trinity fa un **secondo** rerank client-side per fondere più bank.

> ⚠️ `scores.reranker` è `null` se il bank gira in modalità passthrough (rrf/interleave).
> La Fase 0.4 verifica empiricamente che con la config attuale NON sia null.

### 0.4 GATE EMPIRICO — eseguire PRIMA di scrivere codice
Fare un recall di prova e ispezionare il JSON per confermare (a) il nome/forma del campo
`scores`, (b) che `reranker`/`semantic`/`keyword` non siano tutti null:

```bash
cd E:/AI/Claude/Trinity
# assicurarsi che il server sia su (porta 8888). Bank di prova: trinity-project.
curl -s -X POST "http://127.0.0.1:8888/v1/default/banks/trinity-project/memories/recall" \
  -H "Content-Type: application/json" \
  -d '{"query":"hindsight versione control plane","budget":"mid","max_tokens":2048,"tags":["claude-code"],"tags_match":"any","types":["observation","world","experience"]}' \
  | "$HOME/.local/bin/nu" -c 'from json | get results | select text scores | first 5'
```
- Se il download curl fallisce per TLS su PC aziendale, NON serve `--cacert` (endpoint locale http).
- **Decisione dal risultato**: se `scores.reranker` è valorizzato → Fase 3 (opt reranker) e log-reranker sono utili. Se è `null` → limitarsi ai floor `semantic`/`keyword` e loggare solo quelli.

---

## Riepilogo delle 3 ottimizzazioni → fasi

| # | Ottimizzazione | Fasi | Rischio |
|---|---|---|---|
| A | Floor `semantic`/`keyword` pre-fusione (pota candidati prima di zerank) | 1 + 2 | basso |
| B | Arricchire debug log con i `RecallScores` per-stadio | 1 + 4 | basso |
| C | Delegare il filtro reranker/final al server nel ramo single-bank | 1 + 2 + 3 | medio |
| (D) | (avanzata/opzionale) rimuovere il doppio rerank client-side usando `scores.reranker` per il merge cross-bank | 6 | alto — solo se B/C confermano affidabilità |

La dashboard (`hooks/hindsight/hindsight-dashboard`) **non va toccata**: mostra già `data`/`raw`
completo nel dettaglio riga (`app.rb:130`, `app.js:182-215,244`). Colonna dedicata = solo se lo si vuole (Fase 5, opzionale).

---

## FASE 1 — Config: nuove chiavi `min_scores` (fondamenta di A, B, C)

**File 1a:** `hooks/hindsight/lib/hindsight_config.py`, dentro `DEFAULTS` accanto alle altre
chiavi recall (dopo la riga 82, `recall_min_rerank_score`). Aggiungere:

```python
    # --- Floor per-stadio passati al server (hindsight-api >=0.8.4, min_scores) ---
    # Tutti None = nessun filtro (default sicuro). Agiscono nel payload di recall,
    # quindi valgono per ENTRAMBI i rami (single- e multi-bank).
    #   semantic/keyword = cutoff retrieval-level (pre-fusione, dentro le SQL arms)
    #   reranker/final   = filtri post-rerank server-side
    # NB: distinto da recall_min_rerank_score, che filtra il rerank GLOBALE client-side
    # (zerank-2) usato solo per fondere piu' bank.
    "recall_min_semantic": None,
    "recall_min_keyword": None,
    "recall_min_reranker": None,
    "recall_min_final": None,
```

**File 1b:** `hindsight.config.json` — aggiungere le chiavi (partenza conservativa: tutte
`null`, si tarano dopo con dati reali). Inserire dopo la riga 18 (`recall_min_rerank_score`):

```json
  "recall_min_semantic": null,
  "recall_min_keyword": null,
  "recall_min_reranker": null,
  "recall_min_final": null,
```

**Verifica Fase 1:**
```bash
cd E:/AI/Claude/Trinity
"$HOME/.local/share/mise/installs/python/3.13.13/python.exe" -c "import sys; sys.path.insert(0,'hooks/hindsight/lib'); import hindsight_config as c; cfg=c.load_config('hindsight.config.json'); print({k:cfg[k] for k in ('recall_min_semantic','recall_min_keyword','recall_min_reranker','recall_min_final')})"
```
Atteso: le 4 chiavi presenti con valore `None`. (Adeguare il nome della funzione di load a
quello reale nel file — verificare l'API pubblica di `hindsight_config.py`.)

---

## FASE 2 — Payload: passare `min_scores` al server (attiva A e C)

**File:** `hooks/hindsight/lib/hindsight_recall_lib.py`, funzione `build_recall_payload`
(righe 134-161). Aggiungere, prima del `return payload`, la costruzione condizionale di
`min_scores` (omesso del tutto se tutti i floor sono None → nessun cambiamento di comportamento
finché la config resta a null):

```python
    ms = {
        "semantic": cfg.get("recall_min_semantic"),
        "keyword": cfg.get("recall_min_keyword"),
        "reranker": cfg.get("recall_min_reranker"),
        "final": cfg.get("recall_min_final"),
    }
    ms = {k: v for k, v in ms.items() if v is not None}
    if ms:
        payload["min_scores"] = ms
```

Note per l'esecutore:
- Il payload è **condiviso** da entrambi i rami (single-bank inline a `hindsight-recall.sh:98-103`
  e multi-bank via `fan_out_recall`), quindi questa singola modifica copre A e C insieme.
- Nel ramo multi-bank i floor server-side agiscono **prima** del rerank globale client-side:
  sono additivi (AND), riducono i candidati mandati a zerank-2 → meno costo/latenza ZeroEntropy.
- Interazione con `recall_min_rerank_score` (client, 0.5): restano indipendenti. Se in futuro si
  vuole spostare tutto sul server, vedi Fase 6.

**Verifica Fase 2:**
1. Con config a null → `min_scores` NON presente nel payload (comportamento invariato). Test unit:
   costruire `build_recall_payload("q", cfg, ts)` e assertare `"min_scores" not in payload`.
2. Impostare temporaneamente `recall_min_semantic: 0.4` in un cfg di test → assertare
   `payload["min_scores"] == {"semantic": 0.4}`.
3. Recall reale con `recall_min_semantic` valorizzato e `debug_log` attivo: verificare che il
   numero di risultati diminuisca in modo sensato (i match deboli spariscono) e che il recall non
   torni vuoto (attenzione: soglia troppo alta → 0 risultati).

---

## FASE 3 — (Opt C) Soglia reranker anche nel single-bank

Nessuna modifica di codice aggiuntiva oltre la Fase 2: impostando `recall_min_reranker`
(es. `0.5`) in `hindsight.config.json`, il payload lo invia e **il server filtra il ramo
single-bank** — che oggi non ha alcuna soglia. Questo chiude la lacuna nota (documentata in
`hindsight_config.py:76-82`: "in single-bank l'hook fa la POST diretta e NON applica la soglia").

Solo procedere se il GATE 0.4 ha confermato `scores.reranker` non-null.

**Cautela obbligatoria:** gli autori upstream avvisano che lo score del cross-encoder NON è
calibrato cross-query ("a clearly-relevant match can score ~0.001 even though it is ranked
first"). Tarare la soglia su dati reali (fare 5-10 recall rappresentativi, guardare la
distribuzione di `scores.reranker` nel log della Fase 4) prima di fissare un valore. Partire
basso (es. 0.1-0.2) e alzare con prudenza.

**Verifica Fase 3:** una query nota che oggi restituisce risultati rumorosi in single-bank →
con `recall_min_reranker` tarato, i risultati sotto soglia spariscono; una query buona continua
a restituire i suoi risultati.

---

## FASE 4 — (Opt B) Debug log arricchito con i `RecallScores`

**File:** `hooks/hindsight/hindsight-recall.sh`, blocco `memories=[...]` (righe 136-145).
Estendere ogni memoria loggata con i punteggi per-stadio provenienti dal server (campo `scores`).
Mantenere retro-compatibilità: `score` (client `_rerank_score`) resta com'è; si aggiunge un
oggetto `scores` server-side quando presente.

Diff proposto (sostituire il dict di comprehension attuale):

```python
    memories=[
        {
            "type": r.get("type", "?"),
            "text": (r.get("text") or "").strip()[:300],
            "entities": r.get("entities") or [],
            # punteggio del rerank GLOBALE client-side (solo ramo multi-bank)
            **({"score": round(r["_rerank_score"], 3)}
               if r.get("_rerank_score") is not None else {}),
            # punteggi per-stadio del server (hindsight-api >=0.8.4); presenti in
            # entrambi i rami perche' arrivano dalla response del bank
            **({"scores": {k: (round(v, 3) if isinstance(v, (int, float)) else v)
                            for k, v in r["scores"].items()}}
               if isinstance(r.get("scores"), dict) else {}),
        }
        for r in results[:_max_results]
    ],
```

**Far passare anche i meta della soglia** (oggi scartati). File stesso, riga 134, il
dict-unpacking filtra `merge_meta` alle sole chiavi `("merge", "rerank_error")`. Aggiungere le
chiavi utili:

```python
    **{k: v for k, v in merge_meta.items()
       if k in ("merge", "rerank_error", "min_score", "min_score_filtered", "per_bank_counts") and v not in (None, "")},
```

Note per l'esecutore:
- Nel ramo multi-bank `zerank_rerank` fa `r = dict(results[idx])` (shallow copy) e aggiunge
  `_rerank_score` **senza** rimuovere `scores`: quindi `r["scores"]` (dal server) sopravvive e
  può essere loggato accanto a `_rerank_score`. Verificare in `hindsight_multibank.py:148-149`.
- Nel ramo single-bank i result vengono dal server con `scores` già dentro → loggati direttamente.
- La cache (`hindsight-recall.sh:115-120`) serializza `data["results"]` con `json.dump`: `scores`
  essendo parte del result persiste in cache come già accade per `_rerank_score`.

**Verifica Fase 4:**
1. Recall single-bank fresco → nel log JSONL ogni memoria ha `scores.{final,reranker,semantic,keyword}`.
2. Recall multi-bank fresco → ogni memoria ha sia `score` (client) sia `scores` (server), e la
   riga porta `min_score`/`min_score_filtered`.
3. Aprire la dashboard (`mise run dashboard`, porta 9292) e confermare che i nuovi campi
   compaiono nel dettaglio riga **senza** modifiche alla dashboard.

---

## FASE 5 — Test (aggiornare `hindsight-check.sh`)

**File:** `hooks/hindsight/tools/hindsight-check.sh`, blocco `MB_LIB` test soglia (righe 657-668).

1. Estendere il mock di `zerank_rerank` (già presente) perché conservi un `scores` fittizio sul
   result, così il test del logging può verificarne la propagazione.
2. Aggiungere un test unit per `build_recall_payload` (nuovo, in una sezione dedicata o nel blocco
   Python esistente): assertare che con config null NON compaia `min_scores`, e che con
   `recall_min_semantic=0.4` compaia `payload["min_scores"] == {"semantic": 0.4}`.
3. Se si tocca il logging: un test che chiama `debug_log` con un result mock che ha `scores` e
   verifica che la riga JSONL prodotta contenga i 4 sotto-campi.

**Verifica Fase 5:** `bash hooks/hindsight/tools/hindsight-check.sh` → tutto verde (nessun `ko`).

---

## FASE 6 — (Opzionale, avanzata, ALTO rischio) eliminare il doppio rerank client-side

Solo dopo Fasi 1-5 stabili e dopo aver osservato (nei log Fase 4) che `scores.reranker` del server
è **normalizzato 0-1 e comparabile tra bank diversi**.

Idea: nel ramo multi-bank, invece di rifare il rerank ZeroEntropy client-side su tutti i
candidati (`zerank_rerank` in `hindsight_multibank.py`), fondere i candidati dei vari bank
ordinandoli per `scores.reranker` (o `scores.final`) già restituito dal server, applicando la
soglia via `recall_min_reranker` server-side. Vantaggio: elimina una chiamata REST a ZeroEntropy
per ogni recall multi-bank (costo/latenza). Rischio: gli score potrebbero non essere davvero
comparabili tra bank (calibrazione), causando merge peggiore.

Passi:
1. In `multi_recall` (`hindsight_multibank.py:154-199`): se i candidati hanno `scores.reranker`
   valorizzato, saltare `zerank_rerank` e ordinare per `r["scores"]["reranker"]` (desc),
   troncando a `max_n`. Mantenere `zerank_rerank` come fallback se `scores` assente.
2. Deprecare gradualmente `recall_min_rerank_score` (client) a favore di `recall_min_reranker`
   (server), oppure mantenerlo come override.
3. Aggiornare i test.

**Verifica Fase 6:** A/B su un set di query rappresentative: confrontare i top-3 risultati
prima/dopo. Procedere solo se la qualità è pari o migliore. Misurare la riduzione di chiamate a
ZeroEntropy.

---

## Ordine di esecuzione consigliato e commit atomici

1. **Fase 0.4** (gate empirico) — nessun commit, solo osservazione. Decide la fattibilità di C/D.
2. **Fase 1** → commit `feat(hindsight): chiavi config min_scores (retrieval/post-rerank floors)`.
3. **Fase 2** → commit `feat(hindsight): inoltra min_scores al server nel payload di recall`.
4. **Fase 4** → commit `feat(hindsight): logga i RecallScores per-stadio nel debug log`.
5. **Fase 5** → commit `test(hindsight): copre min_scores nel payload e nel log`.
6. **Fase 3** — solo config (tarare `recall_min_reranker`/`recall_min_semantic` su dati reali) →
   commit `chore(hindsight): attiva floor min_scores tarati`.
7. **Fase 6** — ramo separato, solo se giustificato.

Regole di progetto da rispettare durante l'esecuzione:
- Preview del diff + validazione utente prima di ogni Edit/Write.
- Modifiche chirurgiche: toccare solo le righe citate; nessun refactor collaterale.
- Backup `.bak` prima di sovrascrivere file esistenti se si usa Write (con Edit non serve).
- Niente push automatico: chiedere conferma.
- `mise.toml` ha già il pin control-plane 0.8.4 non committato: NON mescolarlo con questi commit
  (committarlo a parte o lasciarlo all'utente).

## File toccati (mappa rapida)

| File | Fase | Cosa |
|---|---|---|
| `hooks/hindsight/lib/hindsight_config.py` | 1 | +4 chiavi in DEFAULTS (dopo :82) |
| `hindsight.config.json` | 1, 3 | +4 chiavi (dopo :18); poi tarate |
| `hooks/hindsight/lib/hindsight_recall_lib.py` | 2 | `build_recall_payload` (:134-161): costruisce `min_scores` |
| `hooks/hindsight/hindsight-recall.sh` | 4 | logging `memories` (:136-145) + meta (:134) |
| `hooks/hindsight/tools/hindsight-check.sh` | 5 | test payload + log (:657-668) |
| `hooks/hindsight/lib/hindsight_multibank.py` | 6 (opz.) | `multi_recall` merge per scores server |
| dashboard | — | nessuna modifica necessaria |
