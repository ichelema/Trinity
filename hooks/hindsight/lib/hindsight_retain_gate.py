"""Gate semantico pre-retain (ICH-67): decide se la finestra del turno precedente
(valutata a UserPromptSubmit, ICH-86) va persistita.

Stesso pattern di hindsight_recall_filter.py: una sola chiamata OpenAI con
response_format json_schema strict e validazione completa della risposta.
Attivo ogni volta che retain_enabled e' true; esiti (li applica il worker):
  retain     -> POST diretta e silenziosa nel bank
  skip       -> nessun salvataggio
  uncertain  -> POST messa in pending + domanda all'utente; il consenso al
                prompt successivo la esegue (handle_retain_consent, stessa
                meccanica dei medium del recall ICH-66)
Un errore TECNICO del gate e' fail-closed lato worker (ICH-73): nessun
salvataggio, notifica non bloccante una volta per sessione e rollback del
contatore cosi' la prossima valutazione riprova. L'errore resta visibile in
GateResult.error e nel debug log.
Il gate produce anche il `context` descrittivo del retain; se manca (retain o
uncertain) il worker mette comunque la POST in pending e Claude propone una
riga di dominio: al prompt successivo handle_retain_consent risolve il context
nell'ordine esplicito (`context: …`) -> gate -> proposta nel transcript ->
riga repo/branch (fallback_context, zero rete).
"""

from __future__ import annotations

import json
import os
import re
import time
import urllib.parse
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
        save_pending,
    )
    from hindsight_recall_lib import last_assistant_text
except ImportError:
    from .hindsight_config import cache_dir
    from .hindsight_multibank import fetch_bank_results
    from .hindsight_recall_filter import (
        ApiCall,
        _normalize_prompt,
        api_json,
        consume_pending,
        save_pending,
    )
    from .hindsight_recall_lib import last_assistant_text

GATE_ACTIONS = {"retain", "skip", "uncertain"}

REASONS_BY_ACTION = {
    "retain": {
        "durable_decision",
        "root_cause_or_workaround",
        "environment_constraint",
        "convention_or_preference",
        "discarded_approach",
    },
    "skip": {
        "trivial_or_ephemeral",
        "repo_recoverable",
        "intermediate_attempt",
        "duplicate",
        "no_durable_knowledge",
    },
    "uncertain": {"borderline"},
}
GATE_REASONS = set().union(*REASONS_BY_ACTION.values())

GATE_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    # Ordine deliberato (ICH-84): con response_format strict il modello emette
    # le chiavi nell'ordine dello schema, quindi scrive il giudizio di
    # copertura PRIMA della action e la condiziona su quello. Non riordinare.
    "properties": {
        "durable_claims": {"type": "array", "items": {"type": "string"}},
        "covered_by": {"type": "array", "items": {"type": "integer"}},
        "action": {"type": "string", "enum": sorted(GATE_ACTIONS)},
        "reason": {"type": "string", "enum": sorted(GATE_REASONS)},
        "preview": {"type": "string"},
        "context": {"type": "string"},
    },
    "required": [
        "durable_claims",
        "covered_by",
        "action",
        "reason",
        "preview",
        "context",
    ],
}

