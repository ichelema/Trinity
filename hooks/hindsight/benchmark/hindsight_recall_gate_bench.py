#!/usr/bin/env python
"""Benchmark offline del gate semantico prima del recall automatico.

Estrae fino a 100 prompt umani recenti dai transcript principali di Claude Code,
esegue il recall con la configurazione reale, valuta l'utilità dei risultati e
confronta gate locali/LLM con e senza due scambi conversazionali precedenti.

I prompt e le memorie restano negli artefatti locali ignorati da Git. Su stdout
vengono stampati soltanto avanzamento, conteggi e metriche aggregate.
"""

from __future__ import annotations

import argparse
import concurrent.futures
import json
import math
import os
import re
import sys
import time
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
PLUGIN_ROOT = HERE.parents[2]
LIB_DIR = PLUGIN_ROOT / "hooks" / "hindsight" / "lib"
sys.path.insert(0, str(LIB_DIR))

from hindsight_config import load_config, recall_bank_urls  # pyright: ignore[reportMissingImports]  # noqa: E402
from hindsight_multibank import multi_recall  # pyright: ignore[reportMissingImports]  # noqa: E402
from hindsight_recall_lib import build_recall_payload  # pyright: ignore[reportMissingImports]  # noqa: E402

OPENAI_URL = "https://api.openai.com/v1/chat/completions"
DEFAULT_SESSIONS_ROOT = Path("E:/msys64/home/Sphynx/.claude/projects")
DEFAULT_MODELS = ("gpt-4.1-nano", "gpt-4.1-mini", "gpt-5.6-luna")
SYSTEM_REMINDER_RE = re.compile(r"<system-reminder>.*?</system-reminder>", re.DOTALL)
MEMORY_BLOCK_RE = re.compile(
    r"<hindsight_memories>.*?</hindsight_memories>"
    r"|## Hindsight (?:persistent memory|knowledge pages).*?Verify mutable facts against the repo\.",
    re.DOTALL,
)
COMMAND_MARKERS = (
    "<command-message>",
    "<command-name>",
    "<command-args>",
    "<local-command-stdout>",
    "<local-command-stderr>",
    "<local-command-caveat>",
    "<bash-input>",
    "<bash-stdout>",
)
SECRET_PATTERNS = (
    re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----"),
    re.compile(r"\bAuthorization\s*:\s*(?:Bearer|Basic)\s+\S+", re.I),
    re.compile(
        r"\b(?:api[_-]?key|access[_-]?token|auth[_-]?token|client[_-]?secret|password|passwd|pwd)\s*[:=]\s*['\"]?\S{8,}",
        re.I,
    ),
    re.compile(r"\b(?:gh[pousr]_[A-Za-z0-9_]{20,}|sk-ant-[A-Za-z0-9_-]{20,}|xox[baprs]-[A-Za-z0-9-]{20,})\b"),
    re.compile(r"\beyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\b"),
    re.compile(r"\b(?:postgres(?:ql)?|mysql|mongodb(?:\+srv)?|redis)://[^\s/@:]+:[^\s/@]+@", re.I),
    re.compile(r"\bhttps?://[^\s/@:]+:[^\s/@]+@", re.I),
)

HISTORY_RE = re.compile(
    r"\b(?:prima|precedent[ei]|scors[oaie]|già|avevamo|abbiamo deciso|ricord[ai]|"
    r"riprendi|continua|prosegui|riprova|torna|rimetti|come al solito|preferisc[oi]|"
    r"workaround|causa radice|root cause|in passato|last time|previous|remember)\b",
    re.I,
)
PROJECT_MEMORY_RE = re.compile(
    r"\b(?:convenzion[ei]|decision[ei] architettural[ei]|regol[ae] di dominio|"
    r"vincol[oi]|configurazion[ei]|ambiente|toolchain|deploy|build|runtime|version[ei]|"
    r"bug|errore|fallisc|non funziona|compatibil|migrazion[ei]|refactor|architettur[ae])\b",
    re.I,
)
MECHANICAL_RE = re.compile(
    r"^(?:correggi (?:il )?refuso|rinomina |formatta |traduci |riassumi |"
    r"scrivi (?:solo )?|mostra |elenca |conta |calcola |crea un promemoria|"
    r"aggiungi un commento|sostituisci )",
    re.I,
)

