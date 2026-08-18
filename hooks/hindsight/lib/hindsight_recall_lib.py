"""Libreria di supporto per il recall Hindsight.

  - strip_memory_block: rimuove blocchi-memoria iniettati dai turni
  - last_assistant_text: ultimo testo assistant del transcript
  - build_recall_payload: costruisce il payload per POST /memories/recall
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
    r"|## Hindsight (?:persistent memory|knowledge pages|recall debug).*?Verify mutable facts against the repo\.",
    re.DOTALL,
)

def strip_memory_block(text: str) -> str:
    if not text:
        return text
    return _MEMORY_BLOCK_RE.sub("", text).strip()


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


def last_assistant_text(transcript_path: str, max_lines: int = 80) -> str:
    """Testo (blocchi text concatenati, ripuliti da strip_memory_block) dell'ULTIMO
    record assistant CON testo nella coda del transcript JSONL. Claude Code scrive
    un record per content-block: i record assistant di soli tool_use vengono
    saltati. "" se il file manca, non e' leggibile o non ha testo assistant."""
    if not transcript_path or not os.path.exists(transcript_path):
        return ""
    for rec in reversed(list(_iter_transcript_tail(transcript_path, max_lines))):
        role, txt = _record_text(rec)
        if role == "assistant" and txt:
            return txt
    return ""


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
    # Floor per-stadio lato server (hindsight-api >=0.8.4): min_scores viene
    # omesso del tutto se nessun floor e' configurato -> payload invariato.
    ms = {
        "semantic": cfg.get("recall_min_semantic"),
        "keyword": cfg.get("recall_min_keyword"),
        "reranker": cfg.get("recall_min_reranker"),
        "final": cfg.get("recall_min_final"),
    }
    ms = {k: v for k, v in ms.items() if v is not None}
    if ms:
        payload["min_scores"] = ms
    return payload
