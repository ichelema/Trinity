#!/usr/bin/env python
"""
Benchmark EMBEDDING (vettoriale puro) per Hindsight: provider candidati messi a
confronto con gemini-embedding-001 (produzione dal 2026-07-27).

A differenza del reranker, valutare un embedding model non richiede ne' Postgres ne' il bank: si misura
a livello di vettori. Per ogni provider: encode(documenti) + encode(query) → coseno → ranking → MRR e
recall@k contro la ground truth (`relevant_ids`). NESSUN rebuild, NESSUNA modifica alla produzione.

Fedelta' alla produzione: i documenti passano da encode_documents() e le query da encode_query(),
esattamente come fa il recall del server (memory_engine usa input_type="query"). Solo il
provider onnx implementa davvero l'asimmetria: per tutti gli altri la classe base fa cadere
encode_query() su encode(), quindi la query viene trattata come un documento.

NB (2026-07-26): fino a hindsight-api 0.8.4 l'input_type si passava al costruttore; dalla 0.8.5
si usano i metodi encode_query/encode_documents. Lo script e' stato aggiornato di conseguenza.

Corpus riusato: bench_corpus_rerank.json (50 doc, 15 query, rank-aware con hard negatives).
I provider senza chiave/dipendenza vengono SALTATI con un avviso (no crash).

Uso: `mise run embed-bench`  (eredita GEMINI_API_KEY dall'[env] del .mise.toml).
"""

import asyncio
import json
import os
import time
from pathlib import Path

import numpy as np

os.environ.setdefault("PYTHONUTF8", "1")

# Corpus configurabile via env (default: il corpus rerank). Per il test ostico:
#   EMBED_BENCH_CORPUS=bench_corpus_embed_hard.json mise run embed-bench
CORPUS = Path(__file__).with_name(
    os.environ.get("EMBED_BENCH_CORPUS", "bench_corpus_rerank.json")
)
KS = (1, 3, 5)


def _l2(mat: np.ndarray) -> np.ndarray:
    norms = np.linalg.norm(mat, axis=1, keepdims=True)
    norms[norms == 0] = 1.0
    return mat / norms


def build_providers():
    """Costruisce i provider disponibili. Ognuno e' (nome, factory_callable, query_aware).
    query_aware=True → le query saranno embeddate con input_type="query".
    Le chiavi/dipendenze mancanti emergono solo a init: gestite nel loop principale con SKIP."""
    from hindsight_api.engine.embeddings import (
        GeminiEmbeddings,
        LiteLLMSDKEmbeddings,
        LocalSTEmbeddings,
        OpenAIEmbeddings,
    )

    providers = []

    # --- Candidati alternativi a gemini-embedding-001 ---------------------------
    # Passano tutti da litellm-sdk (in-process, nessun proxy). Nessuno di questi
    # implementa encode_query asimmetrico: le query finiscono su encode().
    voyage_key = os.environ.get("VOYAGE_API_KEY")
    if voyage_key:
        for vmodel, vdims in (("voyage-4-large", 1024), ("voyage-4", 1024)):
            providers.append(
                (
                    f"{vmodel} ({vdims})",
                    # encoding_format=None obbligatorio: il default "float" di
                    # LiteLLMSDKEmbeddings fa rifiutare la richiesta da Voyage e Jina.
                    lambda m=vmodel, d=vdims: LiteLLMSDKEmbeddings(
                        api_key=voyage_key,
                        model=f"voyage/{m}",
                        output_dimensions=d,
                        encoding_format=None,
                    ),
                    True,
                )
            )
    else:
        print("[skip] voyage: VOYAGE_API_KEY assente")

    jina_key = os.environ.get("JINA_API_KEY") or os.environ.get("JINA_AI_API_KEY")
    if jina_key:
        for jmodel, jdims in (("jina-embeddings-v3", 1024), ("jina-embeddings-v4", 2048)):
            providers.append(
                (
                    f"{jmodel} ({jdims})",
                    lambda m=jmodel: LiteLLMSDKEmbeddings(
                        api_key=jina_key, model=f"jina_ai/{m}", encoding_format=None
                    ),
                    True,
                )
            )
    else:
        print("[skip] jina: JINA_API_KEY assente")

    openai_key = os.environ.get("HINDSIGHT_API_EMBEDDINGS_OPENAI_API_KEY") or os.environ.get(
        "OPENAI_API_KEY"
    )
    if openai_key:
        providers.append(
            (
                "text-embedding-3-large (1536)",
                lambda: OpenAIEmbeddings(
                    api_key=openai_key, model="text-embedding-3-large", dimensions=1536
                ),
                True,
            )
        )
    else:
        print("[skip] openai: OPENAI_API_KEY assente")

    gemini_key = os.environ.get(
        "HINDSIGHT_API_EMBEDDINGS_GEMINI_API_KEY"
    ) or os.environ.get("GEMINI_API_KEY")
    if gemini_key:
        providers.append(
            (
                "gemini-embedding-001 (1536, PROD)",
                lambda: GeminiEmbeddings(
                    model="gemini-embedding-001",
                    api_key=gemini_key,
                    output_dimensionality=1536,
                ),
                False,
            )
        )
        # gemini-embedding-2: a giugno 2026 era inutilizzabile (restituiva 1 vettore
        # per N input, rompendo il batching di hindsight). Ri-verificato il 2026-07-27
        # con hindsight-api 0.8.5: allineamento 1:1 corretto, quindi torna in gara.
        # NB: il nome "gemini-embedding-002" NON esiste (404), e' "gemini-embedding-2".
        providers.append(
            (
                "gemini-embedding-2 (1536)",
                lambda: GeminiEmbeddings(
                    model="gemini-embedding-2",
                    api_key=gemini_key,
                    output_dimensionality=1536,
                ),
                True,
            )
        )
    else:
        print("[skip] gemini: GEMINI_API_KEY assente")

    # bge-m3 locale: pesante (scarica ~2GB e carica torch). Opt-in via EMBED_BENCH_LOCAL=1.
    if os.environ.get("EMBED_BENCH_LOCAL", "0").lower() in ("1", "true", "yes"):
        providers.append(
            (
                "bge-m3 (1024, locale)",
                lambda: LocalSTEmbeddings(model_name="BAAI/bge-m3", force_cpu=True),
                False,
            )
        )
    else:
        print(
            "[skip] bge-m3 locale: imposta EMBED_BENCH_LOCAL=1 per includerlo (scarica ~2GB)"
        )

    return providers


