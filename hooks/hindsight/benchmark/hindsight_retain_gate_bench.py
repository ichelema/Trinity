#!/usr/bin/env python
"""Benchmark offline del gate semantico pre-retain (ICH-67).

Due fasi:

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
   "durable_claims": ["..."], "duplicate_of": ["mem-..."],
   "duplicate_kind": "exact|semantic", "critical": false}

`duplicate_kind` e' richiesto per misurare separatamente i target dei
duplicati, rivisti da ICH-84: exact >=80%, semantic >=84% (~2 miss ammessi per
categoria, con causa nota: fatti del documento fuori dai top-k del recall o
citazioni di documenti affini; un terzo miss e' una regressione), piu' due
guardie bloccanti a zero — "copertura ignorata" e "falsi duplicati". Tutto
applicato solo quando il dataset contiene label duplicate; in quel caso il
dataset deve contenere entrambe le categorie e l'evaluate richiede
--with-dedup; input incompleto o target mancati restituiscono un codice di
uscita non zero. Protocollo di misura: 3 run e mediana, per i target E per le
guardie (la varianza su 10-13 finestre e' di +-1-2 finestre a run: un exit 1
su una run singola chiede di completare il protocollo, non e' da solo un FAIL
del gate di merge). Un dataset senza duplicati mantiene il contratto storico
ICH-67: exit 0 se la run tecnica va a buon fine.

Il bank della misura controllata (--dedup-bank-url) resta production-like,
observation di consolidamento COMPRESE: da ICH-89 il gate chiede al recall solo
i raw fact (types world/experience), quindi le observation — derivate, senza
document_id, riscritte in background — non entrano piu' fra i candidati ne' in
bench ne' in produzione, e non vanno piu' disattivate sul bank di misura.

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
    duplicates = [label for label, _window in labeled if label.get("duplicate_of")]
    invalid_kinds = [
        label.get("id")
        for label in duplicates
        if label.get("duplicate_kind") not in {"exact", "semantic"}
    ]
    duplicate_kinds = {label.get("duplicate_kind") for label in duplicates}
    if invalid_kinds:
        print(
            "[evaluate] duplicate_kind mancante/non valido per: "
            + ", ".join(str(item) for item in invalid_kinds)
        )
        return 1
    if duplicates and duplicate_kinds != {"exact", "semantic"}:
        missing = {"exact", "semantic"} - duplicate_kinds
        print(
            "[evaluate] dataset duplicati incompleto; categorie mancanti: "
            + ", ".join(sorted(missing))
        )
        return 1
    if duplicates and not args.with_dedup:
        print("[evaluate] le label duplicate richiedono --with-dedup")
        return 1
    print(f"[evaluate] {len(labeled)} finestre etichettate, modello {cfg['retain_gate_model']}")

    if not args.with_dedup:
        bank_urls = []
    elif args.dedup_bank_url:
        # Misura controllata (piano ICH-72): un bank popolato ad hoc al posto
        # dei bank reali, cosi' i candidati di dedup sono noti e stabili.
        bank_urls = [args.dedup_bank_url]
    else:
        bank_urls = recall_bank_urls(cfg)

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
    exact_duplicates = [
        x for x in duplicates if x[0].get("duplicate_kind") == "exact"
    ]
    semantic_duplicates = [
        x for x in duplicates if x[0].get("duplicate_kind") == "semantic"
    ]

    def detected_duplicate(row) -> bool:
        label, _window, result = row
        if not (
            result.action == "skip"
            and result.reason == "duplicate"
            and result.duplicate_of
        ):
            return False
        expected_ids = {str(item) for item in label.get("duplicate_of") or []}
        detected_ids = {
            str(result.candidates[index].get("id"))
            for index in result.duplicate_of
            if 0 <= index < len(result.candidates)
            and result.candidates[index].get("id") is not None
        }
        return bool(expected_ids & detected_ids)

    dup_suppressed = [x for x in duplicates if detected_duplicate(x)]
    exact_suppressed = [x for x in exact_duplicates if detected_duplicate(x)]
    semantic_suppressed = [x for x in semantic_duplicates if detected_duplicate(x)]
    uncertain = [x for x in rows if x[2].action == "uncertain"]
    latencies = [r.latency_ms for _l, _w, r in rows if r.latency_ms]

    def pct(part, whole):
        return 100.0 * len(part) / len(whole) if whole else 0.0

    print(f"  precisione retain      : {pct(tp, predicted_retain):5.1f}%  ({len(tp)}/{len(predicted_retain)})")
    print(f"  copertura retain-worthy: {pct(tp, expected_retain):5.1f}%  ({len(tp)}/{len(expected_retain)})")
    print(f"  falsi negativi critici : {len(critical_fn)}")
    print(f"  riduzione POST         : {pct([x for x in rows if x[2].action != 'retain'], rows):5.1f}%")
    print(f"  duplicati rilevati     : {pct(dup_suppressed, duplicates):5.1f}%  ({len(dup_suppressed)}/{len(duplicates)})")
    # Target rivisti (ICH-84): l'analisi dei miss persistenti ha mostrato che
    # i residui sono limiti di recall (fatti del documento fuori dai top-8 per
    # affollamento) o artefatti di misura (citazioni di documenti affini che
    # coprono davvero), non errori di giudizio; e su 10-13 finestre il 100%
    # boccia ~40% delle run sane per pura varianza (P(10/10)~0.6 con tasso
    # vero 92-95%). La quota ammessa e' ~2 miss per categoria; un terzo miss
    # e' per costruzione una regressione. Le soglie percentuali equivalgono a
    # ~2 miss SOLO sul corpus corrente (10 exact / 13 semantic): ricalibrarle
    # se cambia la cardinalita' delle label. Protocollo: 3 run e mediana.
    exact_pct = pct(exact_suppressed, exact_duplicates)
    exact_ok = not exact_duplicates or exact_pct >= 80
    if exact_duplicates:
        exact_target = "PASS" if exact_pct >= 80 else "FAIL"
        print(
            f"  duplicati exact        : {exact_pct:5.1f}%  "
            f"({len(exact_suppressed)}/{len(exact_duplicates)}) target >=80% {exact_target}"
        )
    else:
        print("  duplicati exact        : n/a (0 label) target >=80%")
    semantic_pct = pct(semantic_suppressed, semantic_duplicates)
    semantic_ok = not semantic_duplicates or semantic_pct >= 84
    if semantic_duplicates:
        semantic_target = "PASS" if semantic_pct >= 84 else "FAIL"
        print(
            f"  duplicati semantic     : {semantic_pct:5.1f}%  "
            f"({len(semantic_suppressed)}/{len(semantic_duplicates)}) target >=84% {semantic_target}"
        )
    else:
        print("  duplicati semantic     : n/a (0 label) target >=84%")
    print(f"  quota uncertain        : {pct(uncertain, rows):5.1f}%")
    print(f"  errori tecnici gate    : {pct(tech_errors, rows):5.1f}%  ({len(tech_errors)})")
    # Guardie ICH-84, bloccanti sui dataset con label duplicate e ristrette al
    # danno dimostrato (review ICH-84): copertura dichiarata su un duplicato
    # etichettato ma senza skip (il modello ha VISTO la copertura e ha salvato
    # lo stesso — il pattern esatto dei miss ICH-84), e skip "duplicate" su una
    # finestra che andava salvata (conoscenza nuova cestinata come duplicato:
    # il costo peggiore). Esiti corretti con giudizio rumoroso — retain giusto
    # con copertura parziale citata, skip giusto con reason discutibile — non
    # scattano. Sui dataset senza duplicati restano solo stampate: il
    # contratto storico ICH-67 non cambia.
    coverage_ignored = [
        (l, w, r)
        for l, w, r in rows
        if l.get("duplicate_of") and r.covered_by and r.action != "skip"
    ]
    false_duplicates = [
        (l, w, r)
        for l, w, r in rows
        # Le finestre etichettate duplicate sono escluse: il loro skip e' il
        # successo che i target contano gia', qualunque sia l'expected_action.
        if not l.get("duplicate_of")
        and l.get("expected_action") != "skip"
        and r.action == "skip"
        and r.reason == "duplicate"
    ]
    guards_ok = not duplicates or (not coverage_ignored and not false_duplicates)
    print(f"  copertura ignorata     : {len(coverage_ignored)}")
    print(f"  falsi duplicati        : {len(false_duplicates)}")
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
                        "covered_by": result.covered_by,
                        "durable_claims": result.durable_claims,
                        # TUTTI i candidati visti (non solo quelli citati in
                        # duplicate_of/covered_by): archivio per-miss (ICH-84).
                        "candidate_ids": [c.get("id") for c in result.candidates],
                        "duplicate_candidate_ids": [
                            result.candidates[index].get("id")
                            for index in result.duplicate_of
                            if 0 <= index < len(result.candidates)
                        ],
                        "latency_ms": result.latency_ms,
                        "error": result.error,
                    },
                    ensure_ascii=False,
                )
                + "\n"
            )
    print(f"[evaluate] dettaglio per finestra -> {RESULTS_FILE}")
    return 0 if exact_ok and semantic_ok and guards_ok else 1


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
    parser.add_argument("--dedup-bank-url", default="", metavar="URL", help="con --with-dedup, usa questo bank al posto dei bank reali")
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
