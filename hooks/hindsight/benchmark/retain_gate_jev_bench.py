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
  --claims   (ICH-164) per ogni finestra con luna retain chiede a Jev un
             giudizio su ogni durable_claim, in due forme di state (C1 claim
             da solo, C2 claim + finestra); scrive artifacts/<dir>/claims.jsonl.
             Con claims.jsonl presente --report sceglie su tune aggregazione e
             soglia (costo 2 x a_torto + perse) e le valuta una volta su test.

Domande, nota di stato, ask_jev e jev_score (F1) vivono nel gate
(lib/hindsight_retain_gate.py): una sola copia, la stessa della produzione.

Chiavi: OPENAI_API_KEY (luna), TYPESAFE_API_KEY (Jev). Contenuti solo negli
artefatti locali ignorati da Git; su stdout solo conteggi e metriche.
"""

from __future__ import annotations

import argparse
import concurrent.futures
import hashlib
import itertools
import json
import os
import sys
from collections import defaultdict
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
CLAIMS = ART / "claims.jsonl"
JEV_TIMEOUT = 30

RETAIN_TYPES = [
    "durable_decision",
    "root_cause_or_workaround",
    "environment_constraint",
    "convention_or_preference",
    "discarded_approach",
]

# ICH-164: domande riformulate sul singolo claim. Le chiavi di F1 sono le
# stesse delle QUESTIONS di finestra, cosi' jev_score vale anche qui.
CLAIM_NOTE = (
    "A single claim extracted from a conversation between a developer and the "
    "Claude Code coding assistant (may be in Italian). It is being considered "
    "for storage in the assistant's long-term memory."
)
CLAIM_QUESTIONS = {
    "root_cause_or_workaround": "Does this claim state a root cause or a workaround that was confirmed to work?",
    "discarded_approach": "Does this claim describe an approach that was tried and discarded, with the reason it failed?",
    "environment_constraint": "Does this claim describe a non-obvious constraint or quirk of the user's environment, tools or versions?",
    "durable_decision": "Does this claim state a decision or convention together with its rationale?",
    "convention_or_preference": "Does this claim state a user preference or rule about how the assistant should work?",
    "ephemeral": "Is this claim only about momentary state (something true now but not lasting)?",
    "repo_recoverable": "Is this claim easily recoverable by reading the repository, the code or the git history?",
    "unverified": "Is this claim a hypothesis that was not confirmed by evidence (test, command result, or the user)?",
}
CLAIM_FORMS = ("C1", "C2")
# Soglie da 0,05 a 0,80 a passi di 0,01.
THRESHOLDS = [round(0.05 + 0.01 * k, 2) for k in range(76)]


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
        luna = {
            "action": g.action,
            "reason": g.reason,
            "durable_claims": g.durable_claims,
            "preview": g.preview,
            "latency_ms": round(g.latency_ms, 1),
            "error": g.error,
        }
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


def claim_state(form: str, claim: str, window: str) -> dict:
    """C1: claim da solo; C2: claim con la finestra come contesto."""
    state = {"about": CLAIM_NOTE, "claim": claim}
    return state if form == "C1" else {**state, "window": window}


def claim_key(r: dict) -> tuple:
    # Il testo del claim fa parte della chiave: dopo un nuovo --run i claim
    # cambiati vanno richiesti di nuovo.
    return (r["id"], r["i"], r["form"], r["claim"])


def expected_claims(rows: list[dict]) -> list[tuple]:
    return [
        (r["id"], i, form, claim)
        for r in rows
        if r["luna"]["action"] == "retain"
        for i, claim in enumerate(r["luna"].get("durable_claims", []))
        for form in CLAIM_FORMS
    ]


def run_claims(args) -> int:
    if not os.environ.get("TYPESAFE_API_KEY"):
        print("[claims] FAIL: serve TYPESAFE_API_KEY")
        return 1
    content = {w["id"]: w["content"] for w in read_jsonl(WINDOWS)}
    wanted = expected_claims(read_jsonl(RESULTS))
    wanted_set = set(wanted)
    kept = [r for r in read_jsonl(CLAIMS) if not r.get("error") and claim_key(r) in wanted_set]
    done = {claim_key(r) for r in kept}
    todo = [k for k in wanted if k not in done]
    print(f"[claims] {len(wanted)} richieste (claim x forma), {len(done)} gia' fatte, {len(todo)} da fare")

    def one(k: tuple) -> dict:
        wid, i, form, claim = k
        row = {"id": wid, "i": i, "form": form, "claim": claim}
        try:
            p, ms = ask_jev("", JEV_TIMEOUT, state=claim_state(form, claim, content[wid]), questions=CLAIM_QUESTIONS)
            row.update(p=p, latency_ms=round(ms, 1))
        except Exception as exc:  # noqa: BLE001 — la riga resta da rifare
            row["error"] = f"{type(exc).__name__}: {exc}"
        return row

    errors = 0
    with concurrent.futures.ThreadPoolExecutor(max_workers=args.workers) as pool:
        for n, row in enumerate(pool.map(one, todo), 1):
            kept.append(row)
            errors += bool(row.get("error"))
            if row.get("error"):
                print(f"[claims] {n}/{len(todo)} {row['id']}#{row['i']} {row['form']} ERRORE: {row['error']}")
            elif n % 50 == 0:
                print(f"[claims] {n}/{len(todo)}")
    CLAIMS.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in kept), encoding="utf-8")
    print(f"[claims] {'PASS' if not errors else 'FAIL'}: {len(kept)} righe, {errors} errori -> {CLAIMS}")
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


def claim_score(p: dict, unverified: bool = False) -> float:
    """claimF: la F1 applicata al claim; A3 la smorza anche per unverified."""
    s = jev_score(p)
    return s * (1 - p["unverified"]) if unverified else s


def rule_cost(pred: dict[str, bool], gold: dict[str, bool]) -> tuple[int, int, int]:
    """(costo, a torto, perse), con costo = 2 x a_torto + perse."""
    fp = sum(1 for i, p in pred.items() if p and not gold[i])
    fn = sum(1 for i, p in pred.items() if not p and gold[i])
    return 2 * fp + fn, fp, fn


def pick_threshold(rule, grid: list[tuple], gold: dict[str, bool]) -> tuple:
    """Le soglie di grid a costo minimo su gold. A parita' di costo vince la
    soglia piu' alta; con due soglie conta prima la prima."""
    return min(grid, key=lambda t: (rule_cost({i: rule(i, *t) for i in gold}, gold)[0], [-x for x in t]))


