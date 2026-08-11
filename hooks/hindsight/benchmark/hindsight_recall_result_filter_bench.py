#!/usr/bin/env python
"""Benchmark post-recall: score bypass + classificatore low/medium/high.

I risultati con reranker >= soglia vengono iniettati direttamente. Gli altri
sono classificati in una sola chiamata per prompt: low=scarta, medium=proponi
all'utente, high=inietta. Un secondo giudizio, fuori dal costo di produzione,
misura separatamente l'utilità dei canali automatico e opzionale.
"""

from __future__ import annotations

import argparse
import concurrent.futures
import json
import math
import os
import statistics
import sys
import time
import urllib.request
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
LIB = HERE.parent / "lib"
sys.path.insert(0, str(LIB))
from hindsight_recall_filter import CLASSIFIER_PROMPT, CLASSIFIER_SCHEMA, classifier_input, result_score

OPENAI_URL = "https://api.openai.com/v1/chat/completions"
DEFAULT_MODEL = "gpt-5.6-luna"

CHANNEL_JUDGE_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "automatic_useful": {"type": "boolean"},
        "optional_useful": {"type": "boolean"},
    },
    "required": ["automatic_useful", "optional_useful"],
}

CHANNEL_JUDGE_PROMPT = """Valuta separatamente due gruppi di memorie per il prompt corrente.

automatic_useful=true solo se almeno una memoria automatica contiene informazione specifica e concretamente utile per migliorare, cambiare o rendere più sicura la risposta.
optional_useful=true solo se almeno una memoria opzionale merita davvero di interrompere il flusso e chiedere all'utente se vuole leggerla.

Memorie generiche, tangenziali, ridondanti o sullo stesso strumento ma su un altro problema non sono utili. I due booleani sono indipendenti."""


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-run", type=Path)
    parser.add_argument("--model", default=DEFAULT_MODEL)
    parser.add_argument("--judge-model", default=DEFAULT_MODEL)
    parser.add_argument("--score-field", default="reranker")
    parser.add_argument("--threshold", type=float, default=0.8)
    parser.add_argument("--workers", type=int, default=6)
    parser.add_argument("--output-dir", type=Path)
    return parser.parse_args()


def latest_complete_run() -> Path:
    runs = sorted(
        path.parent
        for path in (HERE / "bench_results").glob("recall_gate_*/results.private.json")
        if "cautious" not in path.parent.name
    )
    if not runs:
        raise RuntimeError("nessun benchmark completo trovato")
    return runs[-1]


def api_json(model: str, system: str, user: str, schema_name: str, schema: dict, timeout: int = 45) -> tuple[dict, float]:
    key = os.environ.get("OPENAI_API_KEY")
    if not key:
        raise RuntimeError("OPENAI_API_KEY non impostata")
    body = {
        "model": model,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        "response_format": {
            "type": "json_schema",
            "json_schema": {"name": schema_name, "schema": schema, "strict": True},
        },
    }
    request = urllib.request.Request(
        OPENAI_URL,
        data=json.dumps(body, ensure_ascii=False).encode("utf-8"),
        headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
        method="POST",
    )
    started = time.perf_counter()
    with urllib.request.urlopen(request, timeout=timeout) as response:
        data = json.loads(response.read().decode("utf-8", "replace"))
    return json.loads(data["choices"][0]["message"]["content"]), (time.perf_counter() - started) * 1000


def classify_results(item: dict, results: list[dict], model: str, score_field: str, threshold: float) -> dict:
    if score_field != "reranker":
        raise ValueError("la produzione supporta solo scores.reranker")
    automatic: list[dict] = []
    candidates: list[tuple[int, dict]] = []
    for index, result in enumerate(results):
        score = result_score(result)
        if score is not None and score >= threshold:
            automatic.append({**result, "route": "bypass", "confidence": "high"})
        else:
            candidates.append((index, result))

    if not candidates:
        return {"automatic": automatic, "optional": [], "discarded": [], "latency_ms": 0.0, "classifier_called": False}

    data, latency = api_json(
        model,
        CLASSIFIER_PROMPT,
        classifier_input(item["prompt"], candidates),
        "recall_result_classification",
        CLASSIFIER_SCHEMA,
    )
    expected = {index for index, _ in candidates}
    classified = {row.get("index"): row for row in data.get("classifications") or [] if row.get("index") in expected}
    if set(classified) != expected:
        raise ValueError("classificazioni mancanti o duplicate")

    optional: list[dict] = []
    discarded: list[dict] = []
    by_index = dict(candidates)
    for index in sorted(expected):
        row = classified[index]
        enriched = {**by_index[index], "route": "classifier", "confidence": row["confidence"], "classifier_reason": row["reason"]}
        if row["confidence"] == "high":
            automatic.append(enriched)
        elif row["confidence"] == "medium":
            optional.append(enriched)
        else:
            discarded.append(enriched)
    return {
        "automatic": automatic,
        "optional": optional,
        "discarded": discarded,
        "latency_ms": round(latency, 2),
        "classifier_called": True,
    }


