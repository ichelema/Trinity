#!/usr/bin/env bash
# Benchmark A/B del recall composto (step H mirato) — NON un hook, NON tocca produzione.
# Misura ORA, su scenari fissi, i due lati del tradeoff:
#   Parte A (BENEFICIO): scenari etichettati con keyword intent-specifiche →
#                        precision@K e n_results, bare (OFF) vs composto (ON), sul bank reale.
#   Parte B (COSTO):     stream di prompt simulato con ripetizioni →
#                        cache-hit-rate OFF (key=prompt) vs ON (key=contesto+prompt).
#
# Gli scenari/etichette sono editabili in testa allo script Python: sono un giudizio
# trasparente di rilevanza, non verita' assolute. Uso: bash hindsight-recall-bench.sh
set -euo pipefail

HOOKS_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
export HOOKS_DIR

python - <<'PY'
import json, os, sys, time, urllib.request
sys.path.insert(0, os.path.join(os.environ["HOOKS_DIR"], "..", "lib"))
from hindsight_config import load_config
import hindsight_recall_lib as lib

cfg = load_config()
BASE = cfg["api_url"]
K = cfg["recall_max_results"]

def recall(query):
    body = {"query": query, "budget": cfg["recall_budget"], "max_tokens": cfg["recall_max_tokens"],
            "tags": cfg["recall_tags"], "tags_match": cfg["recall_tags_match"]}
    req = urllib.request.Request(BASE + "/memories/recall",
        data=json.dumps(body).encode(), headers={"Content-Type": "application/json"}, method="POST")
    t0 = time.time()
    with urllib.request.urlopen(req, timeout=20) as r:
        res = json.loads(r.read().decode("utf-8", "replace")).get("results") or []
    return res, (time.time() - t0)

def precision_at_k(results, expected):
    top = results[:K]
    if not top:
        return 0.0, 0
    hit = sum(any(kw in (r.get("text") or "").lower() for kw in expected) for r in top)
    return hit / len(top), hit

# ---- SCENARI ETICHETTATI (giudizio di rilevanza, editabili) -------------------
# context = turno recente plausibile; prompt = corto/referenziale (fa FIRE);
# expected = keyword intent-specifiche che una memoria RILEVANTE dovrebbe contenere.
SCENARIOS = [
    {"context": "Stiamo configurando i mental model di Hindsight come knowledge page, con seed e refresh.",
     "prompt": "e adesso come procedo?",
     "expected": ["mental model", "mental-model", "knowledge page", "refresh", "seed", "pagina"]},
    {"context": "Il retain hook salvava a ogni Stop, abbiamo aggiunto un throttling ogni N turni.",
     "prompt": "come lo verifico questo?",
     "expected": ["throttl", "retain", "stop", "sessionend", "turno", "every", "n turni"]},
    {"context": "Abbiamo centralizzato i parametri degli hook Hindsight in un unico file JSON.",
     "prompt": "qual e' l'approccio migliore qui?",
     "expected": ["config", "json", "hindsight_config", "load_config", "centralizz", "parametr"]},
    {"context": "Python su Windows dava errori di encoding sui caratteri accentati.",
     "prompt": "come lo sistemo adesso?",
     "expected": ["utf-8", "utf8", "pythonutf8", "encoding", "windows", "unicode", "accent", "charmap"]},
    {"context": "L'utente preferisce certi strumenti e linguaggi per gli script di sistema.",
     "prompt": "ricordami queste preferenze",
     "expected": ["ruby", "msys2", "nushell", "script", "preferen", "curl", "bash"]},
    {"context": "Avevamo problemi col provider LLM gratuito e i limiti di token al minuto.",
     "prompt": "e adesso quale conviene?",
     "expected": ["groq", "tpm", "token", "openai", "nano", "openrouter", "tier"]},
]

