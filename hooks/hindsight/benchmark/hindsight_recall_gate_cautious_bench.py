#!/usr/bin/env python
"""Benchmark del gate prudente Luna: recall / skip / uncertain.

Riusa dataset, recall e giudizi dell'ultimo benchmark completo. Esegue soltanto
le 100 classificazioni Luna necessarie al nuovo prompt. `recall` e `uncertain`
consultano Hindsight; solo `skip` evita il richiamo.
"""

from __future__ import annotations

import argparse
import concurrent.futures
import json
import math
import os
import statistics
import time
import urllib.request
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
OPENAI_URL = "https://api.openai.com/v1/chat/completions"
DEFAULT_MODEL = "gpt-5.6-luna"

CAUTIOUS_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "decision": {"type": "string", "enum": ["recall", "skip", "uncertain"]},
        "reason": {
            "type": "string",
            "enum": [
                "explicit_past_reference",
                "preference_or_convention",
                "project_history",
                "environment_or_workaround",
                "possible_hidden_constraint",
                "clearly_self_contained",
                "purely_mechanical",
                "ambiguous",
            ],
        },
    },
    "required": ["decision", "reason"],
}

CAUTIOUS_SYSTEM_PROMPT = """Sei un gate prudente che decide se consultare la memoria persistente Hindsight prima di eseguire un task di sviluppo.

Devi restituire una sola decisione:
- recall: esiste un motivo concreto per cui informazioni storiche potrebbero cambiare, migliorare o rendere più sicuro il lavoro;
- skip: il task è chiaramente autosufficiente e la memoria storica non può aggiungere valore materiale;
- uncertain: non puoi escludere con sicurezza che esistano decisioni, preferenze, vincoli o workaround rilevanti.

REGOLA DI SICUREZZA: perdere una memoria utile è molto peggio di fare un recall inutile. Se hai un dubbio reale, scegli uncertain. Non usare una falsa sicurezza numerica.

Scegli recall quando compare almeno uno di questi segnali:
- riferimento esplicito o implicito a lavoro, decisioni o tentativi precedenti;
- preferenze dell'utente o convenzioni del progetto;
- bug, cause radice o workaround già incontrati;
- configurazioni, versioni, ambiente, toolchain, deploy, build o vincoli non ovvi;
- modifica architetturale, migrazione o scelta fra approcci già discussi;
- continuazioni come “continua”, “questo”, “come prima”, interpretate col contesto recente.

Scegli skip SOLO se tutte le condizioni sono vere:
1. il risultato dipende interamente dal prompt corrente o da dati esplicitamente presenti;
2. non richiede preferenze, decisioni, configurazioni o storia del progetto;
3. è un'operazione meccanica e locale, come un calcolo completo, una traduzione letterale, una formattazione o una trasformazione con input e output pienamente specificati;
4. anche se esistessero memorie pertinenti, non cambierebbero materialmente il risultato.

Scegli uncertain per task di codice o repository non banali quando il prompt sembra autosufficiente ma potrebbero esistere convenzioni o vincoli nascosti.

Esempi:
- “Continua il fix di prima” -> recall.
- “Usa il package manager che preferisco” -> recall.
- “Correggi questo errore di build su Windows” -> recall.
- “Traduci letteralmente in inglese: Buongiorno” -> skip.
- “Calcola 17 * 23” -> skip.
- “Rinomina esattamente foo in bar nel testo seguente” -> skip.
- “Aggiungi validazione a questo servizio” senza sapere se esistono regole precedenti -> uncertain.
- “Implementa questa modifica nel repository” -> uncertain, salvo riferimento storico che richiede recall.

Il contesto recente serve a interpretare il prompt corrente, non è memoria Hindsight."""


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-run", type=Path)
    parser.add_argument("--model", default=DEFAULT_MODEL)
    parser.add_argument("--workers", type=int, default=6)
    parser.add_argument("--output-dir", type=Path)
    return parser.parse_args()


def latest_complete_run() -> Path:
    runs = sorted(
        path.parent
        for path in (HERE / "bench_results").glob("recall_gate_*/results.private.json")
    )
    if not runs:
        raise RuntimeError("nessun benchmark completo trovato")
    return runs[-1]


def context_block(item: dict) -> str:
    context = item.get("context") or []
    if not context:
        return "(nessun contesto precedente disponibile)"
    compacted: list[dict] = []
    for turn in context:
        if compacted and compacted[-1]["role"] == turn["role"]:
            compacted[-1]["text"] = f"{compacted[-1]['text']}\n{turn['text']}"
        else:
            compacted.append(dict(turn))
    return "\n\n".join(
        f"[{turn['role']}] {turn['text']}" for turn in compacted[-4:]
    )


def gate_input(item: dict) -> str:
    return (
        f"## Progetto\n{item.get('project') or '(sconosciuto)'}\n\n"
        f"## Due scambi precedenti\n{context_block(item)}\n\n"
        f"## Prompt corrente\n{item['prompt'][:6000]}"
    )


