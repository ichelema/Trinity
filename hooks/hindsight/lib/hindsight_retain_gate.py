"""Gate semantico pre-retain (ICH-67): decide se la finestra Stop va persistita.

Stesso pattern di hindsight_recall_filter.py: una sola chiamata OpenAI con
response_format json_schema strict e validazione completa della risposta.
Attivo ogni volta che retain_enabled e' true; esiti (li applica il worker):
  retain     -> POST diretta e silenziosa nel bank
  skip       -> nessun salvataggio
  uncertain  -> POST messa in pending + domanda all'utente; il consenso al
                prompt successivo la esegue (handle_retain_consent, stessa
                meccanica dei medium del recall ICH-66)
Un errore TECNICO del gate e' fail-open lato worker (salva come prima del
gate): con il gate obbligatorio, il fail-closed perderebbe ogni retain a
server LLM giu'. L'errore resta visibile in GateResult.error e nel debug log.
"""

from __future__ import annotations

import json
import os
import re
import urllib.request
from dataclasses import dataclass, field

# Doppio percorso: nome top-level quando lib/ e' su sys.path (worker, bench);
# relativo quando il modulo viene importato come package (test: lib.<modulo>).
try:
    from hindsight_config import cache_dir
    from hindsight_multibank import fetch_bank_results
    from hindsight_recall_filter import (
        ApiCall,
        _normalize_prompt,
        api_json,
        consume_pending,
        discard_pending_if_present,
        save_pending,
    )
except ImportError:
    from .hindsight_config import cache_dir
    from .hindsight_multibank import fetch_bank_results
    from .hindsight_recall_filter import (
        ApiCall,
        _normalize_prompt,
        api_json,
        consume_pending,
        discard_pending_if_present,
        save_pending,
    )

GATE_ACTIONS = {"retain", "skip", "uncertain"}

GATE_REASONS = {
    # retain
    "durable_decision",
    "root_cause_or_workaround",
    "environment_constraint",
    "convention_or_preference",
    "discarded_approach",
    # skip
    "trivial_or_ephemeral",
    "repo_recoverable",
    "intermediate_attempt",
    "duplicate",
    "no_durable_knowledge",
    # uncertain
    "borderline",
}

GATE_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "action": {"type": "string", "enum": sorted(GATE_ACTIONS)},
        "reason": {"type": "string", "enum": sorted(GATE_REASONS)},
        "preview": {"type": "string"},
        "duplicate_of": {"type": "array", "items": {"type": "integer"}},
        "context": {"type": "string"},
    },
    "required": ["action", "reason", "preview", "duplicate_of", "context"],
}

# Derivato dal draft di ICH-67. Il preview e' nella lingua della conversazione:
# e' il testo che Claude mostra all'utente e ri-usa per il retain MCP.
GATE_PROMPT = """You decide whether a Claude Code session window deserves to be persisted to Hindsight long-term memory.

Choose action "retain" ONLY if the window contains durable, verified knowledge likely useful in future sessions: decisions or conventions with their rationale, domain rules, non-obvious constraints, root causes and workarounds, relevant discarded approaches, environment quirks.

Choose action "skip" for: temporary or trivial information, anything easily recoverable from the repository or git history, ordinary command output, intermediate attempts, work still in progress with no conclusion, or content already covered by one of the existing memories provided.

Ask yourself: "Could this information avoid work, mistakes or repeated analysis in the future?"

Rules:
1. action "retain": set preview to ONE short self-contained sentence, in the same language as the conversation, stating WHAT gets stored and WHY it matters (favour the why over the what).
2. action "skip": set preview to "".
3. action "uncertain": only when genuinely borderline; set preview to the short summary you would store.
4. duplicate_of: indices of the provided existing memories that already cover the same facts. If the window adds nothing beyond them, use action "skip" with reason "duplicate".
5. Judge the window as a whole: one durable fact is enough to retain.
6. context: ONE short line, in the same language as the conversation, describing the technical domain the window is about — subject and project, not an activity and not a bare category (e.g. "architettura del recall automatico Hindsight nel plugin Trinity", NOT "tooling"). Fill it for every action; empty string only if the window has no technical subject."""


