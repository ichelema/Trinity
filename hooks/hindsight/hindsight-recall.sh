#!/usr/bin/env bash
# UserPromptSubmit hook: recupera memorie rilevanti da Hindsight via REST.
# Cache client-side filesystem-based con TTL 5 min: HIT ~500ms (Python startup +
# read file), MISS ~2.7s (Python + server). Cache key = SHA256(prompt
# normalizzato + bank risolti + fingerprint del payload di filtro), dettagli
# al blocco "Cache lookup" sotto.
# Vedi https://hindsight.vectorize.io/developer/performance — "client-side cache
# raccomandata", hit rate atteso 50-70% su prompt simili.
set -uo pipefail

# Config centralizzata in hindsight.config.json (vedi hindsight_config.py).
HOOKS_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
HOOK_INPUT="$(cat)"
export HOOK_INPUT HOOKS_DIR

. "$HOOKS_DIR/lib/hs-python.sh"

PYTHONUTF8=1 "$HS_PY" <<'PY' 2>/dev/null
import hashlib, json, os, sys, time, urllib.request, urllib.error
from datetime import datetime, timezone

sys.path.insert(0, os.path.join(os.environ["HOOKS_DIR"], "lib"))
from hindsight_config import load_config, recall_bank_urls
from hindsight_debug import debug_log
from hindsight_recall_lib import build_recall_payload
from hindsight_multibank import multi_recall

cfg = load_config()

# Interruttore master: se il recall automatico e' disattivato in config, esci
# prima di toccare cache o rete. Nessun additionalContext iniettato.
if not cfg.get("recall_enabled", True):
    debug_log(cfg, "recall_skip", reason="disabled")
    sys.exit(0)

try:
    hook = json.loads(os.environ["HOOK_INPUT"])
except Exception:
    sys.exit(0)

prompt = (hook.get("prompt") or "").strip()
# Skip prompt brevi: "ok", "si", "continua" ecc. — non valgono il costo del recall.
if len(prompt) < cfg["recall_min_prompt_chars"]:
    debug_log(cfg, "recall_skip", reason="prompt_too_short", prompt_len=len(prompt))
    sys.exit(0)

# Clamp MAX: il recall-embedder rifiuta query > 500 token (HTTP 400). Tronca la
# query (solo quella usata per il recall, non il prompt inviato a Claude) alla
# parte iniziale, che di norma contiene l'istruzione/intento; il resto è incollato.
_max_chars = cfg["recall_max_prompt_chars"]
if len(prompt) > _max_chars:
    debug_log(cfg, "recall_truncate", orig_len=len(prompt), max_chars=_max_chars)
    prompt = prompt[:_max_chars]

# --- Bank di lettura (multi-bank) ---
# Risolti da bank.recall_banks ("auto" = slug del repo del cwd della sessione).
# Con un solo bank il percorso resta la singola POST di sempre; con piu' bank
# si fa fan-out parallelo + fusione (vedi hindsight_multibank.py).
bank_urls = recall_bank_urls(cfg, hook.get("cwd") or None)

# --- Payload di recall (serve anche per la cache key) ---
# Costruito PRIMA della key: i parametri di filtro (types, tags, min_scores,
# budget, cap...) devono entrare nella chiave, altrimenti un loro cambio in
# config entro il TTL riuserebbe una risposta calcolata con la config vecchia.
query_ts = datetime.now(timezone.utc).isoformat()
payload = build_recall_payload(prompt, cfg, query_ts)

# --- Cache lookup ---
cache_dir = cfg["recall_cache_dir"]
cache_ttl = int(cfg["recall_cache_ttl"])
os.makedirs(cache_dir, exist_ok=True)
# Key: prompt normalizzato (case-insensitive, whitespace collassato) + set dei
# bank risolti + fingerprint del payload di filtro. Dal payload si escludono
# 'query' (gia' coperta dal prompt normalizzato) e 'query_timestamp' (volatile:
# romperebbe ogni cache hit). Cosi' un cambio di recall_types/min_scores/tags/
# budget entro il TTL produce una key diversa.
payload_fp = json.dumps(
    {k: v for k, v in payload.items() if k not in ("query", "query_timestamp")},
    sort_keys=True,
    ensure_ascii=False,
)
key_src = " ".join(prompt.lower().split()) + "|" + ",".join(bank_urls) + "|" + payload_fp
cache_key = hashlib.sha256(key_src.encode("utf-8")).hexdigest()[:32]
cache_file = os.path.join(cache_dir, cache_key + ".json")

