#!/usr/bin/env python
"""Benchmark A/B/D di un tag semantico generato dal gate pre-retain (ICH-85).

Domanda: conviene far restituire al gate semantico pre-retain
(hindsight_retain_gate.py), nella STESSA chiamata LLM, un tag `topic:*` da un
vocabolario CHIUSO da unire ai tag fissi `claude-code` + `repo:<nome>`? Prima
di cablarlo in produzione serve capire come quel tag in piu' cambia la
consolidation (fatti piu' frammentati o meno) e il recall (piu' o meno
preciso), non solo se il gate lo produce in modo affidabile.

Esito misurato il 17 agosto 2026 (GATE_TAG_EVALUATION.md): RIFIUTATO. Il
codice di produzione non conosce il tag: il vocabolario, la regola aggiuntiva
del prompt, la enum dello schema e la validazione vivono SOLO qui, sopra il
prompt/schema di produzione (GATE_PROMPT/GATE_SCHEMA + gate_input), cosi' il
benchmark resta riproducibile senza codice morto nella libreria.

Questo script copia lo STESSO corpus di documenti reali su tre bank:
  A  tags = [claude-code, repo:<repo>]                    (baseline oggi)
  B  tags = A + [topic:*]                                 (solo tag in piu')
  D  tags = A + [topic:*], observation_scopes = [A, A+topic] (tag + scope
     esplicito: la consolidation produce osservazioni sia SENZA il topic
     [comparabili con A/B] sia CON [piu' mirate])

Fasi (ognuna riavviabile: gli artefatti in artifacts/ fanno da cache):
  export       esporta i --limit documenti piu' recenti del bank sorgente
               (stesse funzioni di tools/hindsight_export.py) in
               artifacts/gate_tag_docs.jsonl.
  tag          per ogni documento chiama il gate (ask_gate_tag: stesso modello,
               prompt e schema di produzione piu' la regola/enum del tag, senza
               candidati di dedup) e salva l'esito in
               artifacts/gate_tag_assignments.jsonl. Riprende da dove si era
               fermato (salta i document_id gia' presenti).
  retain       costruisce gli item A/B/D (build_variant_items) e li invia in
               batch da 20 con POST /memories async=true ai tre bank
               bench-tag-a/-b/-d. Stato di invio in
               artifacts/gate_tag_retain_state.json (riavviabile per batch).
  wait         polling di /operations finche' pending/processing non sono zero
               sui tre bank.
  consolidate  POST /consolidate su ciascun bank, poi polling
               dell'operation_id fino a completed/failed/cancelled.
  measure      per ciascun bank: metriche di frammentazione via query dirette
               al DB Postgres (sola lettura, memory_units/documents) e
               metriche di qualita' del recall (MRR/R@1/R@3, dup_rate_topk)
               con lo stesso payload di produzione di
               hindsight_recall_quality_bench.py. Scrive
               artifacts/gate_tag_metrics.json.
  report       tabella markdown A/B/D su stdout e in
               artifacts/gate_tag_report.md. Nessuna decisione automatica.

--dry-run: SOLA fase export, al massimo 3 documenti, nessuna scrittura remota
e nessuna chiamata al gate (solo GET sul bank sorgente). Utile per verificare
la connettivita' prima di lanciare il benchmark vero.

--cleanup: cancella (DELETE) i tre bank bench-tag-a/-b/-d e basta.

Il DB e' raggiunto in sola lettura (SET TRANSACTION READ ONLY, come
ops/hindsight-strip-branch-tags.py) con le stesse env HS_PGHOST/HS_PGPORT/
HS_PGUSER/HS_PGPASSWORD/HS_PGDATABASE dell'istanza pg0 locale.

Uso tipico (in ordine):
  PYTHONUTF8=1 python hindsight_gate_tag_bench.py --dry-run
  PYTHONUTF8=1 python hindsight_gate_tag_bench.py --phase all --limit 150

Gli artefatti restano locali (artifacts/ e' gitignored): niente contenuti nel
codice sorgente, solo avanzamento e metriche aggregate su stdout.
"""

from __future__ import annotations

import argparse
import concurrent.futures
import difflib
import importlib.util
import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

try:
    import psycopg2
except ImportError:  # pragma: no cover - ambiente senza psycopg2
    psycopg2 = None

HERE = Path(__file__).resolve().parent
PLUGIN_ROOT = HERE.parents[2]
LIB_DIR = PLUGIN_ROOT / "hooks" / "hindsight" / "lib"
sys.path.insert(0, str(LIB_DIR))

from hindsight_config import bank_url, load_config  # pyright: ignore[reportMissingImports]  # noqa: E402
from hindsight_recall_filter import api_json  # pyright: ignore[reportMissingImports]  # noqa: E402
from hindsight_retain_gate import (  # pyright: ignore[reportMissingImports]  # noqa: E402
    GATE_ACTIONS,
    GATE_PROMPT,
    GATE_SCHEMA,
    gate_input,
)

ARTIFACTS = HERE / "artifacts"
DOCS_FILE = ARTIFACTS / "gate_tag_docs.jsonl"
ASSIGN_FILE = ARTIFACTS / "gate_tag_assignments.jsonl"
RETAIN_STATE_FILE = ARTIFACTS / "gate_tag_retain_state.json"
METRICS_FILE = ARTIFACTS / "gate_tag_metrics.json"
REPORT_FILE = ARTIFACTS / "gate_tag_report.md"
DEFAULT_GOLD = HERE / "gold_questions.json"

VARIANTS = ("a", "b", "d")
PHASES = ("export", "tag", "retain", "wait", "consolidate", "measure", "report")

