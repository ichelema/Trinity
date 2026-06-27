#!/usr/bin/env python
"""Promozione curata dei fatti dai bank di progetto al bank CORE.

Funnel (design multi-bank 2026-06-12): scan -> triage LLM -> review umana
(/trinity:promote) -> MOVE dei soli approvati. Questo script copre le parti
meccaniche; la review resta al comando Claude (MAI promozione automatica).

  --scan              elenca i documenti dei bank progetto non ancora revisionati
  --triage            scan + classifica ogni candidato con gpt-4.1-nano
                      ("resterebbe utile su un progetto completamente diverso?")
                      e scrive logs/promote-candidates.json
  --move ID --bank B  promuove: retain dell'original_text sul CORE (senza i tag
                      repo:/branch:, che nello scope all_strict impedirebbero la
                      fusione con lo stesso fatto da altri repo) + delete_document
                      dal bank progetto (MOVE, non copy: un fatto, un bank)
  --reject ID --bank B  marca revisionato-e-respinto (non ricompare negli scan)
  --status            riepilogo dello stato

Stato in logs/promote-state.json: TUTTI gli ID revisionati, anche i respinti
(mai tag sul documento per marcare "reviewed": frammenterebbe la consolidation).
I verdetti del triage LLM sono cachati nello stato (chiave "triage") per non
ripagare il modello sugli stessi documenti a ogni run settimanale.

NB Windows: path nei flag in stile Windows (C:/...), non MSYS (/c/...).
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone

sys.path.insert(
    0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "lib")
)
from hindsight_config import load_config, bank_url

OPENAI_URL = "https://api.openai.com/v1/chat/completions"

_TRIAGE_SYSTEM_PROMPT = """You triage facts extracted from per-project memory banks of a coding agent.
Decide if a fact should be PROMOTED to the shared CORE bank (cross-project) or KEPT in its project bank.

The key question: would this fact remain useful on a COMPLETELY DIFFERENT project?

PROMOTE examples: user preferences (tools, languages, communication style), environment
constraints (OS, shell, proxy, path conventions), reusable procedures/workarounds for the
machine or the toolchain, lessons about tools used across projects.
KEEP examples: project-specific architecture/config/decisions, file paths or components that
exist only in that project, task state, anything meaningless outside the project.