cached = None
if os.path.exists(cache_file):
    age = time.time() - os.path.getmtime(cache_file)
    if age < cache_ttl:
        try:
            with open(cache_file, "r", encoding="utf-8") as f:
                cached = json.load(f)
        except Exception:
            cached = None

# --- Network call (solo se cache miss) ---
merge_meta = {}  # sempre definito: il debug_log lo usa anche sul ramo cache-hit
if cached is None:
    # Cleanup laziness al miss: rimuovi file scaduti per evitare crescita illimitata.
    # Costa pochi ms (listdir + stat), si paga solo sui miss.
    try:
        cutoff = time.time() - cache_ttl
        for fn in os.listdir(cache_dir):
            fp = os.path.join(cache_dir, fn)
            if os.path.isfile(fp) and os.path.getmtime(fp) < cutoff:
                os.remove(fp)
    except Exception:
        pass
    if len(bank_urls) == 1:
        # Bank singolo: stessa singola POST di sempre, zero overhead multi-bank.
        req = urllib.request.Request(
            bank_urls[0] + "/memories/recall",
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=cfg["recall_timeout"]) as res:
                data = json.loads(res.read().decode("utf-8", errors="replace"))
        except Exception as e:
            debug_log(cfg, "recall_error", query=prompt, error=str(e)[:200])
            sys.exit(0)
    else:
        # Multi-bank: fan-out parallelo -> dedup -> rerank globale zerank-2
        # (fallback interleave). multi_recall non solleva mai.
        merged, merge_meta = multi_recall(prompt, cfg, bank_urls, payload)
        data = {"results": merged}
    # Salva in cache (best-effort, ignora errori).
    try:
        with open(cache_file, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False)
    except Exception:
        pass
else:
    data = cached

results = data.get("results") or []
source = "cache" if cached is not None else "fresh"
# Cap sui risultati iniettati: il multi-bank puo' mostrarne di piu' (piu' fonti).
_max_results = int(cfg.get("recall_max_results_multibank") or cfg["recall_max_results"]) if len(bank_urls) > 1 else cfg["recall_max_results"]
debug_log(
    cfg,
    "recall",
    query=prompt,
    cache=source,
    banks=[u.rsplit("/", 1)[-1] for u in bank_urls],
    **{k: v for k, v in merge_meta.items()
       if k in ("merge", "rerank_error", "min_score", "min_score_filtered", "per_bank_counts")
       and v not in (None, "")},
    n_results=len(results),
    memories=[
        {
            "type": r.get("type", "?"),
            "text": (r.get("text") or "").strip()[:300],
            "entities": r.get("entities") or [],
            # punteggio del rerank GLOBALE client-side (solo ramo multi-bank)
            **({"score": round(r["_rerank_score"], 3)}
               if r.get("_rerank_score") is not None else {}),
            # punteggi per-stadio del server (hindsight-api >=0.8.4); presenti
            # in entrambi i rami perche' arrivano dalla response del bank
            **({"scores": {k: (round(v, 3) if isinstance(v, (int, float)) else v)
                           for k, v in r["scores"].items()}}
               if isinstance(r.get("scores"), dict) else {}),
        }
        for r in results[:_max_results]
    ],
)
if not results:
    sys.exit(0)

lines = []
for r in results[:_max_results]:
    text = (r.get("text") or "").strip()
    if not text:
        continue
    kind = r.get("type", "?")
    ents = ", ".join(r.get("entities") or [])
    lines.append(f"- ({kind}) {text}" + (f"  [entities: {ents}]" if ents else ""))

if not lines:
    sys.exit(0)

context = (
    f"## Hindsight persistent memory (advisory, source: {source})\n\n"
    + "\n".join(lines)
    + "\n\nUse as consultative context. Verify mutable facts against the repo."
)

print(json.dumps({
    "hookSpecificOutput": {
        "hookEventName": "UserPromptSubmit",
        "additionalContext": context,
    }
}, ensure_ascii=False))
PY
