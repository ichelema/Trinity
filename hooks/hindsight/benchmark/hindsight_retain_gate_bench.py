#!/usr/bin/env python
"""Benchmark offline del gate semantico pre-retain (ICH-67).

Due fasi, stessa filosofia di hindsight_recall_gate_bench.py:

  --build-corpus   ricostruisce finestre Stop REALI dai transcript di Claude
                   Code alla cadenza di produzione (retain_every_n_turns=3,
                   overlap 1, stesse funzioni del worker) e le scrive in
                   artifacts/retain_windows.jsonl per l'etichettatura manuale.

  --evaluate       per ogni finestra etichettata in artifacts/retain_labels.jsonl
                   esegue il gate REALE (evaluate_retain, stessa libreria di
                   produzione) e stampa le metriche del piano ICH-67: precisione
                   retain, copertura, falsi negativi critici, riduzione POST,
                   soppressione duplicati, quota uncertain, errori tecnici,
                   latenza p95. Con --dry-run-extract le finestre decise
                   "retain" passano anche da POST /memories/dry-run-extract
                   (estrazione senza persistenza) per ispezione qualitativa.

Formato label (una riga JSONL per finestra, allineata per "id"):
  {"id": "...", "expected_action": "retain|skip|uncertain", "reason": "...",
   "durable_claims": ["..."], "duplicate_of": ["mem-..."], "critical": false}

I contenuti restano negli artefatti locali ignorati da Git; su stdout solo
avanzamento, conteggi e metriche aggregate.
"""

from __future__ import annotations

import argparse
import concurrent.futures
import hashlib
import importlib.util
import json
import re
import sys
import urllib.request
from pathlib import Path

HERE = Path(__file__).resolve().parent
PLUGIN_ROOT = HERE.parents[2]
LIB_DIR = PLUGIN_ROOT / "hooks" / "hindsight" / "lib"
sys.path.insert(0, str(LIB_DIR))

from hindsight_config import load_config, recall_bank_urls  # pyright: ignore[reportMissingImports]  # noqa: E402
from hindsight_retain_gate import evaluate_retain  # pyright: ignore[reportMissingImports]  # noqa: E402

DEFAULT_SESSIONS_ROOT = Path("E:/msys64/home/Sphynx/.claude/projects")
ARTIFACTS = HERE / "artifacts"
WINDOWS_FILE = ARTIFACTS / "retain_windows.jsonl"
LABELS_FILE = ARTIFACTS / "retain_labels.jsonl"
RESULTS_FILE = ARTIFACTS / "retain_gate_results.jsonl"

# Stessi filtri del bench recall: mai portare segreti negli artefatti.
SECRET_PATTERNS = (
    re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----"),
    re.compile(r"\bAuthorization\s*:\s*(?:Bearer|Basic)\s+\S+", re.I),
    re.compile(
        r"\b(?:api[_-]?key|access[_-]?token|auth[_-]?token|client[_-]?secret|password|passwd|pwd)\s*[:=]\s*['\"]?\S{8,}",
        re.I,
    ),
    re.compile(r"\b(?:gh[pousr]_[A-Za-z0-9_]{20,}|sk-ant-[A-Za-z0-9_-]{20,}|xox[baprs]-[A-Za-z0-9-]{20,})\b"),
    re.compile(r"\beyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\b"),
)