# Derivato dal draft di ICH-67. Il preview e' nella lingua della conversazione:
# e' il testo che Claude mostra all'utente e ri-usa per il retain MCP.
GATE_PROMPT = """You decide whether a Claude Code session window deserves to be persisted to Hindsight long-term memory.

Choose action "retain" ONLY if the window contains durable, verified knowledge likely useful in future sessions: decisions or conventions with their rationale, domain rules, non-obvious constraints, root causes and workarounds, relevant discarded approaches, environment quirks.

Choose action "skip" for: temporary or trivial information, anything easily recoverable from the repository or git history, ordinary command output, intermediate attempts, work still in progress with no conclusion, or content whose durable part is already covered by the existing memories provided, even when the window wraps it in fresh ephemeral material.

Ask yourself: "Could this information avoid work, mistakes or repeated analysis in the future?"

Duplicate check — fill these two fields BEFORE choosing the action:
- durable_claims: the durable facts this window states, at most 3, one short sentence each, in the same language as the conversation. List them even when you believe memory already contains them — covered_by is where you say so. Ephemeral material — command output, intermediate attempts, anything recoverable from the repository or git history — is not a durable claim; leave the list empty when the window states none.
- covered_by: indices of the existing memories that, taken together, already cover EVERY claim you listed. Judge substance, not wording: a memory that is phrased differently, is more general, or is written in another language still covers a claim. Extra ephemeral material in the window never prevents coverage. If you listed no durable claim but the window's content is already reflected by the existing memories, set covered_by to the memories that reflect it. Leave it empty when at least one claim is missing from the existing memories, or when no existing memory was provided.

Rules:
1. action "retain": set preview to ONE short self-contained sentence, in the same language as the conversation, stating WHAT gets stored and WHY it matters (favour the why over the what).
2. action "skip": set preview to "".
3. action "uncertain": when the window contains knowledge that WOULD be durable but is not yet confirmed — an unverified hypothesis with concrete value, a provisional decision, conflicting sources — or when retain and skip both seem defensible; set preview to the short summary you would store. Coverage is never borderline: when covered_by is not empty, choose "skip" with reason "duplicate" instead of "uncertain".
4. reason must match the action:
   - action "retain": durable_decision, root_cause_or_workaround, environment_constraint, convention_or_preference, discarded_approach
   - action "skip": trivial_or_ephemeral, repo_recoverable, intermediate_attempt, duplicate, no_durable_knowledge
   - action "uncertain": borderline (the only reason it admits)
5. A covered window is a duplicate: whenever covered_by is not empty the window adds nothing durable, so the verdict is action "skip" with reason "duplicate" — not "repo_recoverable", not "no_durable_knowledge", not "intermediate_attempt". Conversely, never report reason "duplicate" with an empty covered_by.
6. Judge the window as a whole: ONE durable claim that is not already covered is enough to retain, and the ephemeral material around it does not matter. A window whose durable claims are all covered is never retained, however much extra text it contains.
7. context: ONE short line, in the same language as the conversation, describing the technical domain the window is about — subject and project, not an activity and not a bare category (e.g. "architettura del recall automatico Hindsight nel plugin Trinity", NOT "tooling"). Fill it for every action; empty string only if the window has no technical subject."""


@dataclass
class GateResult:
    action: str
    reason: str
    preview: str = ""
    # Riga descrittiva del dominio della finestra, prodotta dal gate: diventa il
    # campo `context` del retain (vuota = il worker mette il retain in pending e
    # chiede un context all'utente).
    context: str = ""
    duplicate_of: list[int] = field(default_factory=list)
    # Evidenza di copertura come l'ha dichiarata il modello (ICH-84): su skip
    # alimenta duplicate_of, su retain/uncertain resta solo osservabilita'.
    durable_claims: list[str] = field(default_factory=list)
    covered_by: list[int] = field(default_factory=list)
    candidates: list[dict] = field(default_factory=list)
    latency_ms: float = 0.0
    error: str | None = None


DEDUP_QUERY_MAX_CHARS = 1500

# Solo fatti grezzi come candidati di dedup (ICH-89). Le observation di
# consolidamento sono un layer DERIVATO dai raw fact (che restano sempre nel
# bank), non hanno document_id e vengono riscritte in background: come
# candidati spiazzano i fatti atomici dai top-8, non si etichettano per
# documento nel bench e non si espandono per documento (ICH-88). Filtrandole
# alla fonte, bench e produzione vedono lo stesso mix di candidati.
DEDUP_CANDIDATE_TYPES = ["world", "experience"]


