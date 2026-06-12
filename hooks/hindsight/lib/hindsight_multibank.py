"""Recall multi-bank: fan-out parallelo sui bank + fusione con rerank globale.

Usato da hindsight-recall.sh quando recall_bank_urls() risolve piu' di un bank
(es. progetto + core). Pipeline:
  1. fan_out_recall: POST /memories/recall su ogni bank IN PARALLELO (thread),
     ~recall_per_bank_candidates risultati per bank
  2. dedup_results: scarta i duplicati esatti di testo tra bank
  3. zerank_rerank: rerank GLOBALE via ZeroEntropy REST (zerank-2) — gli score
     dei singoli bank NON sono confrontabili tra loro, il rerank unico li
     ricalibra sulla query. Stesso provider del reranker interno del server
     (ZEROENTROPY_API_KEY), nessuna esposizione privacy nuova.
  4. fallback: se ZeroEntropy non risponde, interleave() alterna i risultati
     dei bank (round-robin) senza rerank. MAI sollevare verso il hook.

Con un solo bank risolto il chiamante salta tutto questo e fa la singola POST
di sempre (zero latenza aggiunta nel caso comune).
"""

from __future__ import annotations

import json
import os
import threading
import urllib.error
import urllib.request

ZEROENTROPY_RERANK_URL = "https://api.zeroentropy.dev/v1/models/rerank"


def fetch_bank_results(url: str, payload: dict, timeout: float) -> list[dict]:
    """POST /memories/recall su un singolo bank. Lista vuota su qualsiasi errore
    (bank assente, server giu', timeout): un bank irraggiungibile non deve
    azzerare il recall degli altri."""
    req = urllib.request.Request(
        url + "/memories/recall",
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as res:
            data = json.loads(res.read().decode("utf-8", errors="replace"))
        return data.get("results") or []
    except Exception:
        return []


def fan_out_recall(
    urls: list[str], payload: dict, timeout: float, per_bank: int
) -> list[list[dict]]:
    """Recall in parallelo su tutti i bank (un thread per bank — sono 2-3, non
    serve un pool). Ritorna le liste per-bank nell'ordine di urls, ognuna cappata
    a per_bank risultati."""
    out: list[list[dict]] = [[] for _ in urls]

    def _work(i: int, url: str) -> None:
        out[i] = fetch_bank_results(url, payload, timeout)[:per_bank]

    threads = [
        threading.Thread(target=_work, args=(i, u), daemon=True)
        for i, u in enumerate(urls)
    ]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout + 1)
    return out


def dedup_results(per_bank: list[list[dict]]) -> list[list[dict]]:
    """Rimuove i duplicati esatti di testo TRA bank (ordine di urls = priorita':
    il primo bank che porta un fatto lo tiene). Dopo una promozione move il fatto
    vive in un solo bank, ma la finestra tra retain e promote puo' duplicare."""
    seen: set[str] = set()
    cleaned: list[list[dict]] = []
    for results in per_bank:
        kept = []
        for r in results:
            key = " ".join((r.get("text") or "").lower().split())
            if key and key not in seen:
                seen.add(key)
                kept.append(r)
        cleaned.append(kept)
    return cleaned


def interleave(per_bank: list[list[dict]], max_n: int) -> list[dict]:
    """Fallback senza rerank: alterna i risultati dei bank (round-robin) cosi'
    nessun bank monopolizza il budget. L'ordine interno per-bank (gia' rerankato
    dal server di quel bank) e' preservato."""
    out: list[dict] = []
    idx = 0
    while len(out) < max_n:
        added = False
        for results in per_bank:
            if idx < len(results):
                out.append(results[idx])
                added = True
                if len(out) >= max_n:
                    break
        if not added:
            break
        idx += 1
    return out


def zerank_rerank(
    query: str,
    results: list[dict],
    model: str = "zerank-2",
    timeout: float = 6,
    api_key: str | None = None,
) -> list[dict]:
    """Rerank globale via ZeroEntropy REST. Riordina `results` per rilevanza
    rispetto a `query` usando gli indici del response. Solleva su errore: il
    chiamante decide il fallback (interleave)."""
    api_key = api_key or os.environ.get("ZEROENTROPY_API_KEY")
    if not api_key:
        raise RuntimeError("ZEROENTROPY_API_KEY non impostata")
    documents = [(r.get("text") or "") for r in results]
    req = urllib.request.Request(
        ZEROENTROPY_RERANK_URL,
        data=json.dumps(
            {"model": model, "query": query, "documents": documents}
        ).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=timeout) as res:
        data = json.loads(res.read().decode("utf-8", errors="replace"))
    ranked = data.get("results") or []
    # results: [{index, relevance_score}, ...] gia' ordinati per score desc;
    # riordina difensivamente e scarta indici fuori range.
    ranked.sort(key=lambda x: x.get("relevance_score", 0), reverse=True)
    return [results[x["index"]] for x in ranked if 0 <= x.get("index", -1) < len(results)]


def multi_recall(
    prompt: str, cfg: dict, urls: list[str], payload: dict
) -> tuple[list[dict], dict]:
    """Orchestrazione completa: fan-out -> dedup -> rerank globale (fallback
    interleave). Ritorna (results fusi, meta per il debug log). Mai solleva."""
    timeout = float(cfg.get("recall_timeout", 6))
    per_bank_cap = int(cfg.get("recall_per_bank_candidates", 5))
    max_n = int(cfg.get("recall_max_results", 8))

    per_bank = fan_out_recall(urls, payload, timeout, per_bank_cap)
    per_bank = dedup_results(per_bank)
    candidates = [r for results in per_bank for r in results]
    meta = {
        "banks": [u.rsplit("/", 1)[-1] for u in urls],
        "per_bank_counts": [len(r) for r in per_bank],
        "merge": "none",
    }
    if not candidates:
        return [], meta
    if len(candidates) <= 1 or len([r for r in per_bank if r]) <= 1:
        # tutto da un bank solo: l'ordine del server e' gia' buono
        meta["merge"] = "single-source"
        return candidates[:max_n], meta
    try:
        merged = zerank_rerank(prompt, candidates, timeout=timeout)
        meta["merge"] = "zerank"
        return merged[:max_n], meta
    except Exception as e:  # noqa: BLE001 — fallback, mai rompere il recall
        meta["merge"] = "interleave-fallback"
        meta["rerank_error"] = f"{type(e).__name__}: {e}"[:200]
        return interleave(per_bank, max_n), meta