GATE_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "should_recall": {"type": "boolean"},
        "reason": {
            "type": "string",
            "enum": [
                "past_work",
                "preference_or_convention",
                "project_history",
                "environment_or_workaround",
                "self_contained",
                "mechanical",
                "other",
            ],
        },
    },
    "required": ["should_recall", "reason"],
}

JUDGE_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "memory_would_help": {"type": "boolean"},
        "returned_memory_useful": {"type": "boolean"},
        "reason": {
            "type": "string",
            "enum": [
                "directly_actionable",
                "useful_constraint",
                "useful_preference",
                "useful_history",
                "generic_or_redundant",
                "irrelevant",
                "no_results",
            ],
        },
    },
    "required": ["memory_would_help", "returned_memory_useful", "reason"],
}

GATE_SYSTEM_PROMPT = """Decidi se vale la pena consultare la memoria persistente prima di rispondere al prompt corrente.

Usa recall solo quando sessioni precedenti potrebbero contenere informazioni concrete capaci di cambiare, migliorare o rendere più sicura la risposta: decisioni e convenzioni, regole di dominio, preferenze, bug e workaround già analizzati, vincoli/configurazioni d'ambiente, approcci già provati o lavoro precedente richiamato dal prompt.

Non usare recall per task autosufficienti e meccanici risolvibili dal prompt e dal repository corrente. Non scegliere recall per mera precauzione. Il contesto recente, se presente, serve solo a interpretare riferimenti come “questo”, “continua” o “come prima”."""

JUDGE_SYSTEM_PROMPT = """Valuta l'utilità concreta della memoria persistente per il prompt.

memory_would_help=true solo se informazioni storiche non ricavabili con sicurezza dal solo prompt e repository potrebbero migliorare materialmente il lavoro.
returned_memory_useful=true solo se almeno una memoria restituita contiene una decisione, preferenza, vincolo, configurazione, causa/fix o fatto storico direttamente azionabile per questo prompt. Una memoria generica, tangenziale, ripetuta nel prompt o verificabile banalmente nel repository non è utile.

Sii severo: non premiare il richiamo per precauzione."""


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sessions-root", type=Path, default=DEFAULT_SESSIONS_ROOT)
    parser.add_argument("--limit", type=int, default=100)
    parser.add_argument("--workers", type=int, default=6)
    parser.add_argument("--models", default=",".join(DEFAULT_MODELS))
    parser.add_argument("--judge-model", default="gpt-5.6-luna")
    parser.add_argument("--output-dir", type=Path)
    parser.add_argument("--dataset-only", action="store_true")
    return parser.parse_args()


def content_text(content: object, *, allow_images: bool = True) -> tuple[str, bool] | None:
    if isinstance(content, str):
        return content, False
    if not isinstance(content, list):
        return None
    parts: list[str] = []
    has_image = False
    for block in content:
        if not isinstance(block, dict):
            return None
        kind = block.get("type")
        if kind == "text":
            parts.append(block.get("text") or "")
        elif kind == "image" and allow_images:
            has_image = True
        else:
            return None
    return "\n".join(parts), has_image


def clean_text(text: str) -> str | None:
    if not text:
        return None
    opens = text.count("<system-reminder>")
    closes = text.count("</system-reminder>")
    if opens != closes:
        return None
    text = SYSTEM_REMINDER_RE.sub("", text)
    text = MEMORY_BLOCK_RE.sub("", text).strip()
    if not text or any(marker in text for marker in COMMAND_MARKERS):
        return None
    return text


def looks_sensitive(text: str) -> bool:
    return any(pattern.search(text) for pattern in SECRET_PATTERNS)