def _bounded_dedup_query(first_user: str, last_assistant: str) -> str:
    """Compone una query entro il limite conservando entrambe le estremità.
    A ogni parte spetta metà budget; quello inutilizzato passa all'altra."""
    separator = "\n\n"
    budget = DEDUP_QUERY_MAX_CHARS - len(separator)
    first_budget = min(len(first_user), budget // 2)
    assistant_budget = min(len(last_assistant), budget - first_budget)
    first_budget = min(len(first_user), budget - assistant_budget)
    return f"{first_user[:first_budget]}{separator}{last_assistant[-assistant_budget:]}"


def dedup_query(summary: dict) -> str:
    """Query anti-duplicato composta dal primo prompt user e dall'ultima
    risposta assistant. Il primo conserva il soggetto anche quando la chiusura
    devia su test o PR; l'ultima conserva la conclusione. Se coincidono o una
    manca, usa un solo testo. Fallback al prompt user legacy."""
    turns = summary.get("turns") or []
    first_user = next(
        (text.strip() for role, text in turns if role == "user" and text.strip()),
        "",
    )
    last_assistant = next(
        (
            text.strip()
            for role, text in reversed(turns)
            if role == "assistant" and text.strip()
        ),
        "",
    )
    if first_user and last_assistant and first_user != last_assistant:
        return _bounded_dedup_query(first_user, last_assistant)
    query = first_user or last_assistant or (summary.get("last_user_prompt") or "")
    return query[:DEDUP_QUERY_MAX_CHARS]


# Completamento per documento (ICH-88): un documento duplicato produce 4-13
# fatti atomici e il top-k ne mostra solo una parte; il giudizio di copertura
# (ICH-84) esige OGNI claim in vista, quindi ogni documento citato dal top-k
# viene completato coi suoi fatti restanti. Tetti: per documento (oltre, il
# documento resta parziale com'era nel top-k: scartarlo perderebbe recall) e
# totale sui candidati (oltre, i documenti successivi restano parziali).
# Le GET sono sequenziali (~15 ms l'una a server sano) ma condividono una
# deadline pari al timeout del gate: un server appeso non somma 8 timeout.
DEDUP_DOC_FACTS_CAP = 20
DEDUP_MAX_TOTAL_CANDIDATES = 40
DEDUP_DOC_FETCH_TIMEOUT = 5.0


def _text_key(r: dict) -> str:
    return " ".join((r.get("text") or "").lower().split())


def fetch_document_facts(
    url: str, document_id: str, timeout: float, cap: int = DEDUP_DOC_FACTS_CAP
) -> list[dict] | None:
    """Tutti i fatti del documento via GET /memories/list?document_id=… (i
    fatti sono restituiti piu' recenti prima; per un documento sono i fatti
    estratti dallo stesso testo, l'ordine non conta). None su qualsiasi errore,
    se il documento supera il cap o se la pagina non lo contiene per intero
    (`total` oltre gli item ricevuti): in tutti i casi il chiamante lascia il
    documento com'e' nel top-k."""
    query = urllib.parse.urlencode(
        {"document_id": document_id, "limit": cap + 1}, quote_via=urllib.parse.quote
    )
    req = urllib.request.Request(url + "/memories/list?" + query, method="GET")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as res:
            data = json.loads(res.read().decode("utf-8", errors="replace"))
    except Exception:
        return None
    items = data.get("items") if isinstance(data, dict) else None
    if not isinstance(items, list) or len(items) > cap:
        return None
    total = data.get("total")
    if isinstance(total, int) and total > len(items):
        return None
    return [r for r in items if isinstance(r, dict)]


def complete_documents(
    ranked: list[tuple[str, dict]],
    timeout: float,
    max_total: int = DEDUP_MAX_TOTAL_CANDIDATES,
    fetch=None,
    clock=time.monotonic,
) -> list[dict]:
    """Raggruppa i candidati del top-k per document_id (ordine di prima
    apparizione) e completa ogni documento coi fatti mancanti, letti dal bank
    da cui il candidato proviene. I fatti dello stesso documento restano
    contigui; un candidato senza document_id (observation, entita') resta
    alla sua posizione relativa, non completato. Best-effort: GET fallita,
    deadline scaduta o documento oltre i tetti => il documento resta parziale,
    esattamente com'era nel top-k. Un documento rifiutato per budget non
    consuma il dedup dei successivi (i suoi fatti non sono in vista)."""
    fetch = fetch or fetch_document_facts
    groups: dict[str, list[dict]] = {}
    origin: dict[str, str] = {}
    order: list[str] = []
    for i, (url, r) in enumerate(ranked):
        doc_id = r.get("document_id")
        is_doc = isinstance(doc_id, str) and bool(doc_id)
        key = doc_id if is_doc else f"\x00{i}"
        if key not in groups:
            groups[key] = []
            order.append(key)
        groups[key].append(r)
        if is_doc:
            origin.setdefault(key, url)
    seen_ids = {r.get("id") for _u, r in ranked if r.get("id") is not None}
    seen_text = {_text_key(r) for _u, r in ranked}
    total = len(ranked)
    deadline = clock() + timeout
    out: list[dict] = []
    for key in order:
        facts = list(groups[key])
        remaining = deadline - clock()
        if key in origin and remaining > 0:
            full = fetch(origin[key], key, min(remaining, DEDUP_DOC_FETCH_TIMEOUT))
            if full is not None:
                extra: list[dict] = []
                extra_ids: set = set()
                extra_text: set[str] = set()
                for r in full:
                    rid = r.get("id")
                    text_key = _text_key(r)
                    if not text_key or text_key in seen_text or text_key in extra_text:
                        continue
                    if rid is not None and (rid in seen_ids or rid in extra_ids):
                        continue
                    extra.append(r)
                    extra_text.add(text_key)
                    if rid is not None:
                        extra_ids.add(rid)
                if total + len(extra) <= max_total:
                    facts.extend(extra)
                    total += len(extra)
                    seen_ids |= extra_ids
                    seen_text |= extra_text
        out.extend(facts)
    return out


def fetch_duplicate_candidates(
    bank_urls: list[str], query: str, timeout: float, max_candidates: int = 8
) -> list[dict]:
    """Memorie esistenti vicine alla finestra, dai bank di lettura: top-k di
    max_candidates fatti, poi ogni documento in vista completato coi suoi
    fatti restanti (ICH-88, vedi complete_documents). Best-effort: bank giu'
    o query vuota => lista vuota (il gate valuta senza controllo duplicati).
    Il tetto alla query evita il 400 "Query too long" del query-embedder
    (vedi recall_max_prompt_chars).
    Otto candidati, non tre (ICH-84): il giudizio di copertura richiede che
    OGNI claim della finestra sia in vista, e un documento duplicato produce
    in media 4-13 fatti atomici — con tre slot la copertura era quasi sempre
    parziale e il gate negava il duplicato pur avendo il documento giusto.
    Misurato anche a 12: piu' candidati portano in vista piu' documenti
    affini e le citazioni si disperdono, senza guadagno (bench ICH-84). Il
    top-8 mostrava pero' solo 2-5 dei fatti del documento duplicato,
    spiazzati dai fatti dei documenti affini: da qui il completamento.
    Il tetto lo applica il loop qui sotto: il server ignora `limit`, ma
    rispetta `types` (solo raw fact, vedi DEDUP_CANDIDATE_TYPES) e
    `include.entities` (spente come nel recall: rumore, e il gate legge solo
    il testo)."""
    if not query:
        return []
    payload = {
        "query": query[:DEDUP_QUERY_MAX_CHARS],
        "limit": max_candidates,
        "types": list(DEDUP_CANDIDATE_TYPES),
        "include": {"entities": None},
    }
    seen: set[str] = set()
    ranked: list[tuple[str, dict]] = []
    for url in bank_urls:
        for r in fetch_bank_results(url, payload, timeout):
            key = _text_key(r)
            if key and key not in seen:
                seen.add(key)
                ranked.append((url, r))
                if len(ranked) >= max_candidates:
                    break
        if len(ranked) >= max_candidates:
            break
    return complete_documents(ranked, timeout)


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
    """Valuta la finestra. Le violazioni STRUTTURALI della risposta (enum fuori
    schema, tipi errati, indici fuori range o ripetuti) e gli errori tecnici
    (key assente, timeout, HTTP, JSON) => "skip" con error valorizzato, che il
    worker tratta come fail-closed (nessun salvataggio + notifica). Le
    violazioni SEMANTICHE (action e reason entrambe valide ma male accoppiate)
    vengono invece normalizzate senza errore: la action decisa dal modello non
    cambia mai."""
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
        durable_claims = data.get("durable_claims")
        covered_by = data.get("covered_by")
        context = data.get("context")
        if not isinstance(action, str) or action not in GATE_ACTIONS:
            raise ValueError(f"action non valida: {action!r}")
        if not isinstance(reason, str) or reason not in GATE_REASONS:
            raise ValueError(f"reason non valida: {reason!r}")
        if not isinstance(preview, str):
            raise ValueError(f"preview non valida: {preview!r}")
        if not isinstance(context, str):
            raise ValueError(f"context non valido: {context!r}")
        if action == "retain" and not preview.strip():
            raise ValueError("preview vuota su action retain")
        if not isinstance(durable_claims, list) or any(
            not isinstance(claim, str) for claim in durable_claims
        ):
            raise ValueError(f"durable_claims non valide: {durable_claims!r}")
        if not isinstance(covered_by, list) or any(
            isinstance(i, bool) or not isinstance(i, int) for i in covered_by
        ):
            raise ValueError(f"covered_by non valido: {covered_by!r}")
        if len(set(covered_by)) != len(covered_by) or any(
            not 0 <= i < len(candidates) for i in covered_by
        ):
            raise ValueError(
                f"indici copertura fuori range o duplicati: {covered_by!r} "
                f"su {len(candidates)} candidati"
            )
        # ICH-84: la copertura e' un giudizio a se' (covered_by), emesso dal
        # modello PRIMA della action; la action resta comunque intoccabile
        # (ICH-82) — degradare a gate_error produrrebbe il fail-closed del
        # worker, cioe' la perdita della finestra. Su skip la copertura ha la
        # precedenza sulle altre reason: e' li' che si perdevano i duplicati
        # del bench ICH-72, gia' scartati ma etichettati repo_recoverable /
        # no_durable_knowledge / intermediate_attempt. Su retain/uncertain la
        # copertura resta sola evidenza (in GateResult): forzare skip qui
        # significherebbe far decidere a un'euristica la perdita di conoscenza.
        duplicate_of = covered_by if action == "skip" else []
        if duplicate_of:
            reason = "duplicate"
        elif action == "skip" and reason == "duplicate":
            # Claim di duplicato senza indici a supporto: l'esito resta skip.
            reason = "no_durable_knowledge"
        return GateResult(
            action=action,
            reason=reason,
            preview=preview.strip(),
            context=context.strip(),
            duplicate_of=duplicate_of,
            durable_claims=durable_claims,
            covered_by=covered_by,
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

# Proposta di Claude nel transcript: "context «…»" ma anche "Context proposto: «…»".
# Si prende l'ULTIMO match del testo dell'ultimo messaggio assistant.
RETAIN_CONTEXT_PROPOSAL_RE = re.compile(r"context[^«»\n]{0,20}«([^«»]+)»", re.IGNORECASE)

# Risposta esplicita dell'utente: l'intero prompt e' "context: <testo>" su UNA
# sola riga, con prefisso opzionale di assenso (lo stesso lessico standalone di
# retain_consent_decision: sì / si / va bene / d'accordo / certo / procedi)
# seguito da separatore opzionale (, . ; : ! -). Niente DOTALL: un prompt
# multi-riga che apre con "context:" e prosegue con altro e' testo libero ->
# new_prompt, come promesso dalla grammatica (mai un context implicito).
RETAIN_CONTEXT_REPLY_RE = re.compile(
    r"^\s*(?:(?:s[iì]|va\s+bene|d['’ ]?accordo|certo|procedi)\s*[,.;:!\-]?\s*)?context\s*:[ \t]*([^\n]+?)\s*$",
    re.IGNORECASE,
)


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


def retain_consent_context(prompt: str) -> str | None:
    """Testo del context se il prompt e' nella forma `context: <testo>` (anche
    `sì, context: <testo>`); None altrimenti. Testo vuoto/solo spazi -> None."""
    match = RETAIN_CONTEXT_REPLY_RE.match(prompt or "")
    if not match:
        return None
    return match.group(1).strip() or None


RETAIN_CONTEXT_PLACEHOLDER = "<PROPOSTA>"


def retain_context_from_transcript(transcript_path: str) -> str | None:
    """Ultimo match di RETAIN_CONTEXT_PROPOSAL_RE nell'ultimo messaggio assistant
    (last_assistant_text). None se assente/vuoto. Il placeholder letterale
    dell'istruzione («<PROPOSTA>»), ricopiato da Claude senza sostituirlo, non
    e' una proposta: si scarta e si guarda il match precedente."""
    matches = RETAIN_CONTEXT_PROPOSAL_RE.findall(last_assistant_text(transcript_path))
    for match in reversed(matches):
        text = match.strip()
        if text and text.upper() != RETAIN_CONTEXT_PLACEHOLDER:
            return text
    return None


def fallback_context(metadata: dict) -> str:
    """Ultima risorsa, zero rete: riga da metadata.repo / metadata.branch.
    repo+branch -> "sessione Claude Code nel repo {repo}, branch {branch}"
    solo repo   -> "sessione Claude Code nel repo {repo}"
    solo branch -> "sessione Claude Code sul branch {branch}"
    nessuno     -> "sessione Claude Code" """
    repo = str(metadata.get("repo") or "")
    branch = str(metadata.get("branch") or "")
    if repo and branch:
        return f"sessione Claude Code nel repo {repo}, branch {branch}"
    if repo:
        return f"sessione Claude Code nel repo {repo}"
    if branch:
        return f"sessione Claude Code sul branch {branch}"
    return "sessione Claude Code"


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
    prompt: str,
    session_id: str,
    cwd: str,
    ttl: float = RETAIN_PENDING_TTL,
    transcript_path: str = "",
) -> dict | None:
    """Da chiamare al prompt successivo alla domanda del gate (hook recall).
    Positivo (si' o `context: <testo>`) -> consuma il pending, risolve il
    context dell'item nell'ordine esplicito -> gate -> proposta di Claude nel
    transcript -> riga repo/branch, ed esegue la POST conservata (se la POST
    fallisce il pending viene rimesso in attesa: un secondo si' riprova);
    negativo o prompt nuovo -> scarta. Ritorna un esito per debug/notifica
    (con preview, e per il salvataggio anche context e context_source; per
    l'errore anche restored), None se non c'era alcun pending valido."""
    directory = retain_pending_dir()
    explicit = retain_consent_context(prompt)
    decision = "positive" if explicit else retain_consent_decision(prompt)
    if decision == "positive":
        consumed = consume_pending(directory, session_id, cwd, ttl)
        if not consumed:
            return None
        entry = consumed[0] if isinstance(consumed[0], dict) else {}
        preview = str(entry.get("preview") or "")
        try:
            # L'item e' quello scritto dal worker (payload {"items": [item]}):
            # un pending malformato finisce nel ramo error qui sotto, non in
            # una POST silenziosa senza context.
            item = entry["payload"]["items"][0]
            if explicit:
                context, context_source = explicit, "explicit"
            elif item.get("context"):
                context, context_source = str(item["context"]), "gate"
            else:
                proposal = retain_context_from_transcript(transcript_path)
                if proposal:
                    context, context_source = proposal, "proposal"
                else:
                    context = fallback_context(item.get("metadata") or {})
                    context_source = "fallback"
            item["context"] = context
            request = urllib.request.Request(
                str(entry["api_url"]) + "/memories",
                data=json.dumps(entry["payload"]).encode("utf-8"),
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            with urllib.request.urlopen(request, timeout=10) as response:
                status = response.status
            return {
                "action": "saved",
                "status": status,
                "preview": preview,
                "context": context,
                "context_source": context_source,
            }
        except Exception as exc:
            # POST fallita DOPO il consumo: senza ripristino il "si'" dell'utente
            # e' andato perso e un secondo "si'" non troverebbe nulla. Si rimette
            # il pending (TTL ripartito) cosi' il prossimo consenso riprova; il
            # document_id stabile fa fare upsert al server, niente doppioni.
            # L'item porta gia' il context risolto qui sopra (proposta/fallback):
            # al retry non serve rileggere un transcript nel frattempo cambiato.
            restored = save_retain_pending(
                session_id,
                cwd,
                str(entry.get("api_url") or ""),
                entry.get("payload") or {},
                preview,
            )
            return {
                "action": "error",
                "error": f"{type(exc).__name__}: {exc}",
                "preview": preview,
                "restored": restored,
            }
    consumed = consume_pending(directory, session_id, cwd, ttl)
    if not consumed:
        return None
    entry = consumed[0] if isinstance(consumed[0], dict) else {}
    return {
        "action": "discarded",
        "reason": "negative" if decision == "negative" else "new_prompt",
        "preview": str(entry.get("preview") or ""),
    }