# Repo di fallback per il tag repo:<repo> di A quando il documento originale
# non porta metadata.repo (es. i vecchi retain automatici, che non lo
# scrivevano): il bank sorgente di default (trinity-project) e' il progetto
# Trinity stesso, quindi e' un fallback rappresentativo e non arbitrario.
DEFAULT_REPO_FALLBACK = "Trinity"

# Ritentativi POST /memories su errore 5xx/timeout (backoff in secondi).
RETAIN_RETRIES = 3
RETAIN_BACKOFF = (2.0, 5.0, 10.0)


# ---------------------------------------------------------------------------
# Tag del gate: vocabolario CHIUSO a bassa cardinalita' (8 valori, prefisso
# topic:, nessun bucket "other"), regola aggiuntiva del prompt e enum dello
# schema. Vive solo qui: in produzione il gate non conosce il tag (rifiutato
# dal bench, vedi GATE_TAG_EVALUATION.md).
# ---------------------------------------------------------------------------

GATE_TAG_VOCABULARY = [
    "topic:environment",
    "topic:config",
    "topic:workflow",
    "topic:debugging",
    "topic:architecture",
    "topic:data",
    "topic:integration",
    "topic:evaluation",
]

# Una riga inglese per valore: entra nella regola 8 del prompt.
GATE_TAG_DESCRIPTIONS: dict[str, str] = {
    "topic:environment": "OS, shell, PATH, installs, tool versions, host quirks (Windows/MSYS2, Linux)",
    "topic:config": "settings, config files, flags, hook and skill wiring",
    "topic:workflow": "processes, conventions, git/PR/issue/release procedures, working and communication preferences",
    "topic:debugging": "bugs, root causes, workarounds, incidents",
    "topic:architecture": "technical design decisions with their rationale, discarded approaches",
    "topic:data": "databases, migrations, schemas, memory banks, backups",
    "topic:integration": "external services, APIs, MCP servers, LLM providers and models",
    "topic:evaluation": "tests, benchmarks, measured results",
}


def gate_tag_schema(vocabulary: list[str]) -> dict:
    """GATE_SCHEMA di produzione piu' la enum "tag" (strict json_schema:
    additionalProperties False e OGNI proprieta' in required)."""
    return {
        **GATE_SCHEMA,
        "properties": {
            **GATE_SCHEMA["properties"],
            "tag": {"type": "string", "enum": sorted(vocabulary)},
        },
        "required": [*GATE_SCHEMA["required"], "tag"],
    }


def gate_tag_prompt(vocabulary: list[str]) -> str:
    """GATE_PROMPT di produzione piu' la regola 8: esattamente UN valore dal
    vocabolario, il dominio tecnico della finestra (non il tipo di conoscenza,
    gia' espresso da reason)."""
    entries = "; ".join(
        f"{value}: {GATE_TAG_DESCRIPTIONS.get(value, value)}" for value in vocabulary
    )
    rule = (
        "8. tag: exactly ONE value from the allowed list, the technical domain "
        "the window is mostly about (not the kind of knowledge, which is already "
        f"expressed by reason): {entries}."
    )
    return f"{GATE_PROMPT}\n{rule}"


def validate_gate_tag(value, vocabulary: list[str]) -> str:
    """Il tag se e' una str presente nel vocabolario, altrimenti "": un valore
    fuori enum (free-form) si scarta, MAI un'eccezione."""
    if isinstance(value, str) and vocabulary and value in vocabulary:
        return value
    return ""


def merge_gate_tags(base: list[str], tag: str) -> list[str]:
    """Nuova lista con l'ordine di base preservato (deduplicato) e il tag
    appeso una sola volta se non vuoto e non gia' presente."""
    out: list[str] = []
    seen: set[str] = set()
    for t in base:
        if t not in seen:
            seen.add(t)
            out.append(t)
    if tag and tag not in seen:
        out.append(tag)
    return out


def ask_gate_tag(content: str, cfg: dict, vocabulary: list[str] | None = None) -> dict:
    """Una chiamata al gate (stesso modello/timeout di produzione, api_json)
    con prompt e schema estesi dal tag; nessun candidato di dedup. Ritorna
    {tag, action, reason, context, latency_ms, error}: un errore tecnico o un
    tag fuori vocabolario danno tag "" (il documento resta "untagged")."""
    vocab = list(vocabulary or GATE_TAG_VOCABULARY)
    model = str(cfg.get("retain_gate_model", "gpt-5.6-luna"))
    timeout = float(cfg.get("retain_gate_timeout", 15))
    try:
        data, latency = api_json(
            model,
            gate_tag_prompt(vocab),
            gate_input(content, []),
            "retain_gate_decision",
            gate_tag_schema(vocab),
            timeout,
        )
        action = data.get("action")
        if not isinstance(action, str) or action not in GATE_ACTIONS:
            raise ValueError(f"action non valida: {action!r}")
        return {
            "tag": validate_gate_tag(data.get("tag"), vocab),
            "action": action,
            "reason": str(data.get("reason") or ""),
            "context": str(data.get("context") or "").strip(),
            "latency_ms": round(float(latency), 2),
            "error": None,
        }
    except Exception as exc:  # noqa: BLE001 - qualunque errore = documento non taggato, riportato
        return {
            "tag": "",
            "action": "",
            "reason": "",
            "context": "",
            "latency_ms": 0.0,
            "error": f"{type(exc).__name__}: {exc}",
        }


# ---------------------------------------------------------------------------
# Caricamento moduli riusati (STESSE funzioni di produzione/dei bench
# esistenti, mai una reimplementazione parallela: vedi le rispettive
# docstring per il perche').
# ---------------------------------------------------------------------------

