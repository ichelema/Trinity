#!/usr/bin/env python
"""Benchmark di QUALITA' del recall (MRR / R@1 / R@3) su uno o piu' bank Hindsight reali.

Colma un buco del toolkit: hindsight_embed_bench.py misura solo gli embedding a livello
vettoriale su un corpus sintetico; hindsight_bench.rb misura un hit-rate binario per provider.
Nessuno dei due valuta il RECALL completo (retrieval + reranking + observation) di un bank
reale con un gold set e metriche di ranking.

Per ogni (bank, query): POST /memories/recall coi parametri di produzione, poi:
  - rank = posizione 1-based del PRIMO risultato rilevante nei top-K (K = --k, default 3,
    = recall_max_results: il cap e' client-side, lo applichiamo qui).
  - MRR += 1/rank (0 se nessun rilevante nei top-K); R@1 += (rank==1); R@3 += (rank<=K).
Rilevanza: il testo del risultato matcha >= min_hits dei pattern `expected` (regex, IGNORECASE).
Calcola anche una variante SENZA troncamento (rank su tutta la lista) per diagnosticare se il
collo di bottiglia e' il cutoff o il ranking.

Uso:
  PYTHONUTF8=1 python hindsight_recall_quality_bench.py \
      --banks trinity-project
  # --gold default: gold_questions.json accanto a questo script (override con --gold <path>)
NB Windows: path in stile Windows (D:/...).
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import urllib.error
import urllib.request
from datetime import datetime, timezone

# La lib runtime vive in hooks/hindsight/lib/ di questo stesso repo. Path da
# TRINITY_PLUGIN_DIR se presente (env utente), altrimenti risoluzione relativa:
# hooks/hindsight/benchmark/ -> ../../.. = root del repo.
_plugin_dir = os.environ.get("TRINITY_PLUGIN_DIR") or os.path.join(
    os.path.dirname(os.path.abspath(__file__)),
    "..", "..", "..",
)
sys.path.insert(0, os.path.join(_plugin_dir, "hooks", "hindsight", "lib"))
from hindsight_config import load_config

# Parametri di recall RICHIESTI per il test (fedeli alla produzione). Espliciti, non da config,
# cosi' il benchmark resta riproducibile anche se la config cambia.
RECALL_BUDGET = "mid"
RECALL_MAX_TOKENS = 2048
RECALL_TAGS = ["claude-code"]
RECALL_TAGS_MATCH = "any"
RECALL_TYPES = ["observation", "world", "experience"]
RECALL_TIMEOUT = 30


def recall(base: str, bank: str, query: str) -> list[dict]:
    body = {
        "query": query,
        "budget": RECALL_BUDGET,
        "max_tokens": RECALL_MAX_TOKENS,
        "tags": RECALL_TAGS,
        "tags_match": RECALL_TAGS_MATCH,
        "types": RECALL_TYPES,
    }
    req = urllib.request.Request(
        f"{base}/{bank}/memories/recall",
        data=json.dumps(body).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=RECALL_TIMEOUT) as res:
        data = json.loads(res.read().decode("utf-8", "replace"))
    return data.get("results") or []


def is_relevant(text: str, patterns: list[str], min_hits: int) -> bool:
    low = (text or "").lower()
    hits = sum(1 for p in patterns if re.search(p.lower(), low))
    return hits >= max(1, min_hits)


def first_relevant_rank(results: list[dict], q: dict, k: int | None) -> int | None:
    """Rank 1-based del primo risultato rilevante; k=None = nessun troncamento."""
    pool = results if k is None else results[:k]
    for i, r in enumerate(pool, 1):
        if is_relevant(r.get("text", ""), q["expected"], q.get("min_hits", 1)):
            return i
    return None


def bench_bank(base: str, bank: str, queries: list[dict], k: int) -> dict:
    rr = r1 = r3 = 0.0
    found_k = found_any = 0
    n_results = []
    per_query = []
    for q in queries:
        try:
            res = recall(base, bank, q["query"])
        except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError) as e:
            print(f"  [{bank}] {q['id']} ERRORE recall: {e}", file=sys.stderr)
            res = []
        n_results.append(len(res))
        rank_k = first_relevant_rank(res, q, k)
        rank_full = first_relevant_rank(res, q, None)
        if rank_k:
            rr += 1.0 / rank_k
            found_k += 1
            if rank_k == 1:
                r1 += 1
            if rank_k <= 3:
                r3 += 1
        if rank_full:
            found_any += 1
        per_query.append(
            {
                "id": q["id"],
                "rank_topk": rank_k,
                "rank_full": rank_full,
                "n_results": len(res),
            }
        )
        print(
            f"  [{bank}] {q['id']}: rank@{k}={rank_k} rank_full={rank_full} n={len(res)}"
        )
    n = len(queries)
    return {
        "bank": bank,
        "queries": n,
        "k": k,
        "MRR": round(rr / n, 4),
        "R@1": round(r1 / n, 4),
        "R@3": round(r3 / n, 4),
        "found_in_topk": found_k,
        "found_anywhere": found_any,
        "avg_results": round(sum(n_results) / n, 2),
        "per_query": per_query,
    }


def main() -> int:
    ap = argparse.ArgumentParser(
        description="Benchmark MRR/R@1/R@3 del recall su bank Hindsight."
    )
    ap.add_argument(
        "--gold",
        default=os.path.join(
            os.path.dirname(os.path.abspath(__file__)), "gold_questions.json"
        ),
    )
    ap.add_argument("--banks", default="trinity-project,Bank_test1,Bank_test2")
    ap.add_argument(
        "--k", type=int, default=3, help="cutoff = recall_max_results (default 3)"
    )
    ap.add_argument("--out-dir", default=None)
    args = ap.parse_args()

    cfg = load_config()
    base = cfg["api_url"].rstrip("/").rsplit("/", 1)[0]  # .../banks
    gold = json.load(open(args.gold, encoding="utf-8"))
    queries = gold["queries"]
    banks = [b.strip() for b in args.banks.split(",") if b.strip()]

    print(f"Gold: {os.path.basename(args.gold)} | {len(queries)} query | K={args.k}")
    print(f"Base: {base}\nBanks: {banks}\n")

    results = []
    for bank in banks:
        print(f"=== {bank} ===")
        results.append(bench_bank(base, bank, queries, args.k))
        print()

    # Tabella riassuntiva
    print("=" * 78)
    print(
        f"{'bank':<20}{'MRR':>8}{'R@1':>8}{'R@3':>8}{'found@K':>10}{'found_any':>11}{'avg_n':>8}"
    )
    print("-" * 78)
    for r in results:
        print(
            f"{r['bank']:<20}{r['MRR']:>8.3f}{r['R@1']:>8.3f}{r['R@3']:>8.3f}"
            f"{r['found_in_topk']:>7}/{r['queries']:<2}{r['found_anywhere']:>8}/{r['queries']:<2}{r['avg_results']:>8.1f}"
        )
    print("=" * 78)

    run_id = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    out_dir = args.out_dir or os.path.join(
        os.path.dirname(os.path.abspath(__file__)),
        "bench_results",
        f"recall_quality_{run_id}",
    )
    os.makedirs(out_dir, exist_ok=True)
    with open(os.path.join(out_dir, "results.json"), "w", encoding="utf-8") as f:
        json.dump(
            {"gold": os.path.basename(args.gold), "k": args.k, "banks": results},
            f,
            ensure_ascii=False,
            indent=2,
        )
    cols = [
        "bank",
        "MRR",
        "R@1",
        "R@3",
        "found_in_topk",
        "found_anywhere",
        "avg_results",
    ]
    csv = [",".join(cols)] + [",".join(str(r[c]) for c in cols) for r in results]
    with open(os.path.join(out_dir, "summary.csv"), "w", encoding="utf-8") as f:
        f.write("\n".join(csv) + "\n")
    print(f"\nRisultati in: {out_dir}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