def evaluate(doc_vecs: np.ndarray, query_vecs: np.ndarray, doc_ids, queries) -> dict:
    """Coseno query→doc, ranking, MRR + recall@k contro relevant_ids."""
    sims = _l2(query_vecs) @ _l2(doc_vecs).T  # (n_query, n_doc), coseno
    id_to_col = {doc_id: i for i, doc_id in enumerate(doc_ids)}

    rr_sum = 0.0
    recall_hits = {k: 0 for k in KS}
    for qi, q in enumerate(queries):
        order = np.argsort(-sims[qi])  # indici doc per similarita' decrescente
        ranked_ids = [doc_ids[i] for i in order]
        relevant = set(q["relevant_ids"])
        # Rank (1-based) del primo rilevante.
        rank = next(
            (pos for pos, did in enumerate(ranked_ids, start=1) if did in relevant),
            None,
        )
        if rank:
            rr_sum += 1.0 / rank
        for k in KS:
            if relevant & set(ranked_ids[:k]):
                recall_hits[k] += 1

    n = len(queries)
    return {
        "mrr": rr_sum / n,
        **{f"recall@{k}": recall_hits[k] / n for k in KS},
        "dim": doc_vecs.shape[1],
    }


def main() -> int:
    corpus = json.loads(CORPUS.read_text(encoding="utf-8"))
    documents = corpus["documents"]
    queries = corpus["queries"]
    doc_ids = [d["id"] for d in documents]
    doc_texts = [d["content"] for d in documents]
    query_texts = [q["query"] for q in queries]

    print(f"Corpus: {len(documents)} doc, {len(queries)} query — {CORPUS.name}\n")

    providers = build_providers()
    if not providers:
        print("\nNessun provider disponibile. Imposta almeno una chiave e riprova.")
        return 1

    rows = []
    for name, factory, query_aware in providers:
        print(f"=== {name} ===")
        try:
            emb = factory()
            t0 = time.perf_counter()
            asyncio.run(emb.initialize())
            t_init = time.perf_counter() - t0

            # Documenti: encode_documents(), come il retain lato server.
            t0 = time.perf_counter()
            dv = np.array(emb.encode_documents(doc_texts), dtype=float)
            t_docs = time.perf_counter() - t0

            # Query: encode_query() e' quello che usa davvero il recall. Sui provider
            # simmetrici la classe base fa cadere entrambi su encode(), quindi il flag
            # cambia qualcosa solo per i provider asimmetrici (oggi solo onnx).
            encode_q = emb.encode_query if query_aware else emb.encode_documents
            t0 = time.perf_counter()
            qv = np.array(encode_q(query_texts), dtype=float)
            t_q = time.perf_counter() - t0

            metrics = evaluate(dv, qv, doc_ids, queries)
            metrics.update(
                name=name,
                init_s=round(t_init, 2),
                docs_s=round(t_docs, 2),
                query_s=round(t_q, 2),
            )
            rows.append(metrics)
            print(
                f"  dim={metrics['dim']} MRR={metrics['mrr']:.3f} "
                + " ".join(f"R@{k}={metrics[f'recall@{k}']:.2f}" for k in KS)
                + f" | init={metrics['init_s']}s docs={metrics['docs_s']}s query={metrics['query_s']}s\n"
            )
        except Exception as e:  # noqa: BLE001 - vogliamo continuare con gli altri provider
            print(f"  ERRORE ({type(e).__name__}): {e}\n")

    if not rows:
        print("Nessun provider ha completato il benchmark.")
        return 1

    # Tabella riassuntiva ordinata per MRR.
    rows.sort(key=lambda r: r["mrr"], reverse=True)
    print("\n=== RIEPILOGO (ordinato per MRR) ===")
    header = (
        f"{'provider':<42}{'dim':>5}{'MRR':>8}"
        + "".join(f"{'R@' + str(k):>7}" for k in KS)
        + f"{'docs_s':>8}{'query_s':>9}"
    )
    print(header)
    print("-" * len(header))
    for r in rows:
        print(
            f"{r['name']:<42}{r['dim']:>5}{r['mrr']:>8.3f}"
            + "".join(f"{r[f'recall@{k}']:>7.2f}" for k in KS)
            + f"{r['docs_s']:>8.2f}{r['query_s']:>9.2f}"
        )

    # Salva JSON in bench_results/.
    out_dir = Path(__file__).with_name("bench_results")
    out_dir.mkdir(exist_ok=True)
    out_file = out_dir / f"embed_{time.strftime('%Y%m%d_%H%M%S')}.json"
    out_file.write_text(
        json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(f"\nRisultati salvati in {out_file}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
