#!/usr/bin/env python
"""Esporta tutti i documenti sorgente di un bank Hindsight in un file JSON.

Scopo: backup e migrazione del bank (es. cambio del modello di embedding, che
obbliga a ri-embeddare tutto). L'export cattura il CONTENUTO GREZZO
(`original_text`) piu' i parametri di retain originali (context, event_date,
metadata, tags) di ogni documento, in un formato gia' pronto per il re-retain
via hindsight_import.py.

Punto chiave: il testo sorgente e' INDIPENDENTE dal modello di embedding. Questo
export resta quindi valido attraverso qualsiasi cambio di modello
(gemini-embedding-001 -> gemini-embedding-2, locale -> remoto, ecc.): si ri-embedda
al momento dell'import con il modello allora attivo.

Uso:
  python hindsight_export.py                       # api_url da hindsight.config.json, out auto
  python hindsight_export.py --out C:/path/dump.json
  python hindsight_export.py --api-url http://localhost:8888/v1/default/banks/trinity-project

NB Windows: i path nei flag vanno in stile Windows (C:/...), non MSYS (/c/...).
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

# Riusa il loader di config condiviso (in ../lib) per l'api_url di default.
sys.path.insert(
    0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "lib")
)
from hindsight_config import load_config


def _get(url: str, timeout: int) -> dict:
    """GET JSON con gestione errori esplicita (niente silenziamento)."""
    req = urllib.request.Request(url, headers={"Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as res:
        return json.loads(res.read().decode("utf-8", errors="replace"))


def list_all_documents(api_url: str, page: int, timeout: int) -> list[dict]:
    """Pagina /documents finche' non li ha raccolti tutti (usa `total`)."""
    docs: list[dict] = []
    offset = 0
    while True:
        data = _get(f"{api_url}/documents?limit={page}&offset={offset}", timeout)
        items = data.get("items") or []
        docs.extend(items)
        total = int(data.get("total", len(docs)))
        offset += len(items)
        if not items or offset >= total:
            break
    return docs


def fetch_document(api_url: str, doc_id: str, timeout: int) -> dict:
    """GET /documents/{id} -> include `original_text` (il testo sorgente pieno)."""
    safe_id = urllib.parse.quote(doc_id, safe="")
    return _get(f"{api_url}/documents/{safe_id}", timeout)


def build_item(doc: dict) -> dict:
    """Mappa un documento nel formato item del retain (POST /memories).

    Conserva document_id per l'upsert idempotente lato server: re-importare lo
    stesso bank due volte non duplica.
    """
    rp = doc.get("retain_params") or {}
    return {
        "document_id": doc.get("id"),
        "content": doc.get("original_text") or "",
        "context": rp.get("context"),
        "timestamp": rp.get("event_date"),
        "metadata": rp.get("metadata") or doc.get("document_metadata") or {},
        "tags": doc.get("tags") or [],
    }


def default_out_path() -> str:
    here = os.path.dirname(os.path.abspath(__file__))
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    # tools/ → la cartella export canonica e' ../data/exports
    return os.path.join(here, "..", "data", "exports", f"hindsight-export-{stamp}.json")


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Esporta i documenti di un bank Hindsight in JSON."
    )
    parser.add_argument(
        "--api-url",
        default=None,
        help="URL del bank (default: api_url da hindsight.config.json)",
    )
    parser.add_argument(
        "--out",
        default=None,
        help="File JSON di output (default: ../data/exports/hindsight-export-<UTC>.json)",
    )
    parser.add_argument(
        "--page",
        type=int,
        default=100,
        help="Dimensione pagina per /documents (default: 100)",
    )
    parser.add_argument(
        "--timeout", type=int, default=20, help="Timeout HTTP in secondi (default: 20)"
    )
    args = parser.parse_args()

    cfg = load_config()
    api_url = (args.api_url or cfg["api_url"]).rstrip("/")
    out_path = args.out or default_out_path()

    print(f"[export] bank: {api_url}")
    try:
        summaries = list_all_documents(api_url, args.page, args.timeout)
    except urllib.error.URLError as e:
        print(
            f"[export] ERRORE: impossibile contattare il bank ({e}). Il server e' acceso?",
            file=sys.stderr,
        )
        return 1
    print(f"[export] documenti trovati: {len(summaries)}")

    items: list[dict] = []
    skipped: list[str] = []
    for i, summ in enumerate(summaries, 1):
        doc_id = summ.get("id")
        try:
            full = fetch_document(api_url, doc_id, args.timeout)
        except urllib.error.URLError as e:
            print(
                f"[export] WARN: doc {doc_id} non recuperato ({e}) — salto",
                file=sys.stderr,
            )
            skipped.append(doc_id)
            continue
        item = build_item(full)
        if not (item["content"] or "").strip():
            skipped.append(doc_id)
            continue
        items.append(item)
        print(
            f"[export]  ({i}/{len(summaries)}) {doc_id}  text={len(item['content'])}  tags={len(item['tags'])}"
        )

    payload = {
        "exported_at": datetime.now(timezone.utc).isoformat(),
        "source_api_url": api_url,
        "document_count": len(items),
        "skipped_ids": skipped,
        "items": items,
    }

    os.makedirs(os.path.dirname(out_path) or ".", exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)

    print(f"[export] OK: {len(items)} documenti scritti in {out_path}")
    if skipped:
        print(f"[export] saltati {len(skipped)} documenti senza testo: {skipped}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