Reply in JSON: {"verdict": "promote"|"keep", "reason": "<one short sentence in Italian>"}.
When uncertain, prefer "keep" (promotion is curated, false positives cost human review time)."""

_TRIAGE_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "verdict": {"type": "string", "enum": ["promote", "keep"]},
        "reason": {"type": "string"},
    },
    "required": ["verdict", "reason"],
}


def _plugin_root() -> str:
    here = os.path.dirname(os.path.abspath(__file__))
    return os.path.abspath(os.path.join(here, "..", "..", ".."))


def _state_path() -> str:
    return os.path.join(_plugin_root(), "logs", "promote-state.json")


def _candidates_path() -> str:
    return os.path.join(_plugin_root(), "logs", "promote-candidates.json")


def _load_state() -> dict:
    try:
        with open(_state_path(), encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return {"reviewed": {}, "triage": {}}


def _save_state(state: dict) -> None:
    path = _state_path()
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=2)
    os.replace(tmp, path)


def _request(url: str, method: str = "GET", payload: dict | None = None,
             headers: dict | None = None, timeout: int = 20) -> dict:
    data = json.dumps(payload).encode("utf-8") if payload is not None else None
    hdrs = {"Accept": "application/json"}
    if payload is not None:
        hdrs["Content-Type"] = "application/json"
    hdrs.update(headers or {})
    req = urllib.request.Request(url, data=data, headers=hdrs, method=method)
    with urllib.request.urlopen(req, timeout=timeout) as res:
        body = res.read().decode("utf-8", errors="replace")
    return json.loads(body) if body.strip() else {}


def list_project_banks(cfg: dict, timeout: int) -> list[str]:
    """Tutti i bank del server tranne il core e quelli esclusi dal promote
    (sottostringhe in bank.promote_exclude_banks, case-insensitive)."""
    bankcfg = cfg.get("bank") or {}
    base = bankcfg.get("api_base", "").rstrip("/")
    core = bankcfg.get("core_bank", "")
    excludes = [s.lower() for s in bankcfg.get("promote_exclude_banks", [])]
    data = _request(f"{base}/banks", timeout=timeout)
    banks = [b["bank_id"] for b in (data.get("banks") or []) if b.get("bank_id") != core]
    return [b for b in banks if not any(x in b.lower() for x in excludes)]


def list_documents(cfg: dict, bank: str, timeout: int, page: int = 100) -> list[dict]:
    url = bank_url(cfg, bank)
    docs: list[dict] = []
    offset = 0
    while True:
        data = _request(f"{url}/documents?limit={page}&offset={offset}", timeout=timeout)
        items = data.get("items") or []
        docs.extend(items)
        total = int(data.get("total", len(docs)))
        offset += len(items)
        if not items or offset >= total:
            break
    return docs


def fetch_document(cfg: dict, bank: str, doc_id: str, timeout: int) -> dict:
    safe = urllib.parse.quote(doc_id, safe="")
    return _request(f"{bank_url(cfg, bank)}/documents/{safe}", timeout=timeout)


def scan(cfg: dict, banks: list[str] | None, timeout: int) -> list[dict]:
    """Documenti dei bank progetto non ancora revisionati (state file)."""
    state = _load_state()
    reviewed = state.get("reviewed", {})
    out: list[dict] = []
    for bank in banks or list_project_banks(cfg, timeout):
        for summ in list_documents(cfg, bank, timeout):
            doc_id = summ.get("id") or ""
            if f"{bank}/{doc_id}" in reviewed:
                continue
            out.append({"bank": bank, "doc_id": doc_id,
                        "tags": summ.get("tags") or [],
                        "created_at": summ.get("created_at") or ""})
    return out


def triage_one(text: str, model: str, timeout: int = 20) -> dict:
    """Verdetto LLM su un singolo documento. Solleva su errore (il chiamante
    decide se proseguire con gli altri)."""
    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        raise RuntimeError("OPENAI_API_KEY non impostata")
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": _TRIAGE_SYSTEM_PROMPT},
            {"role": "user", "content": text[:4000]},
        ],
        "temperature": 0.0,
        "response_format": {
            "type": "json_schema",
            "json_schema": {"name": "triage", "schema": _TRIAGE_SCHEMA, "strict": True},
        },
    }
    data = _request(OPENAI_URL, method="POST", payload=payload,
                    headers={"Authorization": f"Bearer {api_key}"}, timeout=timeout)
    return json.loads(data["choices"][0]["message"]["content"])


def cmd_scan(cfg: dict, args) -> int:
    found = scan(cfg, args.bank or None, args.timeout)
    print(json.dumps({"count": len(found), "documents": found},
                     ensure_ascii=False, indent=2))
    return 0


def cmd_triage(cfg: dict, args) -> int:
    state = _load_state()
    cache = state.setdefault("triage", {})
    model = cfg.get("context_extraction_model", "gpt-4.1-nano")
    found = scan(cfg, args.bank or None, args.timeout)
    candidates: list[dict] = []
    errors = 0
    for d in found:
        key = f"{d['bank']}/{d['doc_id']}"
        verdict = cache.get(key)
        if verdict is None or args.force:
            try:
                full = fetch_document(cfg, d["bank"], d["doc_id"], args.timeout)
                text = full.get("original_text") or ""
                if not text.strip():
                    continue
                verdict = triage_one(text, model)
                verdict["preview"] = text[:500]
                cache[key] = verdict
            except Exception as e:  # noqa: BLE001 — un doc rotto non ferma il giro
                print(f"[triage] WARN {key}: {e}", file=sys.stderr)
                errors += 1
                continue
        if verdict.get("verdict") == "promote":
            candidates.append({**d, "reason": verdict.get("reason", ""),
                               "preview": verdict.get("preview", "")})
    _save_state(state)
    report = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "scanned": len(found),
        "errors": errors,
        "count": len(candidates),
        "candidates": candidates,
    }
    out = _candidates_path()
    os.makedirs(os.path.dirname(out), exist_ok=True)
    with open(out, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)
    print(f"[triage] {len(candidates)} candidati su {len(found)} documenti -> {out}")
    return 0


def cmd_move(cfg: dict, args) -> int:
    bank, doc_id = args.bank[0], args.move
    full = fetch_document(cfg, bank, doc_id, args.timeout)
    text = full.get("original_text") or ""
    if not text.strip():
        print(f"[move] ERRORE: documento {doc_id} senza original_text", file=sys.stderr)
        return 1
    rp = full.get("retain_params") or {}
    # Strip dei tag repo:/branch:: un fatto trasversale con tag di progetto non
    # si consoliderebbe mai con lo stesso fatto arrivato da altri repo (all_strict).
    tags = [t for t in (full.get("tags") or [])
            if not t.startswith(("repo:", "branch:"))]
    item = {
        "content": text,
        "context": rp.get("context"),
        "timestamp": rp.get("event_date"),
        "metadata": {**(rp.get("metadata") or {}), "promoted_from": bank},
        "tags": tags,
        # document_id deterministico: un retry del move fa upsert sul core invece di
        # creare un doppione (l'item altrimenti prenderebbe un UUID casuale a ogni POST).
        "document_id": f"promoted:{bank}:{doc_id}",
    }
    core_url = bank_url(cfg, (cfg.get("bank") or {}).get("core_bank", ""))
    # SINCRONO: attende estrazione+embedding PRIMA del delete. Con async il "success"
    # significa solo "accodato"; un fallimento successivo del worker cancellerebbe il
    # doc dal progetto senza averlo consolidato sul core (perdita irrecuperabile).
    res = _request(f"{core_url}/memories", method="POST",
                   payload={"items": [item], "async": False}, timeout=max(args.timeout, 90))
    if not res.get("success"):
        print(f"[move] ERRORE: retain sul core fallito: {res}", file=sys.stderr)
        return 1
    print(f"[move] retain sul core OK (sync, {res.get('items_count')} item)")
    safe = urllib.parse.quote(doc_id, safe="")
    _request(f"{bank_url(cfg, bank)}/documents/{safe}", method="DELETE",
             timeout=args.timeout)
    print(f"[move] delete dal bank {bank} OK")
    state = _load_state()
    state.setdefault("reviewed", {})[f"{bank}/{doc_id}"] = {
        "decision": "promoted",
        "ts": datetime.now(timezone.utc).isoformat(),
    }
    _save_state(state)
    return 0


def cmd_reject(cfg: dict, args) -> int:
    bank, doc_id = args.bank[0], args.reject
    state = _load_state()
    state.setdefault("reviewed", {})[f"{bank}/{doc_id}"] = {
        "decision": "rejected",
        "ts": datetime.now(timezone.utc).isoformat(),
    }
    _save_state(state)
    print(f"[reject] {bank}/{doc_id} marcato revisionato (respinto)")
    return 0


def cmd_status(cfg: dict, args) -> int:
    state = _load_state()
    reviewed = state.get("reviewed", {})
    promoted = sum(1 for v in reviewed.values() if v.get("decision") == "promoted")
    rejected = sum(1 for v in reviewed.values() if v.get("decision") == "rejected")
    print(json.dumps({
        "reviewed": len(reviewed), "promoted": promoted, "rejected": rejected,
        "triage_cached": len(state.get("triage", {})),
        "state_file": _state_path(),
        "candidates_file": _candidates_path(),
    }, indent=2))
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Promozione fatti progetto -> core.")
    g = parser.add_mutually_exclusive_group(required=True)
    g.add_argument("--scan", action="store_true")
    g.add_argument("--triage", action="store_true")
    g.add_argument("--move", metavar="DOC_ID")
    g.add_argument("--reject", metavar="DOC_ID")
    g.add_argument("--status", action="store_true")
    parser.add_argument("--bank", action="append", default=[],
                        help="Bank progetto (ripetibile; default: tutti tranne il core). "
                             "Obbligatorio con --move/--reject.")
    parser.add_argument("--force", action="store_true",
                        help="--triage: re-interroga l'LLM anche sui verdetti cachati")
    parser.add_argument("--timeout", type=int, default=20)
    args = parser.parse_args()

    if (args.move or args.reject) and len(args.bank) != 1:
        parser.error("--move/--reject richiedono esattamente un --bank")

    cfg = load_config()
    try:
        if args.scan:
            return cmd_scan(cfg, args)
        if args.triage:
            return cmd_triage(cfg, args)
        if args.move:
            return cmd_move(cfg, args)
        if args.reject:
            return cmd_reject(cfg, args)
        return cmd_status(cfg, args)
    except urllib.error.URLError as e:
        print(f"[promote] ERRORE: server Hindsight non raggiungibile ({e})",
              file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