print("=" * 84)
print("PARTE A — BENEFICIO: precision@%d e n_results, bare (OFF) vs composto (ON)" % K)
print("=" * 84)
print(f"{'scenario (prompt)':<34} | OFF p@K  n | ON p@K  n | fire | Δp@K")
print("-" * 84)
sum_off = sum_on = 0.0
lat_off = lat_on = 0.0
for s in SCENARIOS:
    fire, _ = lib.needs_context(s["prompt"], dict(cfg, recall_compose_enabled=True))
    q_on = lib.compose_query(s["prompt"], s["context"], cfg) if fire else s["prompt"]
    r_off, t_off = recall(s["prompt"])
    r_on, t_on = recall(q_on)
    p_off, h_off = precision_at_k(r_off, s["expected"])
    p_on, h_on = precision_at_k(r_on, s["expected"])
    sum_off += p_off; sum_on += p_on; lat_off += t_off; lat_on += t_on
    print(f"{s['prompt']:<34} | {p_off:>5.2f} {h_off}/{len(r_off[:K])} | {p_on:>4.2f} {h_on}/{len(r_on[:K])} | {'Y' if fire else 'n':^4} | {p_on - p_off:+.2f}")
print("-" * 84)
n = len(SCENARIOS)
print(f"{'MEDIA':<34} | p@K {sum_off / n:>6.2f} | p@K {sum_on / n:>5.2f} | {'':4} | {(sum_on - sum_off) / n:+.2f}")
print(f"latenza media:  OFF {lat_off / n * 1000:.0f}ms   ON {lat_on / n * 1000:.0f}ms")

# ---- PARTE B — COSTO: cache-hit-rate su stream simulato ------------------------
# Stream realistico: prompt sostanziosi (per lo piu' unici) + prompt corti referenziali
# che RICORRONO. Ogni turno ha il testo del turno precedente come "contesto" (per la
# chiave ON). Assunzione ottimistica per OFF: turni entro la TTL della cache (5 min) →
# un prompt gia' visto = HIT. Mostra il limite superiore di cio' che ON perde.
STREAM = [
    "implementa la funzione di parsing del CSV",
    "e adesso come procedo?",
    "aggiungi i test per il parser appena scritto",
    "perche' fallisce?",                       # <20 in realta'? no, 16 -> sotto gate; lo teniamo per realismo del flusso
    "e adesso come procedo?",
    "refactora il modulo di config centralizzato",
    "qual e' l'approccio migliore qui?",
    "scrivi la documentazione della nuova API",
    "e adesso come procedo?",
    "ottimizza la query di recall sul bank",
    "come lo verifico questo?",
    "aggiungi il logging strutturato agli hook",
    "qual e' l'approccio migliore qui?",
    "integra il benchmark nei test esistenti",
    "e adesso come procedo?",
]
MIN = int(cfg["recall_min_prompt_chars"])

def norm(s):  # stessa normalizzazione della cache reale
    return " ".join(s.lower().split())

seen_off, seen_on = set(), set()
hit_off = hit_on = recalled = 0
prev = ""
for p in STREAM:
    ctx = prev
    prev = p
    if len(p) < MIN:
        continue  # sotto il gate: nessun recall, nessuna cache
    recalled += 1
    # OFF: chiave = prompt normalizzato
    koff = norm(p)
    if koff in seen_off:
        hit_off += 1
    seen_off.add(koff)
    # ON: se fire → chiave = composto(contesto+prompt); altrimenti = prompt
    fire, _ = lib.needs_context(p, dict(cfg, recall_compose_enabled=True))
    kon = norm(lib.compose_query(p, ctx, cfg)) if fire else norm(p)
    if kon in seen_on:
        hit_on += 1
    seen_on.add(kon)

print()
print("=" * 84)
print("PARTE B — COSTO: cache-hit-rate su stream simulato (%d prompt, %d sopra il gate)" % (len(STREAM), recalled))
print("=" * 84)
print(f"  OFF (key = prompt)            : {hit_off}/{recalled} hit  ({hit_off / recalled * 100:.0f}%)")
print(f"  ON  (key = contesto+prompt)   : {hit_on}/{recalled} hit  ({hit_on / recalled * 100:.0f}%)")
print(f"  Δ hit persi accendendo ON     : {hit_off - hit_on}  (= recall MISS extra: ~{(hit_off - hit_on)} chiamate di rete/LLM in piu')")
PY
