#!/usr/bin/env python
"""Benchmark del retain gate: gpt-5.6-luna (gate di produzione) contro TypeSafe Jev.

Misura solo la domanda "questa finestra contiene conoscenza durevole?": il
controllo duplicati e' escluso (bank_urls vuoto), cosi' i due sistemi vedono
lo stesso input. Il rumore che interessa e' "troppe memorie salvate".

  --run      per ogni finestra di artifacts/jev/windows.jsonl chiama luna
             (evaluate_retain con retain_jev_enabled=False: "luna da solo") e
             Jev (ask_jev del gate, una richiesta con tutte le QUESTIONS);
             scrive artifacts/jev/results.jsonl. Riprende dalle finestre gia'
             fatte.
  --report   confronta i risultati con le label (artifacts/jev/retain_labels.jsonl
             se esiste, altrimenti i draft labels_part*.jsonl) e stampa:
             precisione/copertura di luna, curva a soglie di Jev, chiamate a
             luna evitate usando Jev come pre-filtro, regola di produzione
             (luna retain E F1 >= retain_jev_threshold, ICH-163).
  --split    tune|test: limita il report a una meta' del dataset, divisa per
             sessione (serve artifacts/<dir>/dataset.jsonl). La soglia si
             sceglie su tune, test si guarda una volta sola.

Domande, nota di stato, ask_jev e jev_score (F1) vivono nel gate
(lib/hindsight_retain_gate.py): una sola copia, la stessa della produzione.

Chiavi: OPENAI_API_KEY (luna), TYPESAFE_API_KEY (Jev). Contenuti solo negli
artefatti locali ignorati da Git; su stdout solo conteggi e metriche.
"""

from __future__ import annotations

import argparse
import concurrent.futures
import hashlib
import json
import os
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "lib"))

from hindsight_config import load_config  # pyright: ignore[reportMissingImports]  # noqa: E402
from hindsight_retain_gate import (  # pyright: ignore[reportMissingImports]  # noqa: E402
    JEV_MODEL,
    ask_jev,
    evaluate_retain,
    jev_score,
)

ART = HERE / "artifacts" / "jev"
WINDOWS = ART / "windows.jsonl"
RESULTS = ART / "results.jsonl"
JEV_TIMEOUT = 30

RETAIN_TYPES = [
    "durable_decision",
    "root_cause_or_workaround",
    "environment_constraint",
    "convention_or_preference",
    "discarded_approach",
]


def read_jsonl(path: Path) -> list[dict]:
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def jev_row(content: str) -> dict:
    p, latency = ask_jev(content, JEV_TIMEOUT)
    return {"p": p, "latency_ms": round(latency, 1)}


def group(d: dict) -> str:
    """Sessione di una riga di dataset.jsonl: le finestre della stessa sessione
    stanno tutte nella stessa meta'."""
    return d["transcript"] if d["source"] == "transcript" else d["old_id"]


def half(d: dict) -> str:
    h = int(hashlib.sha256(group(d).encode("utf-8")).hexdigest()[:8], 16)
    return "tune" if h % 2 == 0 else "test"


def refresh_jev(args) -> int:
    """Rifà solo le richieste Jev (dopo aver cambiato QUESTIONS); luna resta."""
    if not os.environ.get("TYPESAFE_API_KEY"):
        print("[jev-only] FAIL: serve TYPESAFE_API_KEY")
        return 1
    content = {w["id"]: w["content"] for w in read_jsonl(WINDOWS)}
    rows = read_jsonl(RESULTS)

    def one(row: dict) -> dict:
        try:
            row["jev"] = jev_row(content[row["id"]])
        except Exception as exc:  # noqa: BLE001
            row["jev"] = {"error": f"{type(exc).__name__}: {exc}"}
        return row

    with concurrent.futures.ThreadPoolExecutor(max_workers=args.workers) as pool:
        rows = list(pool.map(one, rows))
    RESULTS.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows), encoding="utf-8")
    errors = sum(1 for r in rows if r["jev"].get("error"))
    print(f"[jev-only] {'PASS' if not errors else 'FAIL'}: {len(rows)} righe, {errors} errori -> {RESULTS}")
    return 1 if errors else 0


