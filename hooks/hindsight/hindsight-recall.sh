#!/usr/bin/env bash
# UserPromptSubmit hook: recupera memorie rilevanti da Hindsight via REST e
# filtra semanticamente i risultati prima di iniettarli.
set -uo pipefail

HOOKS_DIR="${BASH_SOURCE[0]%/*}"; [ "$HOOKS_DIR" = "${BASH_SOURCE[0]}" ] && HOOKS_DIR="."
case "$HOOKS_DIR" in
[A-Za-z]:/*) _hs_drive="${HOOKS_DIR%%:*}"; HOOKS_DIR="/${_hs_drive,,}${HOOKS_DIR#?:}" ;;
esac
IFS= read -r -d '' HOOK_INPUT || true
export HOOK_INPUT HOOKS_DIR

. "$HOOKS_DIR/lib/hs-python.sh"

PYTHONUTF8=1 "$HS_PY" <<'PY' 2>"$HS_CACHE_DIR/hs-recall-stderr.log"
import json
import os
import sys
import time
import urllib.request
from datetime import datetime, timezone

sys.path.insert(0, os.path.join(os.environ["HOOKS_DIR"], "lib"))
from hindsight_config import cache_dir as _hs_state_dir
from hindsight_config import load_config, recall_bank_urls
from hindsight_debug import debug_log
from hindsight_multibank import multi_recall
from hindsight_recall_filter import (
    consent_decision,
    consume_pending,
    discard_pending_if_present,
    read_with_deadline,
    route_results,
    save_pending,
)
from hindsight_recall_lib import build_recall_payload
from hindsight_retain_gate import handle_retain_consent

cfg = load_config()

try:
    hook = json.loads(os.environ["HOOK_INPUT"])
except Exception as exc:
    debug_log(
        cfg,
        "recall_error",
        reason="bad_hook_input",
        error=f"{type(exc).__name__}: {exc}",
        input_len=len(os.environ.get("HOOK_INPUT", "")),
    )
    sys.exit(0)

original_prompt = (hook.get("prompt") or "").strip()
session_id = str(hook.get("session_id") or "")
cwd = str(hook.get("cwd") or "")
pending_dir = cfg["recall_pending_dir"]
pending_ttl = float(cfg["recall_pending_ttl"])

# Consenso del RETAIN pending (gate "uncertain", ICH-67) — PRIMA di tutto il
# resto, incluso il gate recall_enabled: la domanda del gate retain e' sempre
# la piu' recente (posta alla fine del turno precedente), quindi un si'/no
# secco appartiene a lei, e va onorata anche nei progetti col recall spento.
retain_outcome = handle_retain_consent(original_prompt, session_id, cwd)
if retain_outcome:
    debug_log(
        cfg,
        "retain_pending",
        action=retain_outcome.get("action"),
        reason=retain_outcome.get("reason"),
        status=retain_outcome.get("status"),
        error=retain_outcome.get("error"),
        preview=(retain_outcome.get("preview") or "")[:300],
    )
    if retain_outcome["action"] == "saved":
        # Lo stesso "si'" non deve autorizzare anche le memorie medium rimaste
        # in pending dal recall: la domanda a cui risponde e' quella del retain.
        discard_pending_if_present(pending_dir, session_id, cwd, pending_ttl)
        preview = retain_outcome.get("preview") or ""
        print(json.dumps({
            "systemMessage": f"Hindsight: memoria salvata — {preview}",
            "hookSpecificOutput": {
                "hookEventName": "UserPromptSubmit",
                "additionalContext": (
                    "## Hindsight retain\n\nLa memoria in attesa di conferma è stata "
                    "salvata nel bank. Non serve alcun retain manuale."
                ),
            },
        }, ensure_ascii=False))
        sys.exit(0)
    if retain_outcome["action"] == "error":
        print(json.dumps({
            "systemMessage": (
                "Hindsight: salvataggio della memoria in attesa NON riuscito — "
                + str(retain_outcome.get("error") or "")
            ),
        }, ensure_ascii=False))
        sys.exit(0)
    # "discarded" (no / prompt nuovo): si prosegue col flusso normale.

if not cfg.get("recall_enabled", True):
    debug_log(cfg, "recall_skip", reason="disabled")
    sys.exit(0)


def emit_context(memories, route_counts, model, latency_ms=0.0, error=None):
    lines = []
    for memory in memories:
        text = (memory.get("text") or "").strip()
        if not text:
            continue
        kind = memory.get("type", "?")
        route = memory.get("route", "unknown")
        entities = ", ".join(memory.get("entities") or [])
        if cfg.get("recall_debug_in_context"):
            lines.append(f"- [{route}] ({kind}) {text}" + (f"  [entities: {entities}]" if entities else ""))
        else:
            lines.append(f"- ({kind}) {text}" + (f"  [entities: {entities}]" if entities else ""))
    if not lines:
        return

    if cfg.get("recall_debug_in_context"):
        counts = ", ".join(f"{key}={value}" for key, value in route_counts.items())
        context = (
            "## Hindsight recall debug\n\n"
            f"Model: {model}\n"
            f"Routing: {counts}\n"
            f"Classifier latency: {latency_ms:.1f} ms"
            + (f"\nClassifier error: {error}" if error else "")
            + "\n\nMemorie effettivamente iniettate:\n"
            + "\n".join(lines)
            + "\n\nUse as consultative context. Verify mutable facts against the repo."
        )
    else:
        context = (
            "## Hindsight persistent memory (advisory, source: fresh)\n\n"
            + "\n".join(lines)
            + "\n\nUse as consultative context. Verify mutable facts against the repo."
        )
    output = {
        "hookSpecificOutput": {
            "hookEventName": "UserPromptSubmit",
            "additionalContext": context,
        }
    }
    # additionalContext entra nel modello ma non viene mostrato nel terminale.
    # systemMessage rende visibile lo stesso blocco solo nella modalità debug.
    if cfg.get("recall_debug_in_context"):
        output["systemMessage"] = context
    print(json.dumps(output, ensure_ascii=False))


# Il pending viene gestito prima del gate sui prompt corti: "sì" deve poter
# autorizzare memorie conservate dal turno precedente. La decisione e il consumo
# avvengono sotto lo stesso lock per evitare che due submit concorrenti iniettino
# due volte lo stesso pending; anche verifica+scarto è una singola operazione atomica.
consent = consent_decision(original_prompt)
if consent == "positive":
    consumed = consume_pending(pending_dir, session_id, cwd, pending_ttl) or []
    if consumed:
        injected = [{**memory, "route": "pending_medium"} for memory in consumed]
        debug_log(cfg, "recall_pending", action="consumed", n_results=len(injected))
        emit_context(
            injected,
            {"pending_medium": len(injected)},
            cfg["recall_result_filter_model"],
        )
        sys.exit(0)
elif discard_pending_if_present(pending_dir, session_id, cwd, pending_ttl):
    debug_log(
        cfg,
        "recall_pending",
        action="discarded",
        reason="negative" if consent == "negative" else "new_prompt",
    )

if len(original_prompt) < cfg["recall_min_prompt_chars"]:
    debug_log(cfg, "recall_skip", reason="prompt_too_short", prompt_len=len(original_prompt))
    sys.exit(0)

prompt = original_prompt
max_chars = cfg["recall_max_prompt_chars"]
if len(prompt) > max_chars:
    debug_log(cfg, "recall_truncate", orig_len=len(prompt), max_chars=max_chars)
    prompt = prompt[:max_chars]

bank_urls = recall_bank_urls(cfg, cwd or None)
payload = build_recall_payload(prompt, cfg, datetime.now(timezone.utc).isoformat())
merge_meta = {}
if len(bank_urls) == 1:
    request = urllib.request.Request(
        bank_urls[0] + "/memories/recall",
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        recall_timeout = float(cfg["recall_timeout"])
        deadline = time.monotonic() + recall_timeout
        with urllib.request.urlopen(request, timeout=recall_timeout) as response:
            data = json.loads(
                read_with_deadline(response, deadline).decode("utf-8", errors="replace")
            )
    except Exception as exc:
        debug_log(cfg, "recall_error", query=prompt, error=str(exc)[:200])
        sys.exit(0)
else:
    merged, merge_meta = multi_recall(prompt, cfg, bank_urls, payload)
    data = {"results": merged}

results = data.get("results") or []

# Sentinella del degrado reranker: il failover RRF non emette scores.reranker.
degraded = []
if merge_meta.get("rerank_error"):
    degraded.append(f"rerank globale multi-bank fallito ({merge_meta['rerank_error']})")
if results and not any(
    isinstance(result.get("scores"), dict)
    and result["scores"].get("reranker") is not None
    for result in results
):
    degraded.append("risultati senza scores.reranker: reranker del server in fallback RRF")
if degraded:
    try:
        log_path = os.path.join(_hs_state_dir(), "hs-reranker-degraded.log")
        # Con reranker in degrado persistente si appende a OGNI prompt: stesso
        # cap di rotazione di hindsight_debug (5MB -> .1).
        try:
            if os.path.getsize(log_path) > 5_000_000:
                os.replace(log_path, log_path + ".1")
        except OSError:
            pass
        timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        with open(log_path, "a", encoding="utf-8") as handle:
            for message in degraded:
                handle.write(f"{timestamp}\t{message}\n")
    except Exception:
        pass

max_results = (
    int(cfg.get("recall_max_results_multibank") or cfg["recall_max_results"])
    if len(bank_urls) > 1
    else int(cfg["recall_max_results"])
)
results = results[:max_results]

if cfg.get("recall_result_filter_enabled", True) and results:
    routed = route_results(
        prompt,
        results,
        cfg["recall_result_filter_model"],
        float(cfg["recall_result_filter_threshold"]),
        float(cfg["recall_result_filter_timeout"]),
    )
else:
    routed = {
        "automatic": [{**result, "route": "filter_disabled", "confidence": "high"} for result in results],
        "optional": [],
        "discarded": [],
        "latency_ms": 0.0,
        "classifier_called": False,
        "model": cfg["recall_result_filter_model"],
    }

counts = {
    "bypass": sum(item.get("route") == "bypass" for item in routed["automatic"]),
    "high": sum(item.get("route") == "classifier_high" for item in routed["automatic"]),
    "medium": len(routed["optional"]),
    "low": len(routed["discarded"]),
    "fail_open": sum(item.get("route") == "fail_open" for item in routed["automatic"]),
}
debug_log(
    cfg,
    "recall",
    query=prompt,
    source="fresh",
    banks=[url.rsplit("/", 1)[-1] for url in bank_urls],
    **{
        key: value
        for key, value in merge_meta.items()
        if key in ("merge", "rerank_error", "min_score", "min_score_filtered", "per_bank_counts")
        and value not in (None, "")
    },
    n_results=len(results),
    routing=counts,
    classifier_model=routed["model"],
    classifier_latency_ms=routed["latency_ms"],
    classifier_error=routed.get("error"),
    injected=[
        {
            "route": item.get("route"),
            "type": item.get("type", "?"),
            "text": (item.get("text") or "").strip()[:300],
        }
        for item in routed["automatic"]
    ],
)

if routed["automatic"]:
    # Decisione esplicita: se esiste almeno un high, i medium non vengono proposti.
    emit_context(
        routed["automatic"],
        counts,
        routed["model"],
        routed["latency_ms"],
        routed.get("error"),
    )
    sys.exit(0)

if routed["optional"]:
    if save_pending(pending_dir, session_id, cwd, routed["optional"]):
        debug_log(cfg, "recall_pending", action="saved", n_results=len(routed["optional"]))
        instruction = (
            "## Hindsight: consenso richiesto\n\n"
            "Non usare ancora alcuna memoria. Chiedi esattamente all’utente: "
            "“Ho delle memorie che potrebbero essere utili, le vuoi usare?”"
        )
        print(json.dumps({
            "hookSpecificOutput": {
                "hookEventName": "UserPromptSubmit",
                "additionalContext": instruction,
            }
        }, ensure_ascii=False))
    else:
        # Senza session_id o se lo stato non è scrivibile non si può ottenere un
        # consenso sicuro: fail-open per non perdere una memoria potenzialmente utile.
        fallback = [
            {**memory, "route": "fail_open", "confidence": "high"}
            for memory in routed["optional"]
        ]
        emit_context(fallback, {**counts, "fail_open": len(fallback)}, routed["model"])
PY