# Nome -> (claimF con unverified, in unione con la F1 di finestra).
AGGREGATIONS = {
    "A1": (False, False),
    "A2": (False, True),
    "A3/A1": (True, False),
    "A3/A2": (True, True),
}


def aggregate(retain: bool, f1: float, max_claim: float, union: bool, t: tuple) -> bool:
    """Sempre in AND con luna retain. A1: max claimF >= t; A2: F1 di finestra
    >= t1 oppure max claimF >= t2. Senza claim max claimF vale 0."""
    if not retain:
        return False
    return (f1 >= t[0] or max_claim >= t[1]) if union else max_claim >= t[0]


def claims_report() -> int:
    """ICH-164: forma, aggregazione e soglia scelte su tune; test si guarda
    una volta sola, solo per la regola scelta."""
    claims = [c for c in read_jsonl(CLAIMS) if not c.get("error")]
    if not claims:
        return 0
    labels = {l["id"]: l for l in read_jsonl(ART / "retain_labels.jsonl")}
    halves = {d["id"]: half(d) for d in read_jsonl(ART / "dataset.jsonl")}
    if not labels or not halves:
        print("[claims] FAIL: servono retain_labels.jsonl e dataset.jsonl")
        return 1
    rows = [
        r for r in read_jsonl(RESULTS)
        if r["id"] in labels and r["id"] in halves and not r["luna"].get("error") and not r["jev"].get("error")
    ]
    got = {claim_key(c): c for c in claims}
    by_window = defaultdict(list)
    for k in expected_claims(rows):
        by_window[k[0]].append(got.get(k))
    incomplete = {i for i, cs in by_window.items() if None in cs}
    rows = [r for r in rows if r["id"] not in incomplete]
    print(f"\n[claims] Jev per claim: {len(rows)} finestre, {len(incomplete)} escluse per claim mancanti o in errore")

    gold = {r["id"]: labels[r["id"]]["expected_action"] == "retain" for r in rows}
    retain = {r["id"]: r["luna"]["action"] == "retain" for r in rows}
    f1 = {r["id"]: jev_score(r["jev"]["p"]) for r in rows}
    tune = {i: g for i, g in gold.items() if halves[i] == "tune"}
    test = {i: g for i, g in gold.items() if halves[i] == "test"}

    print(f"\nScelta su tune ({len(tune)} finestre, {sum(tune.values())} da salvare), costo = 2 x a torto + perse:")
    candidates = []
    for form in CLAIM_FORMS:
        for name, (unverified, union) in AGGREGATIONS.items():
            mc = {
                i: max((claim_score(c["p"], unverified) for c in by_window[i] if c["form"] == form), default=0.0)
                for i in gold
            }

            def rule(i, *t, mc=mc, union=union):
                return aggregate(retain[i], f1[i], mc[i], union, t)

            grid = list(itertools.product(THRESHOLDS, THRESHOLDS)) if union else [(t,) for t in THRESHOLDS]
            t = pick_threshold(rule, grid, tune)
            cost, fp, fn = rule_cost({i: rule(i, *t) for i in tune}, tune)
            label = f"{form} {name} " + "/".join(f"{x:.2f}" for x in t)
            print(f"  {label:<24} costo {cost:3d} | a torto {fp:3d} | perse {fn:3d}")
            candidates.append((cost, label, rule, t))
    # A parita' di costo vince la prima nell'ordine: C1 prima di C2, A1 prima di A2.
    _, chosen_label, chosen_rule, chosen_t = min(candidates, key=lambda c: c[0])
    threshold = float(load_config()["retain_jev_threshold"])
    baseline = f"luna + F1 >= {threshold}"
    chosen = f"luna + {chosen_label}"
    preds = {
        "luna da solo": {i: retain[i] for i in test},
        baseline: {i: retain[i] and f1[i] >= threshold for i in test},
        chosen: {i: chosen_rule(i, *chosen_t) for i in test},
    }

    n_pos = sum(test.values())
    buried = [i for i in test if test[i] and labels[i].get("trap") == "root_cause_buried"]
    print(f"\nVerifica su test ({len(test)} finestre, {n_pos} da salvare), una volta sola:")
    for name, pred in preds.items():
        _, fp, fn = rule_cost(pred, test)
        lost = sum(1 for i in buried if not pred[i])
        print(f"  {name:<34} salva {sum(pred.values()):3d} | a torto {fp:3d} | buone perse {fn:2d}/{n_pos} | cause radice sepolte perse {lost:2d}/{len(buried)}")

    print(f"\nPer trap su test (a torto / perse): {baseline} | {chosen}")
    for v in sorted({labels[i].get("trap", "none") for i in test}):
        ids = [i for i in test if labels[i].get("trap", "none") == v]
        cells = [
            f"{sum(1 for i in ids if pred[i] and not test[i]):2d} torto / {sum(1 for i in ids if not pred[i] and test[i]):2d} perse"
            for pred in (preds[baseline], preds[chosen])
        ]
        print(f"  {v:<32} n={len(ids):3d} | {cells[0]} | {cells[1]}")

    n_claims = [len(r["luna"].get("durable_claims", [])) for r in rows if retain[r["id"]]]
    print(f"\nClaim per finestra con luna retain: media {sum(n_claims) / max(1, len(n_claims)):.2f} su {len(n_claims)} finestre, {n_claims.count(0)} senza claim")
    print("Latenza Jev per finestra (ms), somma e massimo sui claim:")
    for form in CLAIM_FORMS:
        lat = [[c["latency_ms"] for c in by_window[i] if c["form"] == form] for i in gold if by_window[i]]
        sums, maxs = [sum(x, 0.0) for x in lat], [max(x) for x in lat]
        print(f"  {form} somma p50 {quantile(sums, .5):6.0f} p90 {quantile(sums, .9):6.0f} | massimo p50 {quantile(maxs, .5):6.0f} p90 {quantile(maxs, .9):6.0f}")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--run", action="store_true")
    ap.add_argument("--report", action="store_true")
    ap.add_argument("--claims", action="store_true", help="Jev su ogni durable_claim di luna (ICH-164)")
    ap.add_argument("--jev-only", action="store_true", help="rifà solo Jev sulle righe di results.jsonl")
    ap.add_argument("--workers", type=int, default=4)
    ap.add_argument("--split", choices=("tune", "test"), help="solo una meta' del dataset (report)")
    ap.add_argument("--dir", default="jev", help="sottocartella di artifacts/ (jev = ICH-89, jev2 = dataset v2)")
    args = ap.parse_args()
    global ART, WINDOWS, RESULTS, CLAIMS
    ART = HERE / "artifacts" / args.dir
    WINDOWS, RESULTS, CLAIMS = ART / "windows.jsonl", ART / "results.jsonl", ART / "claims.jsonl"
    if args.jev_only:
        return refresh_jev(args)
    if not (args.run or args.claims or args.report):
        ap.error("serve --run, --claims e/o --report")
    rc = run(args) if args.run else 0
    rc = rc or (run_claims(args) if args.claims else 0)
    return rc or ((report(args) or claims_report()) if args.report else 0)


if __name__ == "__main__":
    sys.exit(main())
