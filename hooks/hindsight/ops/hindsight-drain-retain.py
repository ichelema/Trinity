"""Attende che i retain in volo siano stati estratti dal server, prima dello stop.

POST /memories e' async:true: torna appena il task e' in coda, mentre l'estrazione
LLM dei fatti prosegue server-side. Chi spegne il server prima che l'operation
raggiunga uno stato terminale perde quella memoria SENZA nessun errore — l'operation
resta 'pending' per sempre e nemmeno hindsight-failcheck.sh la vede (cerca
status=failed). Misurato sulle 100 operation piu' recenti di trinity-project: 89%
dei retain impiega piu' di 7s (mediana 32s, p90 47s), cioe' il vecchio `sleep 7`
fisso nel vecchio hook di shutdown perdeva quasi sempre il retain finale.

Exit 0: nessun retain in volo (o bank gia' irraggiungibile). Exit 1: budget scaduto.
In entrambi i casi il chiamante spegne — il server non puo' restare su per sempre.
"""

from __future__ import annotations

import json
import os
import sys
import time
import urllib.request
from datetime import datetime, timezone

sys.path.insert(
    0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "lib")
)
from hindsight_config import bank_url, cache_dir, load_config, retain_bank_url

# Budget generoso rispetto al p90 misurato (47s) ma finito: un task incastrato non
# deve tenere in piedi server (~1.5GB) e Postgres all'infinito.
BUDGET_S = 180
POLL_S = 2
IN_FLIGHT = ("pending", "processing")  # gli stati non terminali dell'API
# Solo dato utente: consolidation/refresh_mental_model/graph_maintenance si
# auto-recuperano al ciclo successivo, un retain ucciso invece e' perso.
RETAIN_TASKS = {"retain", "batch_retain"}


def in_flight_retains(base: str, timeout: float = 3) -> int | None:
    """Quanti retain non terminati ci sono sul bank. None se il bank non risponde."""
    n = 0
    for status in IN_FLIGHT:
        try:
            req = urllib.request.Request(
                f"{base}/operations?status={status}&limit=100", method="GET"
            )
            with urllib.request.urlopen(req, timeout=timeout) as res:
                data = json.loads(res.read().decode("utf-8", errors="replace"))
        except Exception:
            return None
        n += sum(
            1
            for op in data.get("operations") or []
            if op.get("task_type") in RETAIN_TASKS
        )
    return n


def server_bank_urls(cfg: dict, timeout: float = 3) -> list[str] | None:
    """URL di TUTTE le bank del server (GET /banks), None se la lista non e'
    disponibile (server giu', api_base assente). Un retain in volo puo' vivere su
    qualunque bank, non solo su quella del cwd di CHI spegne: con due sessioni su
    progetti DIVERSI chiuse quasi insieme, il drain lo esegue l'ultima — che senza
    la lista vedrebbe solo la propria bank e ucciderebbe il retain dell'altra."""
    base = (cfg.get("bank") or {}).get("api_base", "").rstrip("/")
    if not base:
        return None
    try:
        req = urllib.request.Request(f"{base}/banks", method="GET")
        with urllib.request.urlopen(req, timeout=timeout) as res:
            data = json.loads(res.read().decode("utf-8", errors="replace"))
    except Exception:
        return None
    names = [b.get("bank_id") or b.get("name") for b in data.get("banks") or []]
    urls = [bank_url(cfg, n) for n in names if n]
    return urls or None


def report_stuck(n: int) -> None:
    """Traccia durevole del timeout: il worker gira detached con output su /dev/null,
    quindi stderr qui non lo legge nessuno. Stesso canale dei fallimenti locali di
    hindsight-retain.sh — hindsight-failcheck.sh lo raccoglie al prossimo prompt."""
    try:
        with open(
            os.path.join(cache_dir(), "hs-retain-failed.log"), "a", encoding="utf-8"
        ) as f:
            f.write(
                f"{datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')}\t"
                f"estrazione non completata: {n} retain ancora in volo dopo {BUDGET_S}s, "
                f"server fermato comunque\n"
            )
    except Exception:
        pass


def main() -> int:
    cfg = load_config()
    try:
        hook = json.loads(os.environ.get("HOOK_INPUT", ""))
    except Exception:
        hook = {}
    # Tutte le bank del server; fallback alla sola bank della sessione se la
    # lista non e' disponibile (comportamento precedente).
    bases = server_bank_urls(cfg) or [retain_bank_url(cfg, hook.get("cwd") or None)]

    deadline = time.monotonic() + BUDGET_S
    while True:
        total = 0
        alive = False
        for base in bases:
            n = in_flight_retains(base)
            if n is None:
                continue  # bank giu': nulla da attendere qui
            alive = True
            total += n
        if not alive:
            return 0  # server gia' giu': non c'e' nulla da attendere
        if total == 0:
            return 0
        if time.monotonic() >= deadline:
            report_stuck(total)
            return 1
        time.sleep(POLL_S)


if __name__ == "__main__":
    sys.exit(main())