def is_human_prompt(record: dict) -> bool:
    message = record.get("message") or {}
    origin = record.get("origin") or {}
    return bool(
        record.get("type") == "user"
        and message.get("role") == "user"
        and record.get("promptSource") == "typed"
        and origin.get("kind") == "human"
        and not record.get("isSidechain")
        and not record.get("isMeta")
        and not record.get("isCompactSummary")
        and not record.get("isVisibleInTranscriptOnly")
    )


def main_transcripts(root: Path) -> list[Path]:
    return sorted(path for project in root.iterdir() if project.is_dir() for path in project.glob("*.jsonl"))


def load_records(root: Path) -> tuple[dict[str, dict], list[dict], dict[str, int]]:
    by_uuid: dict[str, dict] = {}
    candidates: list[dict] = []
    stats = {"files": 0, "bad_json": 0, "duplicate_uuid": 0, "rejected_sensitive": 0}
    for path in main_transcripts(root):
        stats["files"] += 1
        project = path.parent.name
        try:
            lines = path.open("r", encoding="utf-8", errors="replace")
        except OSError:
            continue
        with lines:
            for line in lines:
                try:
                    record = json.loads(line)
                except json.JSONDecodeError:
                    stats["bad_json"] += 1
                    continue
                uuid = record.get("uuid")
                if uuid:
                    if uuid in by_uuid:
                        stats["duplicate_uuid"] += 1
                    else:
                        by_uuid[uuid] = record
                if not is_human_prompt(record):
                    continue
                extracted = content_text((record.get("message") or {}).get("content"))
                if not extracted:
                    continue
                raw_text, has_image = extracted
                text = clean_text(raw_text)
                if not text or len(text) <= 20 or text.startswith("/"):
                    continue
                if looks_sensitive(text):
                    stats["rejected_sensitive"] += 1
                    continue
                candidates.append(
                    {
                        "record": record,
                        "prompt": text,
                        "has_image": has_image,
                        "project": project,
                        "source": str(path),
                    }
                )
    return by_uuid, candidates, stats


def assistant_text(record: dict) -> str | None:
    message = record.get("message") or {}
    if message.get("role") != "assistant":
        return None
    content = message.get("content")
    if isinstance(content, str):
        return clean_text(content)
    if not isinstance(content, list):
        return None
    parts = [
        block.get("text") or ""
        for block in content
        if isinstance(block, dict) and block.get("type") == "text"
    ]
    return clean_text("\n".join(parts))


def prior_context(record: dict, by_uuid: dict[str, dict]) -> list[dict]:
    """Recupera i due scambi completi immediatamente precedenti.

    Uno scambio è la coppia prompt umano + risposta finale dell'assistente. I record
    intermedi dello stesso messaggio assistant vengono uniti e i tool vengono ignorati.
    """
    chain: list[dict] = []
    parent = record.get("parentUuid")
    visited: set[str] = set()
    while parent and parent not in visited and len(chain) < 80:
        visited.add(parent)
        item = by_uuid.get(parent)
        if not item:
            break
        if is_human_prompt(item):
            extracted = content_text((item.get("message") or {}).get("content"))
            text = clean_text(extracted[0]) if extracted else None
            if text and not looks_sensitive(text):
                chain.append({"role": "user", "text": text})
        else:
            text = assistant_text(item)
            if text and len(text) >= 20 and not looks_sensitive(text):
                chain.append(
                    {
                        "role": "assistant",
                        "text": text,
                        "message_id": (item.get("message") or {}).get("id") or item.get("requestId"),
                    }
                )
        parent = item.get("parentUuid")

    chain.reverse()
    merged: list[dict] = []
    for item in chain:
        if (
            item["role"] == "assistant"
            and merged
            and merged[-1]["role"] == "assistant"
            and item.get("message_id") == merged[-1].get("message_id")
        ):
            merged[-1]["text"] = f"{merged[-1]['text']}\n{item['text']}"
        else:
            merged.append(item.copy())

    # Le risposte assistant possono essere frammentate su più message.id. Per il gate
    # serve il testo visibile di due scambi, non la struttura interna del transcript:
    # compatta quindi tutti i frammenti consecutivi dello stesso ruolo.
    compacted: list[dict] = []
    for item in merged:
        if compacted and item["role"] == compacted[-1]["role"]:
            compacted[-1]["text"] = f"{compacted[-1]['text']}\n{item['text']}"
        else:
            compacted.append({"role": item["role"], "text": item["text"]})

    user_indexes = [index for index, item in enumerate(compacted) if item["role"] == "user"]
    if not user_indexes:
        return []
    start = user_indexes[-2] if len(user_indexes) >= 2 else user_indexes[-1]
    selected = compacted[start:]

    total = 0
    bounded: list[dict] = []
    for item in selected:
        remaining = 6000 - total
        if remaining <= 0:
            break
        text = item["text"][: min(2000, remaining)]
        bounded.append({"role": item["role"], "text": text})
        total += len(text)
    return bounded