def load_worker():
    """Il corpus usa LE STESSE funzioni finestra del worker di produzione
    (summarize_window + build_content_chunk): un corpus costruito diversamente
    misurerebbe un gate su input che in produzione non esistono."""
    spec = importlib.util.spec_from_file_location(
        "retain_worker_bench", HERE.parent / "hindsight-retain-worker.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def has_secret(text: str) -> bool:
    return any(p.search(text) for p in SECRET_PATTERNS)


def iter_transcripts(root: Path):
    for project_dir in sorted(root.iterdir()):
        if not project_dir.is_dir():
            continue
        for transcript in sorted(project_dir.glob("*.jsonl")):
            yield project_dir.name, transcript


def build_corpus(root: Path, target: int, every_n: int, overlap: int) -> None:
    worker = load_worker()
    window_turns = every_n + overlap
    seen: set[str] = set()
    windows: list[dict] = []
    per_project: dict[str, int] = {}
    # Cap per progetto: il corpus deve coprire >=5 repository, non farsi
    # monopolizzare dal progetto piu' loquace.
    per_project_cap = max(1, target // 5)

    for project, transcript in iter_transcripts(root):
        if len(windows) >= target:
            break
        if per_project.get(project, 0) >= per_project_cap:
            continue
        entries = worker.load_transcript(str(transcript), max_lines=4000)
        if not entries:
            continue
        # Ricostruzione della cadenza reale: uno Stop dopo ogni turno assistant,
        # retain effettivo ogni every_n Stop (throttling di produzione).
        user_seen = 0
        prefix: list[dict] = []
        for entry in entries:
            prefix.append(entry)
            msg = entry.get("message") or {}
            role = msg.get("role") or entry.get("type")
            if role != "user":
                continue
            user_seen += 1
            if user_seen % every_n != 0:
                continue
            summary = worker.summarize_window(prefix, window_turns)
            content = worker.build_content_chunk(
                {"cwd": "", "session_id": transcript.stem}, summary
            )
            if not content or has_secret(content):
                continue
            window_id = hashlib.sha256(content.encode("utf-8")).hexdigest()[:16]
            if window_id in seen:
                continue
            seen.add(window_id)
            windows.append(
                {
                    "id": window_id,
                    "project": project,
                    "transcript": transcript.name,
                    "turns": summary["turns"],
                    "content": content,
                }
            )
            per_project[project] = per_project.get(project, 0) + 1
            if len(windows) >= target or per_project[project] >= per_project_cap:
                break

    ARTIFACTS.mkdir(exist_ok=True)
    with WINDOWS_FILE.open("w", encoding="utf-8") as handle:
        for window in windows:
            handle.write(json.dumps(window, ensure_ascii=False) + "\n")
    print(f"[corpus] {len(windows)} finestre da {len(per_project)} progetti -> {WINDOWS_FILE}")
    print(f"[corpus] etichetta manualmente in {LABELS_FILE} (una riga JSON per id)")


def read_jsonl(path: Path) -> list[dict]:
    if not path.exists():
        return []
    out = []
    with path.open(encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if line:
                out.append(json.loads(line))
    return out


def dry_run_extract(api_base: str, bank: str, content: str, timeout: float) -> int:
    """POST dry-run-extract: numero di fatti candidati (nessuna persistenza)."""
    url = f"{api_base}/banks/{bank}/memories/dry-run-extract"
    req = urllib.request.Request(
        url,
        data=json.dumps({"items": [{"content": content}]}).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=timeout) as res:
        data = json.loads(res.read().decode("utf-8", errors="replace"))
    facts = data.get("facts") or data.get("items") or []
    return len(facts)


def percentile(values: list[float], pct: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    index = min(len(ordered) - 1, max(0, round(pct / 100 * (len(ordered) - 1))))
    return ordered[index]


def evaluate(args) -> int:
    cfg = load_config()
    if args.model:
        cfg["retain_gate_model"] = args.model
    windows = {w["id"]: w for w in read_jsonl(WINDOWS_FILE)}
    labels = read_jsonl(LABELS_FILE)
    if not windows or not labels:
        print(f"[evaluate] servono {WINDOWS_FILE} e {LABELS_FILE} (vedi --build-corpus)")
        return 1
    labeled = [(l, windows[l["id"]]) for l in labels if l.get("id") in windows]
    print(f"[evaluate] {len(labeled)} finestre etichettate, modello {cfg['retain_gate_model']}")

    bank_urls = recall_bank_urls(cfg) if args.with_dedup else []

    def run(pair):
        label, window = pair
        summary = {"turns": [tuple(t) for t in window.get("turns", [])]}
        result = evaluate_retain(window["content"], summary, bank_urls, cfg)
        return label, window, result

    rows = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=args.workers) as pool:
        for i, (label, window, result) in enumerate(pool.map(run, labeled), 1):
            rows.append((label, window, result))
            print(f"\r[evaluate] {i}/{len(labeled)}", end="", flush=True)
    print()

    tech_errors = [r for _l, _w, r in rows if r.error]
    predicted_retain = [(l, w, r) for l, w, r in rows if r.action == "retain"]
    expected_retain = [(l, w, r) for l, w, r in rows if l["expected_action"] == "retain"]
    tp = [x for x in predicted_retain if x[0]["expected_action"] == "retain"]
    critical_fn = [
        (l, w, r)
        for l, w, r in rows
        if l["expected_action"] == "retain" and l.get("critical") and r.action != "retain"
    ]
    duplicates = [(l, w, r) for l, w, r in rows if l.get("duplicate_of")]
    dup_suppressed = [x for x in duplicates if x[2].action != "retain"]
    uncertain = [x for x in rows if x[2].action == "uncertain"]
    latencies = [r.latency_ms for _l, _w, r in rows if r.latency_ms]

    def pct(part, whole):
        return 100.0 * len(part) / len(whole) if whole else 0.0

    print(f"  precisione retain      : {pct(tp, predicted_retain):5.1f}%  ({len(tp)}/{len(predicted_retain)})")
    print(f"  copertura retain-worthy: {pct(tp, expected_retain):5.1f}%  ({len(tp)}/{len(expected_retain)})")
    print(f"  falsi negativi critici : {len(critical_fn)}")
    print(f"  riduzione POST         : {pct([x for x in rows if x[2].action != 'retain'], rows):5.1f}%")
    print(f"  duplicati soppressi    : {pct(dup_suppressed, duplicates):5.1f}%  ({len(dup_suppressed)}/{len(duplicates)})")
    print(f"  quota uncertain        : {pct(uncertain, rows):5.1f}%")
    print(f"  errori tecnici gate    : {pct(tech_errors, rows):5.1f}%  ({len(tech_errors)})")
    print(f"  latenza gate p95       : {percentile(latencies, 95) / 1000:.2f}s")

    if args.dry_run_extract:
        base = (cfg.get("bank") or {}).get("api_base", "").rstrip("/")
        for label, window, result in predicted_retain[: args.dry_run_extract]:
            try:
                n = dry_run_extract(base, args.bench_bank, window["content"], 60)
                print(f"  [dry-run] {window['id']}: {n} fatti candidati")
            except Exception as exc:  # noqa: BLE001 — ispezione best-effort
                print(f"  [dry-run] {window['id']}: errore {type(exc).__name__}: {exc}")

    ARTIFACTS.mkdir(exist_ok=True)
    with RESULTS_FILE.open("w", encoding="utf-8") as handle:
        for label, window, result in rows:
            handle.write(
                json.dumps(
                    {
                        "id": window["id"],
                        "expected": label["expected_action"],
                        "predicted": result.action,
                        "reason": result.reason,
                        "preview": result.preview,
                        "context": result.context,
                        "duplicate_of": result.duplicate_of,
                        "latency_ms": result.latency_ms,
                        "error": result.error,
                    },
                    ensure_ascii=False,
                )
                + "\n"
            )
    print(f"[evaluate] dettaglio per finestra -> {RESULTS_FILE}")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--build-corpus", action="store_true")
    parser.add_argument("--evaluate", action="store_true")
    parser.add_argument("--sessions-root", type=Path, default=DEFAULT_SESSIONS_ROOT)
    parser.add_argument("--target", type=int, default=120, help="finestre corpus")
    parser.add_argument("--every-n", type=int, default=3)
    parser.add_argument("--overlap", type=int, default=1)
    parser.add_argument("--model", default="", help="override retain_gate_model")
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument("--with-dedup", action="store_true", help="usa i bank reali per il controllo duplicati")
    parser.add_argument("--dry-run-extract", type=int, default=0, metavar="N", help="ispeziona N finestre retain via dry-run-extract")
    parser.add_argument("--bench-bank", default="retain-gate-bench")
    args = parser.parse_args()

    if args.build_corpus:
        build_corpus(args.sessions_root, args.target, args.every_n, args.overlap)
        return 0
    if args.evaluate:
        return evaluate(args)
    parser.print_help()
    return 1


if __name__ == "__main__":
    sys.exit(main())