def run(args) -> int:
    if not os.environ.get("TYPESAFE_API_KEY") or not os.environ.get("OPENAI_API_KEY"):
        print("[run] FAIL: servono OPENAI_API_KEY e TYPESAFE_API_KEY")
        return 1
    # Colonna "luna da solo": senza questo evaluate_retain applicherebbe gia'
    # il filtro Jev di produzione.
    cfg = {**load_config(), "retain_jev_enabled": False}
    windows = read_jsonl(WINDOWS)
    done = {r["id"] for r in read_jsonl(RESULTS) if not r["luna"].get("error") and not r["jev"].get("error")}
    todo = [w for w in windows if w["id"] not in done]
    print(f"[run] {len(windows)} finestre, {len(done)} gia' fatte, {len(todo)} da fare; luna={cfg['retain_gate_model']} jev={JEV_MODEL}")

    def one(w: dict) -> dict:
        summary = {"turns": [tuple(t) for t in w.get("turns", [])]}
        g = evaluate_retain(w["content"], summary, [], cfg)
        luna = {"action": g.action, "reason": g.reason, "latency_ms": round(g.latency_ms, 1), "error": g.error}
        try:
            jev = jev_row(w["content"])
        except Exception as exc:  # noqa: BLE001 — la riga resta da rifare
            jev = {"error": f"{type(exc).__name__}: {exc}"}
        return {"id": w["id"], "luna": luna, "jev": jev}

    kept = [r for r in read_jsonl(RESULTS) if r["id"] in done]
    errors = 0
    with concurrent.futures.ThreadPoolExecutor(max_workers=args.workers) as pool:
        for i, row in enumerate(pool.map(one, todo), 1):
            kept.append(row)
            bad = row["luna"].get("error") or row["jev"].get("error")
            errors += bool(bad)
            if bad:
                print(f"[run] {i}/{len(todo)} {row['id']} ERRORE: {bad}")
            elif i % 10 == 0:
                print(f"[run] {i}/{len(todo)}")
            RESULTS.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in kept), encoding="utf-8")
    print(f"[run] {'PASS' if not errors else 'FAIL'}: {len(kept)} righe, {errors} errori -> {RESULTS}")
    return 1 if errors else 0


def pct(a: int, b: int) -> str:
    return f"{100 * a / b:5.1f}%" if b else "  n/d"


def quantile(xs: list[float], q: float) -> float:
    xs = sorted(xs)
    return xs[min(len(xs) - 1, int(q * len(xs)))] if xs else 0.0