def load_export_tool():
    """list_all_documents/fetch_document/build_item da tools/hindsight_export.py:
    un export diverso qui misurerebbe un corpus diverso da quello che backup e
    migrazione userebbero davvero."""
    spec = importlib.util.spec_from_file_location(
        "gate_tag_bench_export", HERE.parent / "tools" / "hindsight_export.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def load_recall_bench():
    """recall/first_relevant_rank/is_relevant da hindsight_recall_quality_bench.py:
    stessi parametri di produzione (RECALL_BUDGET/MAX_TOKENS/TAGS/TAGS_MATCH/
    TYPES) usati per giudicare i tre bank, altrimenti il confronto A/B/D non
    sarebbe a parita' di condizioni con le altre misure di qualita' del recall."""
    spec = importlib.util.spec_from_file_location(
        "gate_tag_bench_recall", HERE / "hindsight_recall_quality_bench.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


# ---------------------------------------------------------------------------
# Funzioni pure (nessuna rete, nessun DB): costruzione item A/B/D e metriche.
# Testate senza rete in test_hindsight_gate_tag_bench.py.
# ---------------------------------------------------------------------------

def repo_from_metadata(metadata: dict | None, fallback: str) -> str:
    """Repo per il tag repo:<repo> di A: metadata['repo'] del documento
    originale se presente e non vuoto, altrimenti `fallback`."""
    if isinstance(metadata, dict):
        repo = metadata.get("repo")
        if isinstance(repo, str) and repo.strip():
            return repo.strip()
    return fallback


def build_variant_items(doc: dict, tag: str) -> dict[str, dict]:
    """Item di retain per le tre varianti A/B/D (ICH-85) a partire da un
    documento esportato (document_id, content, context, timestamp, metadata)
    e dal tag del gate ("" se il gate non lo ha prodotto / era fuori
    vocabolario / era disabilitato per quel doc).

      A: tags = [claude-code, repo:<repo>]. Nessun observation_scopes.
      B: tags = A + [tag] (tag non vuoto); se tag vuoto, identica ad A.
      D: tags = come B; observation_scopes = [tags_A, tags_B] SOLO se tag non
         vuoto — con tag vuoto tags_A == tags_B e uno scope esplicito
         duplicato non aggiungerebbe nulla: D si comporta come A (nessun
         observation_scopes), esattamente come richiesto.

    content/context/timestamp/metadata/document_id sono IDENTICI nelle tre
    varianti (stessa fonte): l'unica differenza e' tags/observation_scopes.
    Mai un tag branch:*, dismesso da ICH-85 (vedi ops/hindsight-strip-branch-tags.py)."""
    base = {
        "document_id": doc["document_id"],
        "content": doc["content"],
        "context": doc.get("context"),
        "timestamp": doc.get("timestamp"),
        "metadata": doc.get("metadata") or {},
    }
    repo = repo_from_metadata(base["metadata"], DEFAULT_REPO_FALLBACK)
    tags_a = ["claude-code", f"repo:{repo}"]
    item_a = {**base, "tags": list(tags_a)}
    if tag:
        tags_b = merge_gate_tags(tags_a, tag)
        item_b = {**base, "tags": list(tags_b)}
        item_d = {
            **base,
            "tags": list(tags_b),
            "observation_scopes": [list(tags_a), list(tags_b)],
        }
    else:
        item_b = {**base, "tags": list(tags_a)}
        item_d = {**base, "tags": list(tags_a)}
    return {"a": item_a, "b": item_b, "d": item_d}


def pending_docs_for_tagging(docs: list[dict], existing_ids: set[str]) -> list[dict]:
    """Documenti non ancora presenti in artifacts/gate_tag_assignments.jsonl:
    la fase tag riprende da qui invece di ripagare il gate su tutto il corpus."""
    return [d for d in docs if d["document_id"] not in existing_ids]


def pending_items_for_variant(items: list[dict], sent_ids: set[str]) -> list[dict]:
    """Item non ancora inviati (per document_id) per una variante: la fase
    retain riprende da qui dopo un'interruzione a meta' batch."""
    return [it for it in items if it["document_id"] not in sent_ids]


def batch_items(items: list[dict], batch_size: int) -> list[list[dict]]:
    return [items[i : i + batch_size] for i in range(0, len(items), max(1, batch_size))]


def partition_key(tags: list[str] | None) -> tuple:
    """Chiave di partizione: l'insieme (ordinato, deduplicato) dei tag di un
    fatto. Due fatti nella stessa partizione condividono ESATTAMENTE lo stesso
    insieme di tag — e' la stessa nozione di 'recinto' della consolidation
    all_strict (vedi gold_questions.json, q04)."""
    return tuple(sorted(set(tags or [])))


def compute_fact_metrics(fact_rows: list[dict]) -> dict:
    """fact_rows: [{"tags": [...]}] per i fatti world+experience di un bank.
    partitions = insiemi di tag distinti; singleton_partitions = partizioni
    con un solo fatto (il segnale di frammentazione: piu' aumentano, piu' la
    consolidation produce osservazioni striminzite invece di sintesi ampie);
    docs_per_partition_avg = fatti per partizione in media (nome della chiave
    come da specifica; l'unita' di conteggio sono i FATTI, non i documenti
    sorgente)."""
    partitions: dict[tuple, int] = {}
    for row in fact_rows:
        key = partition_key(row.get("tags"))
        partitions[key] = partitions.get(key, 0) + 1
    n_partitions = len(partitions)
    singleton = sum(1 for c in partitions.values() if c == 1)
    avg = (sum(partitions.values()) / n_partitions) if n_partitions else 0.0
    return {
        "n_facts": len(fact_rows),
        "partitions": n_partitions,
        "singleton_partitions": singleton,
        "docs_per_partition_avg": round(avg, 3),
    }


def percentile(values: list[float], pct: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    index = min(len(ordered) - 1, max(0, round(pct / 100 * (len(ordered) - 1))))
    return ordered[index]


def compute_proof_stats(proof_counts: list[int]) -> dict:
    """avg/max/p50 di proof_count sulle observation di un bank (quante fonti
    ogni osservazione sintetizza: piu' basso in media = osservazioni piu'
    frammentate, coerente con partitions/singleton_partitions)."""
    if not proof_counts:
        return {"avg": 0.0, "max": 0, "p50": 0.0}
    return {
        "avg": round(sum(proof_counts) / len(proof_counts), 3),
        "max": max(proof_counts),
        "p50": percentile([float(c) for c in proof_counts], 50),
    }


def compute_topic_distribution(tags_rows: list[list[str]] | None) -> dict[str, int]:
    """Conteggio dei tag topic:* tra le liste di tag fornite (fatti o, per il
    report, i tag assegnati dal gate). Nessun ordine implicito: il chiamante
    ordina in stampa se serve."""
    dist: dict[str, int] = {}
    for tags in tags_rows or []:
        for t in tags or []:
            if isinstance(t, str) and t.startswith("topic:"):
                dist[t] = dist.get(t, 0) + 1
    return dist


def compute_observation_scope_split(tags_rows: list[list[str]] | None) -> dict:
    """Quante observation portano almeno un tag topic:* (scope 'con topic')
    contro quante no. Il segnale interessante e' su D (observation_scopes
    esplicito produce observation sia con che senza topic); su A/B e'
    comunque informativo per il confronto."""
    rows = list(tags_rows or [])
    with_topic = sum(
        1 for tags in rows if any(isinstance(t, str) and t.startswith("topic:") for t in (tags or []))
    )
    return {"with_topic": with_topic, "without_topic": len(rows) - with_topic}


def dup_rate_topk(topk_texts: list[list[str]], threshold: float = 0.9) -> float:
    """Quota di query in cui, tra i top-K risultati, ce ne sono almeno due con
    testo quasi identico (difflib.SequenceMatcher.ratio() >= threshold): un
    proxy di duplicazione senza il campo source_memory_ids, assente in
    RecallResult (vedi openapi.json)."""
    if not topk_texts:
        return 0.0
    dup_queries = 0
    for texts in topk_texts:
        found = False
        for i in range(len(texts)):
            for j in range(i + 1, len(texts)):
                if difflib.SequenceMatcher(None, texts[i] or "", texts[j] or "").ratio() >= threshold:
                    found = True
                    break
            if found:
                break
        if found:
            dup_queries += 1
    return dup_queries / len(topk_texts)


def build_report(metrics: dict, meta: dict) -> str:
    """Tabella markdown A/B/D delle metriche di measure_phase, con intestazione
    (N documenti/taggati/untagged, distribuzione topic, modello gate). Nessuna
    riga di verdetto: la decisione resta all'utente."""
    lines: list[str] = []
    lines.append("# Report benchmark gate tag (ICH-85)")
    lines.append("")
    lines.append(f"- N documenti: {meta.get('n_documents', 0)}")
    lines.append(f"- N taggati: {meta.get('n_tagged', 0)}")
    lines.append(f"- N untagged/errori: {meta.get('n_untagged', 0)} (di cui errori gate: {meta.get('n_errors', 0)})")
    lines.append(f"- Modello gate: {meta.get('gate_model', '')}")
    topic_dist = meta.get("topic_distribution") or {}
    if topic_dist:
        lines.append("- Distribuzione topic assegnati dal gate:")
        for tag, count in sorted(topic_dist.items(), key=lambda kv: -kv[1]):
            lines.append(f"  - {tag}: {count}")
    else:
        lines.append("- Distribuzione topic assegnati dal gate: (nessuna)")
    lines.append("")

    rows_order = [
        ("n_documents", "N documenti"),
        ("n_facts", "N fatti (world+experience)"),
        ("n_observations", "N observation"),
        ("observations_per_fact", "Observation / fatto"),
        ("partitions", "Partizioni tag distinte"),
        ("singleton_partitions", "Partizioni singleton"),
        ("docs_per_partition_avg", "Fatti / partizione (media)"),
        ("MRR", "MRR"),
        ("R@1", "R@1"),
        ("R@3", "R@3"),
        ("dup_rate_topk", "Quota query con duplicati nel top-K"),
    ]
    lines.append("| Metrica | A | B | D |")
    lines.append("|---|---|---|---|")
    for key, label in rows_order:
        vals = [metrics.get(v, {}).get(key, "") for v in VARIANTS]
        lines.append(f"| {label} | {vals[0]} | {vals[1]} | {vals[2]} |")
    for sub, label in (("avg", "proof_count medio"), ("max", "proof_count max"), ("p50", "proof_count p50")):
        vals = [metrics.get(v, {}).get("proof_count", {}).get(sub, "") for v in VARIANTS]
        lines.append(f"| {label} | {vals[0]} | {vals[1]} | {vals[2]} |")
    for sub, label in (("with_topic", "Observation con topic:*"), ("without_topic", "Observation senza topic:*")):
        vals = [metrics.get(v, {}).get("observation_scope_split", {}).get(sub, "") for v in VARIANTS]
        lines.append(f"| {label} | {vals[0]} | {vals[1]} | {vals[2]} |")
    lines.append("")
    lines.append(
        "Nessuna decisione automatica: valutare i numeri sopra (frammentazione "
        "vs qualita' del recall) prima di cablare il tag nel worker di "
        "produzione (esito del 2026-08-17: rifiutato, vedi GATE_TAG_EVALUATION.md)."
    )
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Utility I/O (file locali).
# ---------------------------------------------------------------------------

def read_jsonl(path: Path) -> list[dict]:
    if not path.exists():
        return []
    out = []
    with path.open(encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if line:
                out.append(json.loads(line))
    return out


def load_json(path: Path):
    try:
        with path.open(encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return None


def write_json(path: Path, data) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    with tmp.open("w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    tmp.replace(path)


# ---------------------------------------------------------------------------
# HTTP minimale (stdlib, come gli altri bench/tool del plugin).
# ---------------------------------------------------------------------------

def http_get(url: str, timeout: float) -> dict:
    req = urllib.request.Request(url, headers={"Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as res:
        return json.loads(res.read().decode("utf-8", errors="replace"))


def http_post(url: str, payload: dict, timeout: float) -> dict:
    req = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=timeout) as res:
        body = res.read().decode("utf-8", errors="replace")
    return json.loads(body) if body.strip() else {}


def http_delete(url: str, timeout: float) -> dict:
    req = urllib.request.Request(url, method="DELETE")
    with urllib.request.urlopen(req, timeout=timeout) as res:
        body = res.read().decode("utf-8", errors="replace")
    return json.loads(body) if body.strip() else {}


def post_with_retry(url: str, payload: dict, timeout: float, retries: int = RETAIN_RETRIES) -> dict:
    """POST con ritentativi su 5xx/timeout/errore di rete (backoff crescente).
    Un 4xx e' un errore del payload, non transitorio: si propaga subito."""
    last_exc: Exception | None = None
    for attempt in range(max(1, retries)):
        try:
            return http_post(url, payload, timeout)
        except urllib.error.HTTPError as e:
            if e.code < 500:
                raise
            last_exc = e
        except (urllib.error.URLError, TimeoutError, OSError) as e:
            last_exc = e
        if attempt < retries - 1:
            time.sleep(RETAIN_BACKOFF[min(attempt, len(RETAIN_BACKOFF) - 1)])
    assert last_exc is not None
    raise last_exc


def default_source_bank(cfg: dict) -> str:
    """Nome del bank sorgente di default: ultimo segmento di cfg['api_url']
    (il core risolto), decodificato da eventuale percent-encoding."""
    raw = (cfg.get("api_url") or "").rstrip("/").rsplit("/", 1)[-1]
    return urllib.parse.unquote(raw) or "trinity-project"


# ---------------------------------------------------------------------------
# Fasi.
# ---------------------------------------------------------------------------

def export_phase(cfg: dict, source_bank: str, limit: int, page: int, timeout: float) -> int:
    export_mod = load_export_tool()
    source_url = bank_url(cfg, source_bank)
    print(f"[export] bank sorgente: {source_bank} ({source_url})")
    try:
        summaries, total_start = export_mod.list_all_documents(source_url, page, timeout)
    except urllib.error.URLError as e:
        print(f"[export] ERRORE: server non raggiungibile ({e})")
        return 1
    summaries = summaries[:limit]
    print(f"[export] {len(summaries)} documenti selezionati (bank totale {total_start})")
    ARTIFACTS.mkdir(parents=True, exist_ok=True)
    written = 0
    skipped_empty = 0
    with DOCS_FILE.open("w", encoding="utf-8") as handle:
        for i, summ in enumerate(summaries, 1):
            doc_id = summ.get("id")
            try:
                full = export_mod.fetch_document(source_url, doc_id, timeout)
            except urllib.error.URLError as e:
                print(f"[export]   {doc_id}: ERRORE fetch ({e}), saltato")
                continue
            item = export_mod.build_item(full)
            if not (item.get("content") or "").strip():
                skipped_empty += 1
                continue
            handle.write(json.dumps(item, ensure_ascii=False) + "\n")
            written += 1
            print(f"\r[export] {i}/{len(summaries)}", end="", flush=True)
    print()
    print(f"[export] {written} documenti scritti in {DOCS_FILE} ({skipped_empty} scartati: original_text vuoto)")
    return 0 if written else 1


def tag_phase(cfg: dict, workers: int) -> int:
    docs = read_jsonl(DOCS_FILE)
    if not docs:
        print(f"[tag] {DOCS_FILE} vuoto o assente: esegui prima la fase export")
        return 1
    existing_ids = {row["document_id"] for row in read_jsonl(ASSIGN_FILE)}
    pending = pending_docs_for_tagging(docs, existing_ids)
    print(f"[tag] {len(docs)} documenti, {len(existing_ids)} gia' etichettati, {len(pending)} da valutare")
    if not pending:
        return 0

    ARTIFACTS.mkdir(parents=True, exist_ok=True)

    def run(doc: dict):
        result = ask_gate_tag(doc["content"], cfg)
        return doc, result

    done = 0
    with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as pool, ASSIGN_FILE.open(
        "a", encoding="utf-8"
    ) as handle:
        for doc, result in pool.map(run, pending):
            row = {"document_id": doc["document_id"], **result}
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")
            handle.flush()
            done += 1
            print(f"\r[tag] {done}/{len(pending)}", end="", flush=True)
    print()
    rows = read_jsonl(ASSIGN_FILE)
    tagged = sum(1 for r in rows if r.get("tag"))
    errors = sum(1 for r in rows if r.get("error"))
    print(f"[tag] totale {len(rows)}: {tagged} taggati, {len(rows) - tagged} senza tag (di cui {errors} errori gate)")
    return 0


def retain_phase(cfg: dict, banks: dict[str, str], batch_size: int, timeout: float, retries: int) -> int:
    docs = read_jsonl(DOCS_FILE)
    if not docs:
        print(f"[retain] {DOCS_FILE} vuoto o assente: esegui prima la fase export")
        return 1
    assignments = {row["document_id"]: row for row in read_jsonl(ASSIGN_FILE)}
    missing = [d["document_id"] for d in docs if d["document_id"] not in assignments]
    if missing:
        print(
            f"[retain] ATTENZIONE: {len(missing)} documenti senza assignment "
            "(fase tag incompleta), trattati come tag vuoto (come A)"
        )

    state = load_json(RETAIN_STATE_FILE) or {}
    rc = 0
    for variant in VARIANTS:
        bank_name = banks[variant]
        items = []
        for doc in docs:
            tag = (assignments.get(doc["document_id"]) or {}).get("tag") or ""
            items.append(build_variant_items(doc, tag)[variant])
        url = bank_url(cfg, bank_name)
        sent_ids = set(state.get(variant, {}).get("sent_document_ids", []))
        pending = pending_items_for_variant(items, sent_ids)
        batches = batch_items(pending, batch_size)
        print(
            f"[retain] bank {bank_name}: {len(items)} item totali, {len(sent_ids)} gia' "
            f"inviati, {len(pending)} da inviare in {len(batches)} batch"
        )
        for i, batch in enumerate(batches, 1):
            try:
                post_with_retry(f"{url}/memories", {"items": batch, "async": True}, timeout, retries)
            except Exception as e:  # noqa: BLE001 - qualunque fallimento ferma questa variante, non l'intero run
                print(f"[retain] bank {bank_name}: ERRORE batch {i}/{len(batches)}: {e}")
                rc = 1
                break
            sent_ids.update(it["document_id"] for it in batch)
            state[variant] = {"sent_document_ids": sorted(sent_ids)}
            write_json(RETAIN_STATE_FILE, state)
            print(
                f"\r[retain] bank {bank_name}: batch {i}/{len(batches)} inviato "
                f"({len(sent_ids)}/{len(items)})",
                end="",
                flush=True,
            )
        print()
    return rc


def count_in_flight(bank_base_url: str, timeout: float) -> int:
    """Numero di operazioni pending+processing su un bank (tutte, non solo i
    retain: la fase wait deve aspettare anche eventuali consolidation
    auto-innescate dai retain appena arrivati)."""
    n = 0
    for status in ("pending", "processing"):
        offset = 0
        while True:
            data = http_get(f"{bank_base_url}/operations?status={status}&limit=100&offset={offset}", timeout)
            ops = data.get("operations") or []
            n += len(ops)
            total = int(data.get("total", len(ops)))
            offset += len(ops)
            if not ops or offset >= total:
                break
    return n


def wait_phase(bank_urls: list[str], timeout: float, poll_interval: float, wait_timeout: float) -> int:
    deadline = time.monotonic() + wait_timeout
    last_report = 0.0
    while True:
        details = {}
        total = 0
        alive = True
        for url in bank_urls:
            try:
                n = count_in_flight(url, timeout)
            except urllib.error.URLError as e:
                print(f"[wait] ERRORE: {url} non raggiungibile ({e})")
                alive = False
                continue
            details[url] = n
            total += n
        if not alive:
            return 1
        if total == 0:
            print("[wait] nessuna operazione pending/processing residua")
            return 0
        now = time.monotonic()
        if now - last_report >= 30 or last_report == 0:
            print(f"[wait] in volo: {details}")
            last_report = now
        if now >= deadline:
            print(f"[wait] TIMEOUT dopo {wait_timeout:.0f}s: operazioni ancora in volo {details}")
            return 1
        time.sleep(poll_interval)


def poll_operation(bank_url_: str, operation_id: str, timeout: float, poll_interval: float, wait_timeout: float) -> bool:
    deadline = time.monotonic() + wait_timeout
    while True:
        try:
            data = http_get(f"{bank_url_}/operations/{urllib.parse.quote(operation_id, safe='')}", timeout)
        except urllib.error.URLError as e:
            print(f"[consolidate] {bank_url_}: ERRORE poll ({e})")
            return False
        status = data.get("status")
        if status in ("completed", "failed", "cancelled", "not_found"):
            print(f"[consolidate] {bank_url_}: operazione {operation_id} -> {status}")
            return status == "completed"
        if time.monotonic() >= deadline:
            print(f"[consolidate] TIMEOUT: {bank_url_} operazione {operation_id} ancora '{status}'")
            return False
        time.sleep(poll_interval)


def consolidate_phase(bank_urls: list[str], timeout: float, poll_interval: float, wait_timeout: float) -> int:
    rc = 0
    for url in bank_urls:
        try:
            data = http_post(f"{url}/consolidate", {}, timeout)
        except urllib.error.URLError as e:
            print(f"[consolidate] {url}: ERRORE ({e})")
            rc = 1
            continue
        op_id = data.get("operation_id")
        print(f"[consolidate] {url}: operation_id={op_id} deduplicated={data.get('deduplicated')}")
        if not op_id:
            continue
        if not poll_operation(url, op_id, timeout, poll_interval, wait_timeout):
            rc = 1
    return rc


# ---------------------------------------------------------------------------
# DB (sola lettura, stesse credenziali/pattern di ops/hindsight-strip-branch-tags.py).
# ---------------------------------------------------------------------------

def db_params() -> dict:
    return dict(
        host=os.environ.get("HS_PGHOST", "127.0.0.1"),
        port=int(os.environ.get("HS_PGPORT", "5432")),
        user=os.environ.get("HS_PGUSER", "hindsight"),
        password=os.environ.get("HS_PGPASSWORD", "hindsight"),
        dbname=os.environ.get("HS_PGDATABASE", "hindsight"),
    )


def open_conn():
    conn = psycopg2.connect(**db_params())
    conn.autocommit = False
    cur = conn.cursor()
    cur.execute("SET TRANSACTION READ ONLY")
    cur.close()
    return conn


def fetch_document_count(conn, bank_id: str) -> int:
    cur = conn.cursor()
    cur.execute("SELECT count(*) FROM documents WHERE bank_id=%s", (bank_id,))
    n = cur.fetchone()[0]
    cur.close()
    return n


def fetch_fact_rows(conn, bank_id: str) -> list[dict]:
    cur = conn.cursor()
    cur.execute(
        "SELECT tags FROM memory_units WHERE bank_id=%s AND fact_type IN ('world','experience')",
        (bank_id,),
    )
    rows = [{"tags": r[0]} for r in cur.fetchall()]
    cur.close()
    return rows


def fetch_observation_rows(conn, bank_id: str) -> list[dict]:
    cur = conn.cursor()
    cur.execute(
        "SELECT tags, proof_count FROM memory_units WHERE bank_id=%s AND fact_type='observation'",
        (bank_id,),
    )
    rows = [{"tags": r[0], "proof_count": r[1] or 0} for r in cur.fetchall()]
    cur.close()
    return rows


def measure_bank(conn, recall_mod, api_base: str, bank_name: str, queries: list[dict], k: int, timeout: float) -> dict:
    n_documents = fetch_document_count(conn, bank_name)
    fact_rows = fetch_fact_rows(conn, bank_name)
    obs_rows = fetch_observation_rows(conn, bank_name)

    fact_metrics = compute_fact_metrics(fact_rows)
    proof_stats = compute_proof_stats([r["proof_count"] for r in obs_rows])
    topic_dist = compute_topic_distribution([r["tags"] for r in fact_rows])
    scope_split = compute_observation_scope_split([r["tags"] for r in obs_rows])
    n_observations = len(obs_rows)
    n_facts = fact_metrics["n_facts"]
    observations_per_fact = round(n_observations / n_facts, 3) if n_facts else 0.0

    rr = r1 = r3 = 0.0
    topk_texts: list[list[str]] = []
    for q in queries:
        try:
            res = recall_mod.recall(api_base, bank_name, q["query"])
        except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError) as e:
            print(f"  [{bank_name}] {q.get('id')} ERRORE recall: {e}")
            res = []
        rank = recall_mod.first_relevant_rank(res, q, k)
        if rank:
            rr += 1.0 / rank
            if rank == 1:
                r1 += 1
            if rank <= 3:
                r3 += 1
        topk_texts.append([r.get("text", "") for r in res[:k]])
    n = len(queries) or 1

    return {
        "bank": bank_name,
        "n_documents": n_documents,
        **fact_metrics,
        "n_observations": n_observations,
        "observations_per_fact": observations_per_fact,
        "proof_count": proof_stats,
        "topic_distribution": topic_dist,
        "observation_scope_split": scope_split,
        "MRR": round(rr / n, 4),
        "R@1": round(r1 / n, 4),
        "R@3": round(r3 / n, 4),
        "dup_rate_topk": round(dup_rate_topk(topk_texts), 4),
    }


def measure_phase(cfg: dict, banks: dict[str, str], gold_path: str, k: int, timeout: float) -> int:
    if psycopg2 is None:
        print("[measure] ERRORE: modulo psycopg2 non disponibile")
        return 1
    try:
        with open(gold_path, encoding="utf-8") as f:
            gold = json.load(f)
    except OSError as e:
        print(f"[measure] ERRORE: gold set non leggibile ({gold_path}): {e}")
        return 1
    queries = gold.get("queries") or []
    recall_mod = load_recall_bench()
    api_base = f"{(cfg.get('bank') or {}).get('api_base', '').rstrip('/')}/banks"

    try:
        conn = open_conn()
    except Exception as e:  # noqa: BLE001 - qualunque fallimento di connessione e' fatale per questa fase
        print(f"[measure] ERRORE: connessione al DB fallita ({e})")
        return 1

    metrics: dict[str, dict] = {}
    try:
        for variant in VARIANTS:
            bank_name = banks[variant]
            m = measure_bank(conn, recall_mod, api_base, bank_name, queries, k, timeout)
            metrics[variant] = m
            print(
                f"[measure] {bank_name}: n_documents={m['n_documents']} n_facts={m['n_facts']} "
                f"partitions={m['partitions']} n_observations={m['n_observations']} MRR={m['MRR']}"
            )
        conn.rollback()
    finally:
        conn.close()

    ARTIFACTS.mkdir(parents=True, exist_ok=True)
    write_json(METRICS_FILE, metrics)
    print(f"[measure] metriche scritte in {METRICS_FILE}")
    return 0


def report_phase(cfg: dict) -> int:
    metrics = load_json(METRICS_FILE)
    if not metrics:
        print(f"[report] {METRICS_FILE} assente: esegui prima la fase measure")
        return 1
    docs = read_jsonl(DOCS_FILE)
    assignments = read_jsonl(ASSIGN_FILE)
    tagged = sum(1 for r in assignments if r.get("tag"))
    errors = sum(1 for r in assignments if r.get("error"))
    topic_dist = compute_topic_distribution([[r["tag"]] if r.get("tag") else [] for r in assignments])
    meta = {
        "n_documents": len(docs),
        "n_tagged": tagged,
        "n_untagged": len(assignments) - tagged,
        "n_errors": errors,
        "gate_model": cfg.get("retain_gate_model", ""),
        "topic_distribution": topic_dist,
    }
    text = build_report(metrics, meta)
    print(text)
    ARTIFACTS.mkdir(parents=True, exist_ok=True)
    REPORT_FILE.write_text(text, encoding="utf-8")
    print(f"\n[report] scritto in {REPORT_FILE}")
    return 0


def dry_run(cfg: dict, source_bank: str, prefix: str, timeout: float) -> int:
    """SOLA fase export su al massimo 3 documenti: solo GET sul bank sorgente,
    nessuna scrittura remota, nessuna chiamata al gate."""
    export_mod = load_export_tool()
    source_url = bank_url(cfg, source_bank)
    print(f"[dry-run] bank sorgente: {source_bank} ({source_url})")
    print(f"[dry-run] bank di destinazione (NON creati qui): {prefix}-a, {prefix}-b, {prefix}-d")
    try:
        summaries, total_start = export_mod.list_all_documents(source_url, 3, timeout)
    except urllib.error.URLError as e:
        print(f"[dry-run] ERRORE: server non raggiungibile ({e})")
        return 1
    summaries = summaries[:3]
    print(f"[dry-run] documenti trovati (bank totale {total_start}): {len(summaries)}")
    for summ in summaries:
        doc_id = summ.get("id")
        try:
            full = export_mod.fetch_document(source_url, doc_id, timeout)
        except urllib.error.URLError as e:
            print(f"[dry-run]   {doc_id}: ERRORE fetch ({e})")
            continue
        item = export_mod.build_item(full)
        print(
            f"[dry-run]   {doc_id}: content={len(item.get('content') or '')} chars "
            f"tags={item.get('tags')}"
        )
    print("[dry-run] nessuna scrittura remota, nessuna chiamata gate: fasi successive NON eseguite")
    return 0


def cleanup(cfg: dict, prefix: str, timeout: float) -> int:
    rc = 0
    for variant in VARIANTS:
        name = f"{prefix}-{variant}"
        url = bank_url(cfg, name)
        try:
            http_delete(url, timeout)
            print(f"[cleanup] {name}: cancellato")
        except urllib.error.HTTPError as e:
            if e.code == 404:
                print(f"[cleanup] {name}: gia' assente (404)")
            else:
                print(f"[cleanup] {name}: ERRORE HTTP {e.code}")
                rc = 1
        except urllib.error.URLError as e:
            print(f"[cleanup] {name}: ERRORE ({e})")
            rc = 1
    return rc


# ---------------------------------------------------------------------------
# CLI.
# ---------------------------------------------------------------------------

def run_phase(phase: str, args, cfg: dict, source_bank: str, banks: dict[str, str]) -> int:
    if phase == "export":
        return export_phase(cfg, source_bank, args.limit, args.page, args.export_timeout)
    if phase == "tag":
        return tag_phase(cfg, args.workers)
    if phase == "retain":
        return retain_phase(cfg, banks, args.batch_size, args.retain_timeout, args.retries)
    if phase == "wait":
        bank_urls = [bank_url(cfg, name) for name in banks.values()]
        return wait_phase(bank_urls, args.op_timeout, args.poll_interval, args.wait_timeout)
    if phase == "consolidate":
        bank_urls = [bank_url(cfg, name) for name in banks.values()]
        return consolidate_phase(bank_urls, args.op_timeout, args.poll_interval, args.wait_timeout)
    if phase == "measure":
        return measure_phase(cfg, banks, args.gold, args.k, args.recall_timeout)
    if phase == "report":
        return report_phase(cfg)
    print(f"[gate-tag-bench] fase sconosciuta: {phase}")
    return 1


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--phase", choices=["all", *PHASES], default="all")
    parser.add_argument("--limit", type=int, default=150, help="documenti piu' recenti da esportare")
    parser.add_argument("--source-bank", default="", help="default: bank core risolto da hindsight.config.json")
    parser.add_argument("--prefix", default="bench-tag", help="prefisso dei 3 bank di destinazione (-a/-b/-d)")
    parser.add_argument("--cleanup", action="store_true", help="cancella i 3 bank di destinazione e basta")
    parser.add_argument("--dry-run", action="store_true", help="sola fase export su max 3 documenti, nessuna scrittura")
    parser.add_argument("--wait-timeout", type=float, default=3600.0, help="secondi (fasi wait/consolidate)")
    parser.add_argument("--poll-interval", type=float, default=5.0, help="secondi tra due poll (wait/consolidate)")
    parser.add_argument("--workers", type=int, default=4, help="concorrenza della fase tag")
    parser.add_argument("--batch-size", type=int, default=20, help="item per batch POST /memories")
    parser.add_argument("--retries", type=int, default=RETAIN_RETRIES, help="ritentativi POST /memories su 5xx")
    parser.add_argument("--k", type=int, default=3, help="cutoff del recall (= recall_max_results)")
    parser.add_argument("--page", type=int, default=100, help="dimensione pagina GET /documents")
    parser.add_argument("--gold", default=str(DEFAULT_GOLD), help="gold set per la fase measure")
    parser.add_argument("--export-timeout", type=float, default=20.0)
    parser.add_argument("--retain-timeout", type=float, default=60.0)
    parser.add_argument("--recall-timeout", type=float, default=30.0)
    parser.add_argument("--op-timeout", type=float, default=30.0)
    args = parser.parse_args()

    cfg = load_config()
    source_bank = args.source_bank or default_source_bank(cfg)
    banks = {v: f"{args.prefix}-{v}" for v in VARIANTS}

    if args.cleanup:
        return cleanup(cfg, args.prefix, args.op_timeout)
    if args.dry_run:
        return dry_run(cfg, source_bank, args.prefix, args.export_timeout)

    phases = list(PHASES) if args.phase == "all" else [args.phase]
    for phase in phases:
        rc = run_phase(phase, args, cfg, source_bank, banks)
        if rc != 0:
            print(f"[gate-tag-bench] fase '{phase}' fallita (exit {rc}), interrotto")
            return rc
    return 0


if __name__ == "__main__":
    sys.exit(main())