def build_dataset(root: Path, limit: int) -> tuple[list[dict], dict[str, int]]:
    by_uuid, candidates, stats = load_records(root)
    candidates.sort(
        key=lambda item: (
            item["record"].get("timestamp") or "",
            item["record"].get("uuid") or "",
        ),
        reverse=True,
    )
    dataset: list[dict] = []
    seen: set[str] = set()
    for item in candidates:
        uuid = item["record"].get("uuid") or ""
        if not uuid or uuid in seen:
            continue
        seen.add(uuid)
        context = prior_context(item["record"], by_uuid)
        if any(looks_sensitive(turn["text"]) for turn in context):
            context = []
        dataset.append(
            {
                "id": uuid,
                "session_id": item["record"].get("sessionId") or item["record"].get("session_id"),
                "timestamp": item["record"].get("timestamp"),
                "project": item["project"],
                "cwd": item["record"].get("cwd") or "",
                "prompt": item["prompt"],
                "has_image": item["has_image"],
                "context": context,
            }
        )
        if len(dataset) >= limit:
            break
    stats["eligible"] = len(candidates)
    stats["selected"] = len(dataset)
    stats["with_context"] = sum(1 for item in dataset if item["context"])
    return dataset, stats


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


def api_json(model: str, system: str, user: str, schema_name: str, schema: dict, timeout: int = 30) -> tuple[dict, float]:
    key = os.environ.get("OPENAI_API_KEY")
    if not key:
        raise RuntimeError("OPENAI_API_KEY non impostata")
    body: dict = {
        "model": model,
        "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
        "response_format": {
            "type": "json_schema",
            "json_schema": {"name": schema_name, "schema": schema, "strict": True},
        },
    }
    if not model.startswith("gpt-5"):
        body["temperature"] = 0
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
    return json.loads(data["choices"][0]["message"]["content"]), elapsed_ms


def context_block(item: dict) -> str:
    if not item["context"]:
        return "(nessun contesto precedente disponibile)"
    compacted: list[dict] = []
    for turn in item["context"]:
        if compacted and compacted[-1]["role"] == turn["role"]:
            compacted[-1]["text"] = f"{compacted[-1]['text']}\n{turn['text']}"
        else:
            compacted.append(dict(turn))
    return "\n\n".join(f"[{turn['role']}] {turn['text']}" for turn in compacted[-4:])


def gate_user(item: dict, include_context: bool) -> str:
    parts = []
    if include_context:
        parts.extend(["## Due scambi precedenti", context_block(item), ""])
    parts.extend(["## Prompt corrente", item["prompt"][:6000]])
    return "\n".join(parts)


def run_gate(item: dict, model: str, include_context: bool) -> dict:
    result, latency = api_json(model, GATE_SYSTEM_PROMPT, gate_user(item, include_context), "recall_gate", GATE_SCHEMA)
    return {**result, "latency_ms": round(latency, 2)}


def local_heuristic(prompt: str) -> dict:
    started = time.perf_counter()
    if HISTORY_RE.search(prompt):
        decision, reason = True, "history_signal"
    elif PROJECT_MEMORY_RE.search(prompt):
        decision, reason = True, "project_signal"
    elif MECHANICAL_RE.search(prompt):
        decision, reason = False, "mechanical_signal"
    else:
        decision, reason = False, "no_memory_signal"
    return {
        "should_recall": decision,
        "reason": reason,
        "latency_ms": round((time.perf_counter() - started) * 1000, 4),
    }