@dataclass
class GateResult:
    action: str
    reason: str
    preview: str = ""
    # Riga descrittiva del dominio della finestra, prodotta dal gate: diventa il
    # campo `context` del retain (il worker ricade su resolve_context se vuota).
    context: str = ""
    duplicate_of: list[int] = field(default_factory=list)
    candidates: list[dict] = field(default_factory=list)
    latency_ms: float = 0.0
    error: str | None = None


def dedup_query(summary: dict) -> str:
    """Query per il recall anti-duplicato: l'ultimo testo assistant della
    finestra (e' il riassunto migliore di cosa e' stato concluso). Fallback
    all'ultimo prompt user; stringa vuota se la finestra non ha testo."""
    turns = summary.get("turns") or []
    for role, text in reversed(turns):
        if role == "assistant" and text.strip():
            return text
    last_user = summary.get("last_user_prompt") or ""
    for role, text in reversed(turns):
        if role == "user" and text.strip():
            return text
    return last_user


def fetch_duplicate_candidates(
    bank_urls: list[str], query: str, timeout: float, max_candidates: int = 3
) -> list[dict]:
    """Fino a max_candidates memorie esistenti vicine alla finestra, dai bank
    di lettura. Best-effort: bank giu' o query vuota => lista vuota (il gate
    valuta senza controllo duplicati). Il tetto alla query evita il 400
    "Query too long" del query-embedder (vedi recall_max_prompt_chars)."""
    if not query:
        return []
    payload = {"query": query[:1500], "limit": max_candidates}
    seen: set[str] = set()
    out: list[dict] = []
    for url in bank_urls:
        for r in fetch_bank_results(url, payload, timeout):
            key = " ".join((r.get("text") or "").lower().split())
            if key and key not in seen:
                seen.add(key)
                out.append(r)
                if len(out) >= max_candidates:
                    return out
    return out


def gate_input(content: str, candidates: list[dict]) -> str:
    lines = ["## Session window to evaluate", content[:8000], ""]
    if candidates:
        lines.append("## Existing memories (duplicate check)")
        for index, r in enumerate(candidates):
            lines.append(f"[{index}] {(r.get('text') or '')[:1500]}")
    else:
        lines.append("## Existing memories (duplicate check)\n(none)")
    return "\n".join(lines)


def evaluate_retain(
    content: str,
    summary: dict,
    bank_urls: list[str],
    cfg: dict,
    api_call: ApiCall = api_json,
) -> GateResult:
    """Valuta la finestra. Fail-closed: QUALSIASI errore (key assente, timeout,
    HTTP, JSON, schema violato, indici duplicato fuori range) => "skip" con
    error valorizzato — in enforce non si salva niente, in shadow si logga."""
    timeout = float(cfg.get("retain_gate_timeout", 15))
    model = str(cfg.get("retain_gate_model", "gpt-5.6-luna"))
    candidates = fetch_duplicate_candidates(bank_urls, dedup_query(summary), timeout)
    try:
        data, latency = api_call(
            model,
            GATE_PROMPT,
            gate_input(content, candidates),
            "retain_gate_decision",
            GATE_SCHEMA,
            timeout,
        )
        action = data.get("action")
        reason = data.get("reason")
        preview = data.get("preview")
        duplicate_of = data.get("duplicate_of")
        context = data.get("context")
        if action not in GATE_ACTIONS:
            raise ValueError("action non valida")
        if reason not in GATE_REASONS:
            raise ValueError("reason non valida")
        if not isinstance(preview, str):
            raise ValueError("preview non valida")
        if not isinstance(context, str):
            raise ValueError("context non valido")
        if action == "retain" and not preview.strip():
            raise ValueError("preview vuota su action retain")
        if not isinstance(duplicate_of, list) or any(
            isinstance(i, bool) or not isinstance(i, int) for i in duplicate_of
        ):
            raise ValueError("duplicate_of non valido")
        if len(set(duplicate_of)) != len(duplicate_of) or any(
            not 0 <= i < len(candidates) for i in duplicate_of
        ):
            raise ValueError("indici duplicato fuori range o duplicati")
        return GateResult(
            action=action,
            reason=reason,
            preview=preview.strip(),
            context=context.strip(),
            duplicate_of=duplicate_of,
            candidates=candidates,
            latency_ms=round(latency, 2),
        )
    except Exception as exc:
        return GateResult(
            action="skip",
            reason="gate_error",
            candidates=candidates,
            error=f"{type(exc).__name__}: {exc}",
        )


