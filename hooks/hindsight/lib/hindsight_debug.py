"""Logging di debug opzionale per gli hook Hindsight.

Quando abilitato in config (debug_log_enabled: true) scrive UN evento per riga
(JSONL) su un file di log, per ispezionare COSA viene recuperato dalla memoria
(recall) e COSA viene salvato (retain). Serve a verificare a occhio che il
sistema funzioni: query, cache hit/miss, memorie restituite, contenuto ritenuto,
risposta del server, skip e errori.

Costo ~zero quando spento: debug_log() esce subito se il flag e' false.
Best-effort: non solleva MAI eccezioni, per non rompere gli hook che lo chiamano.

Formato JSONL: leggibile a occhio e processabile con Nushell, es.
  nu -c "open 'D:/AI/Claude/Trinity/logs/hindsight-debug.log' | lines | each { from json } | where event == 'recall'"
"""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone

# Cap di rotazione: oltre questa soglia il log corrente viene ruotato a .1.
_MAX_BYTES = 5_000_000


def debug_enabled(cfg: dict) -> bool:
    return bool(cfg.get("debug_log_enabled"))


def _log_path(cfg: dict) -> str:
    """Path del file di log. Se debug_log_file e' valorizzato in config lo usa,
    altrimenti default portabile: <plugin_root>/logs/hindsight-debug.log,
    calcolato relativo a questo modulo (.../hooks/hindsight/lib/)."""
    p = (cfg.get("debug_log_file") or "").strip()
    if p:
        return p
    here = os.path.dirname(os.path.abspath(__file__))
    # here = hooks/hindsight/lib → 3 livelli su = plugin root
    root = os.path.abspath(os.path.join(here, "..", "..", ".."))
    return os.path.join(root, "logs", "hindsight-debug.log")


def debug_log(cfg: dict, event: str, **fields) -> None:
    """Appende un evento JSONL al file di log se il debug e' attivo. Best-effort:
    qualsiasi errore (path, permessi, encoding) viene ingoiato silenziosamente."""
    if not debug_enabled(cfg):
        return
    try:
        rec = {"ts": datetime.now(timezone.utc).isoformat(), "event": event}
        rec.update(fields)
        line = json.dumps(rec, ensure_ascii=False)
        path = _log_path(cfg)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        try:
            if os.path.exists(path) and os.path.getsize(path) > _MAX_BYTES:
                os.replace(path, path + ".1")
        except OSError:
            pass
        with open(path, "a", encoding="utf-8") as f:
            f.write(line + "\n")
    except Exception:
        pass