def memories_block(memories: list[dict]) -> str:
    if not memories:
        return "(nessuna)"
    return "\n".join(f"- ({item.get('type') or '?'}) {(item.get('text') or '')[:3000]}" for item in memories)


def judge_channels(item: dict, routed: dict, model: str) -> dict:
    user = (
        f"## Prompt corrente\n{item['prompt'][:6000]}\n\n"
        f"## Memorie automatiche\n{memories_block(routed['automatic'])}\n\n"
        f"## Memorie opzionali\n{memories_block(routed['optional'])}"
    )
    data, latency = api_json(model, CHANNEL_JUDGE_PROMPT, user, "recall_filter_channels", CHANNEL_JUDGE_SCHEMA)
    return {**data, "latency_ms": round(latency, 2)}


def percentile(values: list[float], p: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    index = (len(ordered) - 1) * p
    low, high = math.floor(index), math.ceil(index)
    if low == high:
        return ordered[low]
    return ordered[low] + (ordered[high] - ordered[low]) * (index - low)


def write_json(path: Path, value: object) -> None:
    with path.open("x", encoding="utf-8") as handle:
        json.dump(value, handle, ensure_ascii=False, indent=2)
    try:
        os.chmod(path, 0o600)
    except OSError:
        pass


def report(summary: dict) -> str:
    return f"""# Benchmark filtro post-recall Hindsight

Data: {summary['generated_at'][:10]}
Classificatore: `{summary['model']}`; score `{summary['score_field']}` >= {summary['threshold']} bypassa il classificatore.

## Risultati

| Misura | Risultato |
|---|---:|
| Prompt | {summary['samples']} |
| Risultati recall totali | {summary['results_total']} |
| Bypass >= soglia | {summary['bypass_results']} ({summary['bypass_results_pct']}%) |
| Classificati `high` | {summary['classified_high']} ({summary['classified_high_pct']}%) |
| Classificati `medium` | {summary['classified_medium']} ({summary['classified_medium_pct']}%) |
| Classificati `low` | {summary['classified_low']} ({summary['classified_low_pct']}%) |
| Prompt con iniezione automatica | {summary['prompts_automatic_pct']}% |
| Prompt con almeno un risultato medium | {summary['prompts_optional_pct']}% |
| Prompt che propongono davvero all'utente (nessun high) | {summary['prompts_prompted_optional_pct']}% |
| Prompt senza memoria iniettata/proposta | {summary['prompts_empty_pct']}% |
| Recall utili conservati automaticamente | {summary['baseline_useful_auto_kept_pct']}% |
| Recall utili disponibili automatici o su richiesta | {summary['baseline_useful_available_pct']}% |
| Recall utili persi | {summary['false_negative_count']} su {summary['baseline_useful_count']} |
| Iniezioni automatiche inutili | {summary['unnecessary_automatic_pct']}% |
| Proposte all'utente inutili | {summary['unnecessary_optional_pct']}% |
| Chiamate classificatore | {summary['classifier_calls']} |
| Classificatore p50 / p95 | {summary['classifier_p50_ms']} / {summary['classifier_p95_ms']} ms |
| Tempo medio produzione stimato | {summary['production_mean_ms']} ms |
| Baseline sempre-inietta | {summary['baseline_mean_ms']} ms |

Il giudice dei canali è usato solo nel benchmark e non entra nella latenza di produzione.
"""


def main() -> int:
    args = parse_args()
    source_run = args.source_run or latest_complete_run()
    source = json.loads((source_run / "results.private.json").read_text(encoding="utf-8"))
    dataset = source["dataset"]

    routed: dict[str, dict] = {}
    with concurrent.futures.ThreadPoolExecutor(max_workers=args.workers) as executor:
        futures = {
            executor.submit(
                classify_results,
                item,
                source["recalls"][item["id"]]["results"],
                args.model,
                args.score_field,
                args.threshold,
            ): item["id"]
            for item in dataset
        }
        for index, future in enumerate(concurrent.futures.as_completed(futures), 1):
            item_id = futures[future]
            try:
                routed[item_id] = future.result()
            except Exception as exc:
                # Fail-open: su errore, tutti i risultati vengono iniettati.
                results = source["recalls"][item_id]["results"]
                routed[item_id] = {
                    "automatic": [{**result, "route": "fail_open", "confidence": "high"} for result in results],
                    "optional": [],
                    "discarded": [],
                    "latency_ms": 0.0,
                    "classifier_called": True,
                    "error": f"{type(exc).__name__}: {exc}",
                }
            if index % 10 == 0 or index == len(dataset):
                print(f"[classify] {index}/{len(dataset)}", flush=True)

    judged: dict[str, dict] = {}
    with concurrent.futures.ThreadPoolExecutor(max_workers=args.workers) as executor:
        futures = {
            executor.submit(judge_channels, item, routed[item["id"]], args.judge_model): item["id"]
            for item in dataset
            if source["recalls"][item["id"]]["results"]
        }
        for index, future in enumerate(concurrent.futures.as_completed(futures), 1):
            item_id = futures[future]
            try:
                judged[item_id] = future.result()
            except Exception as exc:
                judged[item_id] = {"automatic_useful": False, "optional_useful": False, "error": f"{type(exc).__name__}: {exc}"}
            if index % 10 == 0 or index == len(futures):
                print(f"[judge] {index}/{len(futures)}", flush=True)

    rows = []
    for item in dataset:
        item_id = item["id"]
        baseline_judge = source["judge"][item_id]
        if baseline_judge.get("error"):
            continue
        route = routed[item_id]
        channel_judge = judged.get(item_id, {"automatic_useful": False, "optional_useful": False})
        rows.append((item, source["recalls"][item_id], baseline_judge, route, channel_judge))

    results_total = sum(len(row[1]["results"]) for row in rows)
    routes = Counter()
    for _, _, _, route, _ in rows:
        routes["bypass"] += sum(item.get("route") == "bypass" for item in route["automatic"])
        routes["high"] += sum(item.get("route") == "classifier" for item in route["automatic"])
        routes["medium"] += len(route["optional"])
        routes["low"] += len(route["discarded"])

    useful = [row for row in rows if row[2].get("returned_memory_useful")]
    auto_kept = [row for row in useful if row[4].get("automatic_useful")]
    available = [row for row in useful if row[4].get("automatic_useful") or row[4].get("optional_useful")]
    automatic_prompts = [row for row in rows if row[3]["automatic"]]
    optional_prompts = [row for row in rows if row[3]["optional"]]
    # Non interrompere l'utente con una proposta medium se esiste già almeno una
    # memoria high/bypass che verrà iniettata automaticamente.
    prompted_optional = [row for row in rows if not row[3]["automatic"] and row[3]["optional"]]
    empty_prompts = [row for row in rows if not row[3]["automatic"] and not row[3]["optional"]]
    classifier_latencies = [float(row[3].get("latency_ms") or 0) for row in rows if row[3].get("classifier_called")]
    production_latencies = [float(row[1].get("latency_ms") or 0) + float(row[3].get("latency_ms") or 0) for row in rows]
    baseline_latencies = [float(row[1].get("latency_ms") or 0) for row in rows]
    n = len(rows) or 1

    summary = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source_run": str(source_run),
        "model": args.model,
        "judge_model": args.judge_model,
        "score_field": args.score_field,
        "threshold": args.threshold,
        "samples": len(rows),
        "results_total": results_total,
        "bypass_results": routes["bypass"],
        "bypass_results_pct": round(100 * routes["bypass"] / (results_total or 1), 1),
        "classified_high": routes["high"],
        "classified_high_pct": round(100 * routes["high"] / (results_total or 1), 1),
        "classified_medium": routes["medium"],
        "classified_medium_pct": round(100 * routes["medium"] / (results_total or 1), 1),
        "classified_low": routes["low"],
        "classified_low_pct": round(100 * routes["low"] / (results_total or 1), 1),
        "prompts_automatic_pct": round(100 * len(automatic_prompts) / n, 1),
        "prompts_optional_pct": round(100 * len(optional_prompts) / n, 1),
        "prompts_prompted_optional_pct": round(100 * len(prompted_optional) / n, 1),
        "prompts_empty_pct": round(100 * len(empty_prompts) / n, 1),
        "baseline_useful_count": len(useful),
        "baseline_useful_auto_kept_pct": round(100 * len(auto_kept) / (len(useful) or 1), 1),
        "baseline_useful_available_pct": round(100 * len(available) / (len(useful) or 1), 1),
        "false_negative_count": len(useful) - len(available),
        "unnecessary_automatic_pct": round(100 * sum(not row[4].get("automatic_useful") for row in automatic_prompts) / (len(automatic_prompts) or 1), 1),
        "unnecessary_optional_pct": round(100 * sum(not row[4].get("optional_useful") for row in optional_prompts) / (len(optional_prompts) or 1), 1),
        "classifier_calls": sum(bool(row[3].get("classifier_called")) for row in rows),
        "classifier_p50_ms": round(percentile(classifier_latencies, 0.5), 1),
        "classifier_p95_ms": round(percentile(classifier_latencies, 0.95), 1),
        "production_mean_ms": round(statistics.mean(production_latencies), 1),
        "baseline_mean_ms": round(statistics.mean(baseline_latencies), 1),
        "classifier_errors": sum(bool(row[3].get("error")) for row in rows),
        "judge_errors": sum(bool(row[4].get("error")) for row in rows),
    }

    run_id = datetime.now(timezone.utc).strftime("recall_result_filter_%Y%m%d-%H%M%S")
    output_dir = args.output_dir or HERE / "bench_results" / run_id
    output_dir.mkdir(parents=True, exist_ok=False)
    write_json(output_dir / "results.private.json", {"routed": routed, "judged": judged})
    write_json(output_dir / "summary.json", summary)
    with (output_dir / "report.md").open("x", encoding="utf-8") as handle:
        handle.write(report(summary))
    print("\n" + report(summary))
    print(f"Artefatti locali: {output_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