def classify(item: dict, model: str, timeout: int = 30) -> dict:
    key = os.environ.get("OPENAI_API_KEY")
    if not key:
        raise RuntimeError("OPENAI_API_KEY non impostata")
    body = {
        "model": model,
        "messages": [
            {"role": "system", "content": CAUTIOUS_SYSTEM_PROMPT},
            {"role": "user", "content": gate_input(item)},
        ],
        "response_format": {
            "type": "json_schema",
            "json_schema": {
                "name": "cautious_recall_gate",
                "schema": CAUTIOUS_SCHEMA,
                "strict": True,
            },
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
    elapsed_ms = (time.perf_counter() - started) * 1000
    result = json.loads(data["choices"][0]["message"]["content"])
    return {**result, "latency_ms": round(elapsed_ms, 2)}


def percentile(values: list[float], p: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    index = (len(ordered) - 1) * p
    low = math.floor(index)
    high = math.ceil(index)
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
    return f"""# Benchmark del gate prudente Hindsight

Data: {summary['generated_at'][:10]}
Modello: `{summary['model']}` con due scambi precedenti.

## Risultati

| Misura | Risultato |
|---|---:|
| Prompt | {summary['samples']} |
| Decisioni `recall` | {summary['decisions']['recall']}% |
| Decisioni `uncertain` | {summary['decisions']['uncertain']}% |
| Decisioni `skip` | {summary['decisions']['skip']}% |
| Recall effettivamente eseguiti (`recall` + `uncertain`) | {summary['recall_rate_pct']}% |
| Recall evitati | {summary['recall_avoided_pct']}% |
| Recall utili mantenuti | {summary['useful_recall_kept_pct']}% |
| Falsi negativi | {summary['false_negative_count']} su {summary['baseline_useful_count']} utili |
| Recall inutili tra quelli eseguiti | {summary['unnecessary_recall_pct']}% |
| Gate p50 | {summary['gate_p50_ms']} ms |
| Gate p95 | {summary['gate_p95_ms']} ms |
| Tempo totale medio stimato | {summary['total_mean_ms']} ms |
| Baseline sempre-recall | {summary['baseline_mean_ms']} ms |

## Regola applicata

Solo `skip` evita Hindsight. `recall`, `uncertain`, errori e output invalidi
fanno recall: il comportamento è prudente e fail-open.
"""


def main() -> int:
    args = parse_args()
    source_run = args.source_run or latest_complete_run()
    private = json.loads((source_run / "results.private.json").read_text(encoding="utf-8"))
    dataset = private["dataset"]

    decisions: dict[str, dict] = {}
    with concurrent.futures.ThreadPoolExecutor(max_workers=args.workers) as executor:
        futures = {
            executor.submit(classify, item, args.model): item["id"] for item in dataset
        }
        for index, future in enumerate(concurrent.futures.as_completed(futures), 1):
            item_id = futures[future]
            try:
                decisions[item_id] = future.result()
            except Exception as exc:
                decisions[item_id] = {
                    "decision": "uncertain",
                    "reason": "ambiguous",
                    "latency_ms": 0,
                    "error": f"{type(exc).__name__}: {exc}",
                }
            if index % 10 == 0 or index == len(dataset):
                print(f"[cautious-gate] {index}/{len(dataset)}", flush=True)

    rows = []
    for item in dataset:
        item_id = item["id"]
        judge = private["judge"][item_id]
        recall = private["recalls"][item_id]
        if judge.get("error"):
            continue
        decision = decisions[item_id]
        execute_recall = decision["decision"] != "skip"
        rows.append((item, judge, recall, decision, execute_recall))

    useful = [row for row in rows if row[1].get("returned_memory_useful")]
    useful_kept = [row for row in useful if row[4]]
    executed = [row for row in rows if row[4]]
    unnecessary = [row for row in executed if not row[1].get("returned_memory_useful")]
    gate_latencies = [float(row[3].get("latency_ms") or 0) for row in rows]
    total_latencies = [
        float(row[3].get("latency_ms") or 0)
        + (float(row[2].get("latency_ms") or 0) if row[4] else 0)
        for row in rows
    ]
    baseline_latencies = [float(row[2].get("latency_ms") or 0) for row in rows]
    counts = Counter(row[3]["decision"] for row in rows)
    n = len(rows) or 1
    summary = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source_run": str(source_run),
        "model": args.model,
        "samples": len(rows),
        "decisions": {key: round(100 * counts.get(key, 0) / n, 1) for key in ("recall", "uncertain", "skip")},
        "recall_rate_pct": round(100 * len(executed) / n, 1),
        "recall_avoided_pct": round(100 * (n - len(executed)) / n, 1),
        "baseline_useful_count": len(useful),
        "useful_recall_kept_pct": round(100 * len(useful_kept) / (len(useful) or 1), 1),
        "false_negative_count": len(useful) - len(useful_kept),
        "unnecessary_recall_pct": round(100 * len(unnecessary) / (len(executed) or 1), 1),
        "gate_p50_ms": round(percentile(gate_latencies, 0.5), 1),
        "gate_p95_ms": round(percentile(gate_latencies, 0.95), 1),
        "total_mean_ms": round(statistics.mean(total_latencies), 1),
        "baseline_mean_ms": round(statistics.mean(baseline_latencies), 1),
        "errors": sum(bool(row[3].get("error")) for row in rows),
    }

    run_id = datetime.now(timezone.utc).strftime("recall_gate_cautious_%Y%m%d-%H%M%S")
    output_dir = args.output_dir or HERE / "bench_results" / run_id
    output_dir.mkdir(parents=True, exist_ok=False)
    write_json(output_dir / "results.private.json", {"decisions": decisions})
    write_json(output_dir / "summary.json", summary)
    with (output_dir / "report.md").open("x", encoding="utf-8") as handle:
        handle.write(report(summary))
    print("\n" + report(summary))
    print(f"Artefatti locali: {output_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
