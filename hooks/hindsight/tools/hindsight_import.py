#!/usr/bin/env python
"""Re-importa in un bank Hindsight i documenti esportati da hindsight_export.py.

Ogni item viene re-inviato a POST /memories (retain): il server RI-ESTRAE i fatti
(LLM) e soprattutto RI-GENERA gli embedding con il modello di embedding ATTIVO in
quel momento. E' il passo che concretizza una migrazione di embedding model:
  1. hindsight_export.py            (a server acceso, modello vecchio)
  2. wipe del bank                  (clear_memories / delete+recreate)
  3. cambio modello + restart       (es. gemini-embedding-2, 1536 dim)
  4. hindsight_import.py            (ri-embedda tutto col modello nuovo)

Idempotente: ogni item porta il suo `document_id` → il server fa upsert, quindi
ri-eseguire l'import non duplica.

Uso:
  python hindsight_import.py                      # usa l'export piu' recente in ./exports/
  python hindsight_import.py --in C:/path/dump.json
  python hindsight_import.py --dry-run            # valida il file, non invia nulla
  python hindsight_import.py --async              # accoda lato server (non attende l'estrazione)

NB Windows: path dei flag in stile Windows (C:/...), non MSYS (/c/...).
"""

from __future__ import annotations

import argparse
import glob
import json
import os
import sys
import time
import urllib.error
import urllib.request

sys.path.insert(
    0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "lib")
)
from hindsight_config import load_config


def latest_export() -> str | None:
    here = os.path.dirname(os.path.abspath(__file__))
    files = sorted(glob.glob(os.path.join(here, "exports", "hindsight-export-*.json")))
    return files[-1] if files else None


def to_retain_item(item: dict) -> dict:
    """Costruisce il payload item per POST /memories, omettendo i campi None
    (il server li tratta come 'non forniti', evitando di sporcare l'estrazione)."""
    fields = {
        "content": item.get("content"),
        "context": item.get("context"),
        "tags": item.get("tags") or [],
        "timestamp": item.get("timestamp"),
        "metadata": item.get("metadata") or {},
        "document_id": item.get("document_id"),
    }
    return {k: v for k, v in fields.items() if v is not None}


def retain(api_url: str, item: dict, async_mode: bool, timeout: int) -> tuple[int, str]:
    body = {"items": [to_retain_item(item)], "async": async_mode}
    req = urllib.request.Request(
        f"{api_url}/memories",
        data=json.dumps(body).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=timeout) as res:
        return res.status, res.read().decode("utf-8", errors="replace")


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Re-importa documenti esportati in un bank Hindsight (re-retain)."
    )
    parser.add_argument(
        "--in",
        dest="infile",
        default=None,
        help="File JSON di export (default: il piu' recente in ./exports/)",
    )
    parser.add_argument(
        "--api-url",
        default=None,
        help="URL del bank (default: api_url da hindsight.config.json)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Valida il file e mostra cosa farebbe, senza inviare",
    )
    parser.add_argument(
        "--async",
        dest="async_mode",
        action="store_true",
        help="Retain asincrono lato server (non attende l'estrazione)",
    )
    parser.add_argument(
        "--timeout",
        type=int,
        default=90,
        help="Timeout HTTP per retain sincrono (default: 90s)",
    )
    parser.add_argument(
        "--sleep",
        type=float,
        default=0.0,
        help="Pausa in secondi tra un retain e l'altro (rate-limit)",
    )
    args = parser.parse_args()

    infile = args.infile or latest_export()
    if not infile or not os.path.exists(infile):
        print(
            f"[import] ERRORE: file di export non trovato ({infile}). Esegui prima hindsight_export.py.",
            file=sys.stderr,
        )
        return 1

    with open(infile, encoding="utf-8") as f:
        data = json.load(f)
    items = data.get("items") or []

    cfg = load_config()
    api_url = (args.api_url or cfg["api_url"]).rstrip("/")

    print(f"[import] sorgente : {infile}")
    print(
        f"[import] esportato: {data.get('exported_at')}  (da {data.get('source_api_url')})"
    )
    print(f"[import] bank dest: {api_url}")
    print(
        f"[import] documenti: {len(items)}  | modalita': {'ASYNC' if args.async_mode else 'SYNC'}{'  [DRY-RUN]' if args.dry_run else ''}"
    )

    if args.dry_run:
        for i, it in enumerate(items, 1):
            ri = to_retain_item(it)
            print(
                f"[dry-run]  ({i}/{len(items)}) doc={ri.get('document_id')}  text={len(ri.get('content', ''))}  tags={len(ri.get('tags', []))}"
            )
        print("[import] DRY-RUN: nessuna scrittura effettuata.")
        return 0

    ok, fail = 0, 0
    for i, it in enumerate(items, 1):
        doc_id = it.get("document_id")
        try:
            status, body = retain(api_url, it, args.async_mode, args.timeout)
            ok += 1
            print(f"[import]  ({i}/{len(items)}) OK {status}  doc={doc_id}")
        except urllib.error.HTTPError as e:
            fail += 1
            print(
                f"[import]  ({i}/{len(items)}) FAIL {e.code}  doc={doc_id}  {e.read().decode('utf-8', 'replace')[:200]}",
                file=sys.stderr,
            )
        except urllib.error.URLError as e:
            fail += 1
            print(
                f"[import]  ({i}/{len(items)}) FAIL  doc={doc_id}  {e}", file=sys.stderr
            )
        if args.sleep:
            time.sleep(args.sleep)

    print(f"[import] FINE: {ok} ok, {fail} falliti su {len(items)}")
    if args.async_mode and ok:
        print(
            "[import] NB: retain ASYNC accodati — l'estrazione/embedding gira in background sul server."
        )
    return 0 if fail == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