# ---------------------------------------------------------------------------
# Pending "uncertain" + consenso al prompt successivo — stessa meccanica del
# consenso sui medium del recall (ICH-66): file per session_id+cwd, TTL,
# consumo singolo. Qui il payload conservato e' la POST /memories gia' pronta:
# al "si'" dell'utente la esegue l'hook recall, identica a quella del worker.
# ---------------------------------------------------------------------------

RETAIN_PENDING_TTL = 900.0


def retain_pending_dir() -> str:
    """Directory del pending retain, separata da quella del recall.
    HS_RETAIN_PENDING_DIR consente l'override nei test."""
    return os.environ.get("HS_RETAIN_PENDING_DIR") or cache_dir() + "/hs-retain-pending"


def retain_consent_decision(prompt: str) -> str | None:
    """Si'/no standalone o verbi espliciti di salvataggio nei prompt misti.
    Speculare a consent_decision del recall, con il lessico del salvare."""
    text = _normalize_prompt(prompt)
    if not text:
        return None
    standalone_negative = {"no", "no grazie"}
    standalone_positive = {"si", "sì", "si grazie", "sì grazie", "va bene", "d accordo", "certo", "procedi"}
    explicit_negative = (
        r"\bnon\s+salvar(?:la|lo|e)\b",
        r"\b(?:scartala|scartalo|non\s+salvare)\b",
    )
    if text in standalone_negative or any(re.search(pattern, text) for pattern in explicit_negative):
        return "negative"
    explicit_positive = r"\b(?:salvala|salvalo|salva\s+pure)\b"
    if text in standalone_positive or re.search(explicit_positive, text):
        return "positive"
    return None


def save_retain_pending(
    session_id: str, cwd: str, api_url: str, payload: dict, preview: str
) -> bool:
    """Mette in attesa la POST del retain in cerca di conferma. False se non
    c'e' session_id o lo stato non e' scrivibile: in quel caso NON si chiede
    (una domanda senza pending non potrebbe mantenere la promessa del si')."""
    return save_pending(
        retain_pending_dir(),
        session_id,
        cwd,
        [{"api_url": api_url, "payload": payload, "preview": preview}],
    )


def handle_retain_consent(
    prompt: str, session_id: str, cwd: str, ttl: float = RETAIN_PENDING_TTL
) -> dict | None:
    """Da chiamare al prompt successivo alla domanda del gate (hook recall).
    Positivo -> consuma il pending ed esegue la POST conservata; negativo o
    prompt nuovo -> scarta. Ritorna un esito per debug/notifica, None se non
    c'era alcun pending valido."""
    directory = retain_pending_dir()
    decision = retain_consent_decision(prompt)
    if decision == "positive":
        consumed = consume_pending(directory, session_id, cwd, ttl)
        if not consumed:
            return None
        entry = consumed[0] if isinstance(consumed[0], dict) else {}
        preview = str(entry.get("preview") or "")
        try:
            request = urllib.request.Request(
                str(entry["api_url"]) + "/memories",
                data=json.dumps(entry["payload"]).encode("utf-8"),
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            with urllib.request.urlopen(request, timeout=10) as response:
                status = response.status
            return {"action": "saved", "status": status, "preview": preview}
        except Exception as exc:
            return {
                "action": "error",
                "error": f"{type(exc).__name__}: {exc}",
                "preview": preview,
            }
    if discard_pending_if_present(directory, session_id, cwd, ttl):
        return {
            "action": "discarded",
            "reason": "negative" if decision == "negative" else "new_prompt",
        }
    return None