def report(args) -> int:
    final = ART / "retain_labels.jsonl"
    label_files = [final] if final.exists() else sorted(ART.glob("labels_part*.jsonl"))
    labels = {l["id"]: l for f in label_files for l in read_jsonl(f)}
    if args.split:
        dataset = ART / "dataset.jsonl"
        if not dataset.exists():
            print(f"[report] FAIL: --split richiede {dataset}")
            return 1
        keep = {d["id"] for d in read_jsonl(dataset) if half(d) == args.split}
        labels = {i: l for i, l in labels.items() if i in keep}
    rows = [r for r in read_jsonl(RESULTS) if r["id"] in labels and not r["luna"].get("error") and not r["jev"].get("error")]
    if not rows:
        print("[report] FAIL: nessuna riga con label e senza errori")
        return 1
    gold = {r["id"]: labels[r["id"]]["expected_action"] == "retain" for r in rows}
    n_pos = sum(gold.values())
    src = "label finali" if final.exists() else "label DRAFT (non ancora revisionate)"
    split = f", meta' {args.split}" if args.split else ""
    print(f"[report] {len(rows)} finestre ({src}{split}): {n_pos} da salvare, {len(rows) - n_pos} da scartare\n")

    def line(name: str, pred: dict[str, bool], extra: str = "") -> None:
        tp = sum(1 for i, p in pred.items() if p and gold[i])
        fp = sum(1 for i, p in pred.items() if p and not gold[i])
        print(f"  {name:<28} salva {tp + fp:3d} | giuste {tp:3d} | a torto {fp:3d} | precisione {pct(tp, tp + fp)} | copertura {pct(tp, n_pos)}{extra}")

    print("luna da solo (senza il filtro Jev):")
    act = {r["id"]: r["luna"]["action"] for r in rows}
    unc = sum(1 for a in act.values() if a == "uncertain")
    line("solo retain", {i: a == "retain" for i, a in act.items()}, f" | uncertain {unc}")
    line("retain + uncertain (si')", {i: a in ("retain", "uncertain") for i, a in act.items()})

    scorers = {
        "core": lambda p: p["core"],
        "max tipi retain": lambda p: max(p[k] for k in RETAIN_TYPES),
    }
    for name, f in scorers.items():
        print(f"\nJev, punteggio '{name}':")
        for t in (0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8):
            line(f"soglia {t:.1f}", {r["id"]: f(r["jev"]["p"]) >= t for r in rows})

    print("\nJev come pre-filtro (punteggio 'core'): sotto soglia luna non viene chiamato")
    for t in (0.1, 0.2, 0.3, 0.4):
        below = [r for r in rows if r["jev"]["p"]["core"] < t]
        lost = sum(1 for r in below if gold[r["id"]])
        print(f"  soglia {t:.1f}: chiamate luna evitate {len(below):3d}/{len(rows)} ({pct(len(below), len(rows)).strip()}) | memorie giuste perse {lost}/{n_pos}")

    # Regola di produzione (ICH-163): luna retain E Jev F1 >= soglia di config;
    # luna uncertain resta una domanda all'utente.
    threshold = float(load_config()["retain_jev_threshold"])
    print(f"\nRegola di produzione: luna retain E Jev F1 >= {threshold} (uncertain -> domanda {unc}):")
    frozen = {r["id"]: r["luna"]["action"] == "retain" and jev_score(r["jev"]["p"]) >= threshold for r in rows}
    line("regola di produzione", frozen)
    for t in (0.41, 0.44, 0.47, 0.50, 0.53):
        line(f"luna E F1 >= {t:.2f}", {r["id"]: r["luna"]["action"] == "retain" and jev_score(r["jev"]["p"]) >= t for r in rows})

    source = {w["id"]: w.get("source", "transcript") for w in read_jsonl(WINDOWS)}
    for field, values in (("source", sorted(set(source.values()))), ("trap", sorted({l.get("trap", "none") for l in labels.values()}))):
        if len(values) < 2:
            continue
        print(f"\nPer {field} (salvate a torto / da salvare perse): luna | regola di produzione")
        for v in values:
            ids = [r["id"] for r in rows if (source.get(r["id"]) if field == "source" else labels[r["id"]].get("trap", "none")) == v]
            if not ids:
                continue
            luna_fp = sum(1 for i in ids if act[i] == "retain" and not gold[i])
            luna_fn = sum(1 for i in ids if act[i] != "retain" and gold[i])
            fr_fp = sum(1 for i in ids if frozen[i] and not gold[i])
            fr_fn = sum(1 for i in ids if not frozen[i] and gold[i])
            print(f"  {v:<32} n={len(ids):3d} | luna {luna_fp:2d} torto / {luna_fn:2d} perse | regola {fr_fp:2d} torto / {fr_fn:2d} perse")

    print("\nLatenza (ms):")
    for who in ("luna", "jev"):
        xs = [r[who]["latency_ms"] for r in rows]
        print(f"  {who:<5} p50 {quantile(xs, .5):7.0f} | p90 {quantile(xs, .9):7.0f} | max {max(xs):7.0f}")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--run", action="store_true")
    ap.add_argument("--report", action="store_true")
    ap.add_argument("--jev-only", action="store_true", help="rifà solo Jev sulle righe di results.jsonl")
    ap.add_argument("--workers", type=int, default=4)
    ap.add_argument("--split", choices=("tune", "test"), help="solo una meta' del dataset (report)")
    ap.add_argument("--dir", default="jev", help="sottocartella di artifacts/ (jev = ICH-89, jev2 = dataset v2)")
    args = ap.parse_args()
    global ART, WINDOWS, RESULTS
    ART = HERE / "artifacts" / args.dir
    WINDOWS, RESULTS = ART / "windows.jsonl", ART / "results.jsonl"
    if args.jev_only:
        return refresh_jev(args)
    if not (args.run or args.report):
        ap.error("serve --run e/o --report")
    rc = run(args) if args.run else 0
    return rc or (report(args) if args.report else 0)


if __name__ == "__main__":
    sys.exit(main())