def hybrid_decision(prompt: str, llm: dict) -> dict:
    local = local_heuristic(prompt)
    if HISTORY_RE.search(prompt):
        return {**local, "source": "forced_recall"}
    if MECHANICAL_RE.search(prompt) and not PROJECT_MEMORY_RE.search(prompt):
        return {**local, "source": "forced_skip"}
    return {**llm, "source": "llm"}


def direct_recall(url: str, payload: dict, timeout: int) -> list[dict]:
    request = urllib.request.Request(
        url + "/memories/recall",
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        data = json.loads(response.read().decode("utf-8", "replace"))
    return data.get("results") or []


def recall_one(item: dict, cfg: dict) -> dict:
    query = item["prompt"][: int(cfg["recall_max_prompt_chars"])]
    urls = recall_bank_urls(cfg, item.get("cwd") or None)
    payload = build_recall_payload(query, cfg, datetime.now(timezone.utc).isoformat())
    started = time.perf_counter()
    try:
        if len(urls) == 1:
            results = direct_recall(urls[0], payload, int(cfg["recall_timeout"]))
            meta = {"merge": "single"}
        else:
            results, meta = multi_recall(query, cfg, urls, payload)
        error = meta.get("rerank_error")
    except Exception as exc:  # Il benchmark registra l'errore e prosegue.
        results, meta, error = [], {}, f"{type(exc).__name__}: {exc}"
    latency = (time.perf_counter() - started) * 1000
    cap = int(cfg.get("recall_max_results_multibank") or cfg["recall_max_results"]) if len(urls) > 1 else int(cfg["recall_max_results"])
    compact = [
        {
            "type": result.get("type"),
            "text": (result.get("text") or "")[:3000],
            "scores": result.get("scores") or {},
            "global_score": result.get("_rerank_score"),
        }
        for result in results[:cap]
    ]
    return {
        "latency_ms": round(latency, 2),
        "banks": [url.rsplit("/", 1)[-1] for url in urls],
        "results": compact,
        "nonempty": bool(compact),
        "error": error,
        "meta": {key: value for key, value in meta.items() if key in ("merge", "per_bank_counts", "min_score_filtered")},
    }


def judge_user(item: dict, recall: dict) -> str:
    memories = "\n".join(
        f"- ({memory.get('type') or '?'}) {memory.get('text') or ''}" for memory in recall["results"]
    ) or "(nessun risultato)"
    return (
        f"## Contesto recente\n{context_block(item)}\n\n"
        f"## Prompt corrente\n{item['prompt'][:6000]}\n\n"
        f"## Memorie restituite\n{memories[:12000]}"
    )


def judge_one(item: dict, recall: dict, model: str) -> dict:
    result, latency = api_json(model, JUDGE_SYSTEM_PROMPT, judge_user(item, recall), "recall_utility", JUDGE_SCHEMA, timeout=60)
    return {**result, "latency_ms": round(latency, 2)}


def run_parallel(items: list[dict], workers: int, label: str, fn) -> dict[str, dict]:
    output: dict[str, dict] = {}
    with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as executor:
        futures = {executor.submit(fn, item): item["id"] for item in items}
        for index, future in enumerate(concurrent.futures.as_completed(futures), 1):
            item_id = futures[future]
            try:
                output[item_id] = future.result()
            except Exception as exc:
                output[item_id] = {"error": f"{type(exc).__name__}: {exc}"}
            if index % 10 == 0 or index == len(items):
                print(f"[{label}] {index}/{len(items)}", flush=True)
    return output


def metrics(name: str, decisions: dict[str, dict], rows: list[dict]) -> dict:
    valid = [row for row in rows if not decisions.get(row["id"], {}).get("error")]
    executed = [row for row in valid if decisions[row["id"]].get("should_recall")]
    useful_baseline = [row for row in valid if row["judge"].get("returned_memory_useful")]
    useful_kept = [row for row in useful_baseline if decisions[row["id"]].get("should_recall")]
    unnecessary = [row for row in executed if not row["judge"].get("returned_memory_useful")]
    nonempty = [row for row in executed if row["recall"].get("nonempty")]
    latencies = [float(decisions[row["id"]].get("latency_ms") or 0) for row in valid]
    denom = len(valid) or 1
    exec_denom = len(executed) or 1
    useful_denom = len(useful_baseline) or 1
    return {
        "test": name,
        "samples": len(valid),
        "recall_rate_pct": round(100 * len(executed) / denom, 1),
        "recall_avoided_pct": round(100 * (len(valid) - len(executed)) / denom, 1),
        "unnecessary_recall_pct": round(100 * len(unnecessary) / exec_denom, 1),
        "nonempty_recall_pct": round(100 * len(nonempty) / exec_denom, 1),
        "useful_recall_pct": round(100 * (len(executed) - len(unnecessary)) / exec_denom, 1),
        "useful_recall_kept_pct": round(100 * len(useful_kept) / useful_denom, 1),
        "false_negative_count": len(useful_baseline) - len(useful_kept),
        "gate_p50_ms": round(percentile(latencies, 0.5), 1),
        "gate_p95_ms": round(percentile(latencies, 0.95), 1),
    }


def always_decisions(rows: list[dict]) -> dict[str, dict]:
    return {row["id"]: {"should_recall": True, "reason": "baseline", "latency_ms": 0} for row in rows}


def report_markdown(summary: dict) -> str:
    lines = [
        "# Benchmark del gate semantico Hindsight",
        "",
        f"Data: {summary['generated_at'][:10]}",
        f"Campione: {summary['dataset']['selected']} prompt umani recenti, maggiori di 20 caratteri.",
        "",
        "## Definizioni",
        "",
        "- **Recall evitati**: prompt per cui il gate non avrebbe interrogato Hindsight.",
        "- **Recall inutili**: richiami eseguiti ma giudicati senza alcuna memoria concretamente utile.",
        "- **Recall non vuoti**: richiami che hanno restituito almeno un risultato; non implica utilità.",
        "- **Recall utili mantenuti**: quota dei richiami utili della baseline che il gate non avrebbe perso.",
        "",
        "## Risultati",
        "",
        "| Test | Recall eseguiti | Recall evitati | Recall inutili | Recall non vuoti | Recall utili | Utili mantenuti | Falsi negativi | Gate p50 | Gate p95 |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for row in summary["tests"]:
        lines.append(
            f"| {row['test']} | {row['recall_rate_pct']}% | {row['recall_avoided_pct']}% | "
            f"{row['unnecessary_recall_pct']}% | {row['nonempty_recall_pct']}% | "
            f"{row['useful_recall_pct']}% | {row['useful_recall_kept_pct']}% | "
            f"{row['false_negative_count']} | {row['gate_p50_ms']} ms | {row['gate_p95_ms']} ms |"
        )
    base = summary["baseline"]
    lines.extend(
        [
            "",
            "## Baseline misurata",
            "",
            f"- Latenza recall fresca: p50 **{base['recall_p50_ms']} ms**, p95 **{base['recall_p95_ms']} ms**.",
            f"- Risposta non vuota: **{base['nonempty_pct']}%** dei prompt.",
            f"- Memoria giudicata concretamente utile: **{base['useful_pct']}%** dei prompt.",
            f"- Il giudice ha indicato che la memoria avrebbe potuto aiutare: **{base['would_help_pct']}%** dei prompt.",
            "",
            "## Limiti",
            "",
            "- Il campione rappresenta i prompt recenti disponibili su questa macchina, non tutti i possibili lavori futuri.",
            "- L'utilità è valutata da un LLM forte; una revisione umana resta il controllo migliore per i casi dubbi.",
            "- Il test misura recall freschi. Il gate remoto va eseguito solo dopo un cache miss, per non rallentare gli hit.",
            "- Il braccio che usa lo stesso modello del giudice può risultare favorito; va letto come test supplementare.",
        ]
    )
    return "\n".join(lines) + "\n"


def write_json(path: Path, value: object) -> None:
    with path.open("x", encoding="utf-8") as handle:
        json.dump(value, handle, ensure_ascii=False, indent=2)
    try:
        os.chmod(path, 0o600)
    except OSError:
        pass


def main() -> int:
    args = parse_args()
    if not 1 <= args.limit <= 100:
        raise SystemExit("--limit deve essere tra 1 e 100")
    run_id = datetime.now(timezone.utc).strftime("recall_gate_%Y%m%d-%H%M%S")
    output_dir = args.output_dir or HERE / "bench_results" / run_id
    output_dir.mkdir(parents=True, exist_ok=False)

    dataset, dataset_stats = build_dataset(args.sessions_root, args.limit)
    write_json(output_dir / "dataset.private.json", dataset)
    print(f"[dataset] selezionati={len(dataset)} con_contesto={dataset_stats['with_context']} sensibili_scartati={dataset_stats['rejected_sensitive']}")
    if args.dataset_only:
        print(f"Artefatti locali: {output_dir}")
        return 0

    cfg = load_config()
    recalls: dict[str, dict] = {}
    for index, item in enumerate(dataset, 1):
        recalls[item["id"]] = recall_one(item, cfg)
        if index % 10 == 0 or index == len(dataset):
            print(f"[recall] {index}/{len(dataset)}", flush=True)

    judge = run_parallel(
        dataset,
        args.workers,
        f"judge:{args.judge_model}",
        lambda item: judge_one(item, recalls[item["id"]], args.judge_model),
    )

    models = [model.strip() for model in args.models.split(",") if model.strip()]
    gate_results: dict[str, dict[str, dict]] = {}
    for model in models:
        for include_context in (False, True):
            suffix = "context" if include_context else "prompt"
            key = f"{model}:{suffix}"
            gate_results[key] = run_parallel(
                dataset,
                args.workers,
                f"gate:{key}",
                lambda item, m=model, c=include_context: run_gate(item, m, c),
            )

    rows = [
        {
            "id": item["id"],
            "recall": recalls[item["id"]],
            "judge": judge[item["id"]],
        }
        for item in dataset
        if not judge[item["id"]].get("error")
    ]
    decisions: dict[str, dict[str, dict]] = {"baseline:always": always_decisions(rows)}
    decisions["heuristic:local"] = {item["id"]: local_heuristic(item["prompt"]) for item in dataset}
    for key, result in gate_results.items():
        decisions[f"llm:{key}"] = result
        decisions[f"hybrid:{key}"] = {
            item["id"]: hybrid_decision(item["prompt"], result[item["id"]])
            for item in dataset
            if item["id"] in result and not result[item["id"]].get("error")
        }

    tests = [metrics(name, result, rows) for name, result in decisions.items()]
    recall_latencies = [float(row["recall"]["latency_ms"]) for row in rows]
    baseline = {
        "recall_p50_ms": round(percentile(recall_latencies, 0.5), 1),
        "recall_p95_ms": round(percentile(recall_latencies, 0.95), 1),
        "nonempty_pct": round(100 * sum(row["recall"]["nonempty"] for row in rows) / (len(rows) or 1), 1),
        "useful_pct": round(100 * sum(bool(row["judge"].get("returned_memory_useful")) for row in rows) / (len(rows) or 1), 1),
        "would_help_pct": round(100 * sum(bool(row["judge"].get("memory_would_help")) for row in rows) / (len(rows) or 1), 1),
    }
    summary = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "dataset": dataset_stats,
        "judge_model": args.judge_model,
        "models": models,
        "baseline": baseline,
        "tests": tests,
    }
    private = {
        "dataset": dataset,
        "recalls": recalls,
        "judge": judge,
        "gate_results": gate_results,
        "decisions": decisions,
    }
    write_json(output_dir / "results.private.json", private)
    write_json(output_dir / "summary.json", summary)
    with (output_dir / "report.md").open("x", encoding="utf-8") as handle:
        handle.write(report_markdown(summary))

    print("\n" + report_markdown(summary))
    print(f"Artefatti locali: {output_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
