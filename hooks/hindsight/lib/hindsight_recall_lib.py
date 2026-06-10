"""Logica pura per il recall composto (step H mirato).

Estratta dall'heredoc inline di hindsight-recall.sh per renderla unit-testabile
(stesso pattern di hindsight_config.py). Tre funzioni:
  - needs_context: il prompt e' corto E referenziale → vale comporre col contesto?
  - tail_turns:    estrae l'ultimo turno sostanzioso dalla coda del transcript
  - compose_query: unisce contesto + prompt nella query di recall

Nessuna dipendenza dalla rete: solo decisione + costruzione stringa. Il flag
recall_compose_enabled vive nella config; qui needs_context lo rispetta.
"""

from __future__ import annotations

import json
import os
import re

# Rimozione blocchi-memoria iniettati (recall/knowledge-pages) dai turni passati,
# per non comporre la query con memorie gia' iniettate (anti-feedback-loop). Stesso
# marcatore usato dal retain worker; duplicato qui per non importare il worker (heavy)
# nel path caldo del recall hook.
_MEMORY_BLOCK_RE = re.compile(
    r"<hindsight_memories>.*?</hindsight_memories>"
    r"|## Hindsight (?:persistent memory|knowledge pages).*?Verify mutable facts against the repo\.",
    re.DOTALL,
)

_WORD_RE = re.compile(r"\w+", re.UNICODE)


def strip_memory_block(text: str) -> str:
    if not text:
        return text
    return _MEMORY_BLOCK_RE.sub("", text).strip()


def needs_context(prompt: str, cfg: dict) -> tuple[bool, str]:
    """True se il prompt e' corto e referenziale → conviene comporre col contesto.

    Assume che il prompt abbia gia' passato il gate dei recall_min_prompt_chars.
    Restituisce (decisione, motivo) per logging/diagnostica.
    """
    if not cfg.get("recall_compose_enabled"):
        return (False, "compose disabilitato (flag)")
    p = (prompt or "").strip().lower()
    n = len(p)
    if n > int(cfg.get("recall_compose_max_chars", 60)):
        return (False, "prompt lungo → autosufficiente")
    toks = set(_WORD_RE.findall(p))
    deictics = set(cfg.get("recall_compose_deictics") or [])
    hit = toks & deictics
    if hit:
        return (True, f"deittico: {sorted(hit)}")
    for c in cfg.get("recall_compose_continuations") or []:
        if c in p:
            return (True, "continuazione del turno precedente")
    return (False, "nessun deittico/continuazione → autosufficiente")


def _iter_transcript_tail(transcript_path: str, max_lines: int = 80):
    """Legge solo la coda del transcript JSONL (per latenza). Yield dei record dict."""
    try:
        with open(transcript_path, "r", encoding="utf-8", errors="replace") as f:
            lines = f.readlines()
    except OSError:
        return
    for line in lines[-max_lines:]:
        line = line.strip()
        if not line:
            continue
        try:
            yield json.loads(line)
        except (ValueError, json.JSONDecodeError):
            continue


def _record_text(rec: dict) -> tuple[str, str]:
    """Da un record di transcript estrae (role, testo umano ripulito)."""
    msg = rec.get("message") or {}
    role = msg.get("role") or rec.get("type") or ""
    content = msg.get("content")
    if isinstance(content, str):
        return role, strip_memory_block(content)
    if isinstance(content, list):
        parts = []
        for b in content:
            if isinstance(b, dict) and b.get("type") == "text":
                parts.append(b.get("text") or "")
        return role, strip_memory_block("\n".join(parts).strip())
    return role, ""


def tail_turns(transcript_path: str, cfg: dict) -> str:
    """Estrae gli ultimi N turni sostanziosi (testo utente/assistente) dalla coda
    del transcript, piu' recente per ultimo. Salta tool-call, blocchi-memoria e
    turni troppo corti (< recall_compose_min_context_chars)."""
    if not transcript_path or not os.path.exists(transcript_path):
        return ""
    n_turns = max(1, int(cfg.get("recall_compose_context_turns", 1)))
    min_chars = int(cfg.get("recall_compose_min_context_chars", 40))
    collected: list[str] = []
    for rec in reversed(list(_iter_transcript_tail(transcript_path))):
        role, txt = _record_text(rec)
        if role not in ("user", "assistant"):
            continue
        if not txt or txt.startswith("<") or len(txt) < min_chars:
            continue
        collected.append(txt)
        if len(collected) >= n_turns:
            break
    collected.reverse()
    return " ".join(collected).strip()


def compose_query(prompt: str, context: str, cfg: dict) -> str:
    """Unisce contesto e prompt. Se il contesto e' vuoto restituisce il prompt nudo
    (nessuna composizione → la cache del prompt resta utilizzabile)."""
    context = (context or "").strip()
    if not context:
        return prompt
    # Tronca il contesto per non far esplodere la query.
    cap = int(cfg.get("recall_compose_max_chars", 60)) * 8
    if len(context) > cap:
        context = context[:cap]
    return f"Contesto recente: {context} Domanda: {prompt}"


# Tipi di fatto accettati dall'endpoint recall. Filtro difensivo: un valore non
# valido in config viene scartato invece di provocare un 400 dal server.
_VALID_RECALL_TYPES = ("world", "experience", "observation")


def build_recall_payload(prompt: str, cfg: dict, query_timestamp: str) -> dict:
    """Costruisce il payload per POST /memories/recall.

    Il campo `types` viene incluso SOLO se cfg['recall_types'] contiene almeno un
    valore valido; altrimenti e' omesso → il server cerca tutti e tre i tipi
    (default API). I valori non validi vengono filtrati silenziosamente.
    """
    payload = {
        "query": prompt,
        "budget": cfg["recall_budget"],
        "max_tokens": cfg["recall_max_tokens"],
        "tags": cfg["recall_tags"],
        "tags_match": cfg["recall_tags_match"],
        "query_timestamp": query_timestamp,
    }
    types = [t for t in (cfg.get("recall_types") or []) if t in _VALID_RECALL_TYPES]
    if types:
        payload["types"] = types
    # Entita': l'API REST le include di DEFAULT (include.entities ha un default
    # non-null), a differenza della GUI/MCP che le tengono spente. La lista
    # entita' per-fatto e' rumore nel contesto iniettato (specie sugli
    # observation consolidati) e non serve al ragionamento, solo al retrieval
    # lato server. Con recall_include_entities=false mandiamo include.entities=
    # null per spegnerle ALLA FONTE: il server salta pure la query SQL di
    # risoluzione entita' (engine: `if include_entities and top_scored`).
    if not cfg.get("recall_include_entities", False):
        payload["include"] = {"entities": None}
    return payload
