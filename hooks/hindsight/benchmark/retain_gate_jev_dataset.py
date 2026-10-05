#!/usr/bin/env python
"""Dataset v2 del benchmark retain gate (luna vs Jev): 200 finestre.

  --pool     finestre NON sovrapposte (4 turni umani, confine = Stop prima del
             prompt successivo) da tutti i transcript di ~/.claude/projects,
             esclusa la sessione corrente; per ognuna salva le COORDINATE
             (transcript, indici entry) e la conversazione COMPLETA (tool
             compresi) per chi etichetta. Aggiunge 60 finestre grezze storiche
             salvate dal vecchio gate nel bank Hindsight (testo fisso, non
             rigenerabili). -> artifacts/jev2/pool.jsonl
  --rebuild  rigenera il content delle finestre da transcript con il codice
             ATTUALE del worker (dopo modifiche al builder) -> windows.jsonl

Contenuti solo negli artefatti locali ignorati da Git.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import random
import sys
import urllib.request
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "lib"))
from hindsight_retain_gate_bench import SECRET_PATTERNS, load_worker  # noqa: E402

ART = HERE / "artifacts" / "jev2"
POOL = ART / "pool.jsonl"
WINDOWS = ART / "windows.jsonl"
DATASET = ART / "dataset.jsonl"  # le 200 selezionate (id univoci); il rebuild parte da qui
ROOT = Path("E:/msys64/home/Sphynx/.claude/projects")
EXCLUDE_SESSIONS = {"7a59146f-65a8-4ff2-976c-5093c5042b5a"}  # questa sessione (e' il tema del bench)
NOT_AFTER = "2026-10-05T12:00"  # le sessioni nate dopo (es. il fork) restano fuori
API = "http://127.0.0.1:8888/v1/default/banks/trinity-project"
HISTORICAL = 60
TURNS = 4
FULL_CAP = 24000


def redact(text: str) -> str:
    for p in SECRET_PATTERNS:
        text = p.sub("[REDACTED]", text)
    return text


def clip(text: str, head: int, tail: int) -> str:
    return text if len(text) <= head + tail else f"{text[:head]}\n[... {len(text) - head - tail} caratteri omessi ...]\n{text[-tail:]}"


def block_text(content) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return "\n".join(b.get("text", "") for b in content if isinstance(b, dict) and b.get("type") == "text")
    return ""


def render_full(entries: list[dict], worker) -> str:
    """La conversazione come la vede chi etichetta: dialogo + tool call + esiti."""
    out = []
    for e in entries:
        msg = e.get("message") or {}
        role, content = msg.get("role") or e.get("type"), msg.get("content")
        if role == "user":
            human = worker._human_user_text(content)
            if human:
                out.append(f"[user] {human}")
            elif isinstance(content, list):
                for b in content:
                    if isinstance(b, dict) and b.get("type") == "tool_result":
                        out.append(f"[tool_result{' ERROR' if b.get('is_error') else ''}] {clip(block_text(b.get('content')), 600, 400)}")
        elif role == "assistant" and isinstance(content, list):
            for b in content:
                if not isinstance(b, dict):
                    continue
                if b.get("type") == "text" and b.get("text", "").strip():
                    out.append(f"[assistant] {b['text'].strip()}")
                elif b.get("type") == "tool_use":
                    out.append(f"[tool_use {b.get('name')}] {clip(json.dumps(b.get('input'), ensure_ascii=False), 300, 100)}")
    return redact(clip("\n\n".join(out), FULL_CAP // 3, FULL_CAP * 2 // 3))


def transcript_windows(path: Path, worker) -> list[dict]:
    entries = worker.load_transcript(str(path), max_lines=10**7)
    if not entries or (entries[0].get("timestamp") or "") >= NOT_AFTER:
        return []
    humans = [
        i for i, e in enumerate(entries)
        if ((e.get("message") or {}).get("role") or e.get("type")) == "user"
        and worker._human_user_text((e.get("message") or {}).get("content"))
    ]
    rows = []
    for k in range(0, len(humans) - TURNS + 1, TURNS):
        start = humans[k]
        end = humans[k + TURNS] if k + TURNS < len(humans) else len(entries)
        summary = worker.summarize_window(entries[:end], TURNS)
        content = worker.build_content_chunk({"cwd": "", "session_id": path.stem}, summary)
        if not content:
            continue
        rows.append({
            "id": hashlib.sha256(f"{path.name}:{start}:{end}".encode()).hexdigest()[:16],
            "source": "transcript",
            "project": path.parent.name,
            "transcript": str(path),
            "start": start,
            "end": end,
            "date": (entries[start].get("timestamp") or "")[:10],
            "content": redact(content),
            "full": render_full(entries[start:end], worker),
        })
    return rows


def historical_windows() -> list[dict]:
    docs, off = [], 0
    while True:
        page = json.load(urllib.request.urlopen(f"{API}/documents?limit=100&offset={off}", timeout=30))
        for d in page["items"]:
            doc = json.load(urllib.request.urlopen(f"{API}/documents/{d['id']}", timeout=30))
            text = doc.get("original_text") or doc.get("text") or ""
            if text.startswith("## Conversation"):
                docs.append({
                    "id": "h" + hashlib.sha256(d["id"].encode()).hexdigest()[:15],
                    "source": "hindsight",
                    "project": ",".join(d.get("tags") or []),
                    "date": d["created_at"][:10],
                    "content": redact(text),
                    "full": redact(text),
                })
        off += 100
        if off >= page["total"]:
            break
    random.Random(42).shuffle(docs)
    print(f"[pool] finestre storiche in Hindsight: {len(docs)}, prese {min(HISTORICAL, len(docs))}")
    return docs[:HISTORICAL]


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--pool", action="store_true")
    ap.add_argument("--rebuild", action="store_true")
    args = ap.parse_args()
    worker = load_worker()
    ART.mkdir(parents=True, exist_ok=True)
    if args.pool:
        rows = []
        for path in sorted(ROOT.glob("*/*.jsonl")):
            if path.stem not in EXCLUDE_SESSIONS:
                rows += transcript_windows(path, worker)
        print(f"[pool] finestre da transcript: {len(rows)} da {len({r['transcript'] for r in rows})} sessioni")
        rows += historical_windows()
        POOL.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows), encoding="utf-8")
        print(f"[pool] PASS: {len(rows)} finestre -> {POOL}")
    if args.rebuild:
        out = []
        for r in (json.loads(line) for line in DATASET.read_text(encoding="utf-8").splitlines()):
            if r["source"] == "transcript":
                entries = worker.load_transcript(r["transcript"], max_lines=10**7)
                summary = worker.summarize_window(entries[: r["end"]], TURNS)
                r["content"] = redact(worker.build_content_chunk({"cwd": "", "session_id": Path(r["transcript"]).stem}, summary) or "")
            out.append({k: r[k] for k in ("id", "source", "project", "content")})
        WINDOWS.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in out), encoding="utf-8")
        print(f"[rebuild] PASS: {len(out)} finestre -> {WINDOWS}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
