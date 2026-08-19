"""Filtro semantico post-recall e stato temporaneo per memorie dubbie."""

from __future__ import annotations

import contextlib
import hashlib
import json
import math
import os
import re
import time
import unicodedata
import urllib.request
from pathlib import Path
from typing import Callable, Sequence

# Override solo via env (ambiente fidato): la config di progetto non può
# dirottare l'endpoint. Usato dai test e2e per mockare il classificatore.
OPENAI_URL = os.environ.get("HS_OPENAI_URL", "https://api.openai.com/v1/chat/completions")

CLASSIFIER_REASONS = {
    "directly_actionable",
    "specific_constraint",
    "specific_preference",
    "specific_history",
    "plausible_but_uncertain",
    "generic_or_redundant",
    "tangential",
    "irrelevant",
}

CLASSIFIER_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "classifications": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "index": {"type": "integer"},
                    "confidence": {
                        "type": "string",
                        "enum": ["low", "medium", "high"],
                    },
                    "reason": {
                        "type": "string",
                        "enum": sorted(CLASSIFIER_REASONS),
                    },
                },
                "required": ["index", "confidence", "reason"],
            },
        }
    },
    "required": ["classifications"],
}

CLASSIFIER_PROMPT = """Classifica ogni memoria rispetto al prompt corrente. Valuta la sua utilità concreta, non la somiglianza di parole.

Livelli:
- high: contiene una decisione, preferenza, regola, configurazione, vincolo, causa/fix o fatto storico specifico e direttamente azionabile per il prompt. Potrebbe cambiare o rendere più sicura la risposta.
- medium: è plausibilmente utile, ma il collegamento non è abbastanza diretto o manca contesto per iniettarla senza chiedere all'utente.
- low: è generica, ridondante col prompt, tangenziale, non azionabile o irrilevante.

Regole:
1. Classifica ogni indice indipendentemente; restituisci esattamente una voce per indice.
2. Non alzare il livello per precauzione: medium esiste proprio per i dubbi.
3. Una memoria sullo stesso strumento ma su un problema diverso è low.
4. Una memoria mutabile ma specifica può essere high: verrà comunque verificata nel repository.
5. Non valutare se Hindsight avrebbe dovuto essere chiamato; valuta soltanto le memorie fornite."""

ApiCall = Callable[[str, str, str, str, dict, float], tuple[dict, float]]


def result_score(result: dict) -> float | None:
    """Restituisce scores.reranker; forme malformate e valori non finiti sono assenti."""
    scores = result.get("scores")
    value = scores.get("reranker") if isinstance(scores, dict) else None
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    score = float(value)
    return score if math.isfinite(score) else None


def classifier_input(prompt: str, candidates: list[tuple[int, dict]]) -> str:
    lines = [f"## Prompt corrente\n{prompt[:6000]}", "", "## Memorie da classificare"]
    for index, result in candidates:
        lines.append(
            f"[{index}] ({result.get('type') or '?'}) "
            f"{(result.get('text') or '')[:3000]}"
        )
    return "\n".join(lines)


def read_with_deadline(response, deadline: float) -> bytes:
    """Legge una risposta HTTP rispettando una deadline monotona complessiva."""
    chunks: list[bytes] = []
    while True:
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise TimeoutError("deadline HTTP superata")
        try:
            response.fp.raw._sock.settimeout(remaining)
        except (AttributeError, OSError):
            pass
        chunk = response.read(65_536)
        if not chunk:
            return b"".join(chunks)
        chunks.append(chunk)


def api_json(
    model: str,
    system: str,
    user: str,
    schema_name: str,
    schema: dict,
    timeout: float,
) -> tuple[dict, float]:
    key = os.environ.get("OPENAI_API_KEY")
    if not key:
        raise RuntimeError("OPENAI_API_KEY non impostata")
    body = {
        "model": model,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        "response_format": {
            "type": "json_schema",
            "json_schema": {
                "name": schema_name,
                "schema": schema,
                "strict": True,
            },
        },
    }
    request = urllib.request.Request(
        OPENAI_URL,
        data=json.dumps(body, ensure_ascii=False).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {key}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    started = time.perf_counter()
    deadline = time.monotonic() + timeout
    with urllib.request.urlopen(request, timeout=timeout) as response:
        data = json.loads(read_with_deadline(response, deadline).decode("utf-8", "replace"))
    content = data["choices"][0]["message"]["content"]
    return json.loads(content), (time.perf_counter() - started) * 1000


def route_results(
    prompt: str,
    results: Sequence[object],
    model: str,
    threshold: float,
    timeout: float,
    api_call: ApiCall = api_json,
) -> dict:
    """Instrada i risultati. Qualsiasi errore del classificatore è fail-open."""
    valid_results = [result for result in results if isinstance(result, dict)]
    automatic: list[dict] = []
    candidates: list[tuple[int, dict]] = []
    for index, result in enumerate(valid_results):
        score = result_score(result)
        if score is not None and score >= threshold:
            automatic.append({**result, "route": "bypass", "confidence": "high"})
        else:
            candidates.append((index, result))

    if not candidates:
        return {
            "automatic": automatic,
            "optional": [],
            "discarded": [],
            "latency_ms": 0.0,
            "classifier_called": False,
            "model": model,
        }

    try:
        data, latency = api_call(
            model,
            CLASSIFIER_PROMPT,
            classifier_input(prompt, candidates),
            "recall_result_classification",
            CLASSIFIER_SCHEMA,
            timeout,
        )
        rows = data.get("classifications")
        if not isinstance(rows, list):
            raise ValueError("classifications assente o non è una lista")
        expected = {index for index, _ in candidates}
        indices = [row.get("index") for row in rows if isinstance(row, dict)]
        if len(rows) != len(expected) or len(indices) != len(rows):
            raise ValueError("numero di classificazioni non valido")
        if set(indices) != expected or len(set(indices)) != len(indices):
            raise ValueError("classificazioni mancanti, duplicate o inattese")

        classified = {row["index"]: row for row in rows}
        by_index = dict(candidates)
        optional: list[dict] = []
        discarded: list[dict] = []
        for index in sorted(expected):
            row = classified[index]
            confidence = row.get("confidence")
            reason = row.get("reason")
            if confidence not in {"low", "medium", "high"}:
                raise ValueError("confidence non valida")
            if reason not in CLASSIFIER_REASONS:
                raise ValueError("reason non valida")
            enriched = {
                **by_index[index],
                "route": "classifier_high" if confidence == "high" else f"classifier_{confidence}",
                "confidence": confidence,
                "classifier_reason": reason,
            }
            if confidence == "high":
                automatic.append(enriched)
            elif confidence == "medium":
                optional.append(enriched)
            else:
                discarded.append(enriched)
        return {
            "automatic": automatic,
            "optional": optional,
            "discarded": discarded,
            "latency_ms": round(latency, 2),
            "classifier_called": True,
            "model": model,
        }
    except Exception as exc:
        return {
            "automatic": [
                {**result, "route": "fail_open", "confidence": "high"}
                for result in valid_results
            ],
            "optional": [],
            "discarded": [],
            "latency_ms": 0.0,
            "classifier_called": True,
            "model": model,
            "error": f"{type(exc).__name__}: {exc}",
        }


def _normalize_prompt(prompt: str) -> str:
    value = unicodedata.normalize("NFKC", prompt).casefold()
    value = re.sub(r"[^\wàèéìòù]+", " ", value, flags=re.UNICODE)
    return " ".join(value.split())


def consent_decision(prompt: str) -> str | None:
    """Riconosce consenso standalone o riferito esplicitamente alle memorie."""
    text = _normalize_prompt(prompt)
    if not text:
        return None
    standalone_negative = {"no", "no grazie"}
    standalone_positive = {"si", "sì", "si grazie", "sì grazie", "va bene", "d accordo", "certo",
                           "ok", "okay", "vai", "procedi", "yes", "perfetto"}
    explicit_negative = (
        r"\bnon\s+(?:le\s+)?(?:usare|usarle|mostrare|mostrarle|iniettare|iniettarle)\b",
        r"\b(?:ignorale|scartale|dimenticale)\b",
    )
    if text in standalone_negative or any(re.search(pattern, text) for pattern in explicit_negative):
        return "negative"
    if text in standalone_positive:
        return "positive"
    explicit_positive = r"\b(?:usale|utilizzale|mostrale|mostramele|iniettale)\b"
    pos_match = re.search(explicit_positive, text)
    if pos_match:
        prefix = text[:pos_match.start()]
        if re.search(r"\bnon\b", prefix):
            return "negative"
        consent_filler = r"(?:(?:si|sì|va bene|d accordo|certo|grazie)\s*)*"
        if re.fullmatch(consent_filler, prefix.strip()):
            return "positive"
    return None


def _pending_path(directory: str, session_id: str, cwd: str) -> Path | None:
    if not session_id:
        return None
    key = hashlib.sha256(f"{session_id}\0{cwd}".encode("utf-8")).hexdigest()[:32]
    return Path(directory) / f"{key}.json"


def _secure_directory(directory: str) -> Path:
    """Best-effort 0700: reale solo su POSIX. Su Windows/NTFS mkdir(mode=...)
    e chmod sono di fatto no-op (toccano solo il bit read-only): la protezione
    dei testi delle memorie dipende dalle ACL ereditate dalla directory cache
    per-utente. Vale anche per i chmod 0600 su lock e file pending."""
    path = Path(directory)
    path.mkdir(mode=0o700, parents=True, exist_ok=True)
    try:
        path.chmod(0o700)
    except OSError:
        pass
    return path


@contextlib.contextmanager
def _file_lock(path: Path, timeout: float = 2.0):
    lock_path = str(path) + ".lock"
    handle = None
    release = None
    acquired = False
    try:
        handle = open(lock_path, "a+b")
        try:
            os.chmod(lock_path, 0o600)
        except OSError:
            pass
        try:
            import fcntl

            def acquire(fd):
                fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)

            def unlock(fd):
                fcntl.flock(fd, fcntl.LOCK_UN)

        except ImportError:
            import msvcrt

            def acquire(fd):
                os.lseek(fd, 0, os.SEEK_SET)
                msvcrt.locking(fd, msvcrt.LK_NBLCK, 1)

            def unlock(fd):
                os.lseek(fd, 0, os.SEEK_SET)
                msvcrt.locking(fd, msvcrt.LK_UNLCK, 1)

        deadline = time.monotonic() + timeout
        while True:
            try:
                acquire(handle.fileno())
                acquired = True
                release = unlock
                break
            except (BlockingIOError, OSError):
                if time.monotonic() >= deadline:
                    break
                time.sleep(0.02)
    except OSError:
        if handle is not None:
            handle.close()
        handle = None

    try:
        yield acquired
    finally:
        if handle is not None:
            if acquired and release is not None:
                try:
                    release(handle.fileno())
                except OSError:
                    pass
            handle.close()


# Età oltre la quale lo sweep elimina gli artefatti orfani. Volutamente molto
# più ampia del recall_pending_ttl (900s): qui si fa igiene della directory,
# non si applica la scadenza — quella resta a consume/discard_if_present.
_SWEEP_AGE = 86400


def _sweep_stale(directory: str, now: float) -> None:
    """Best-effort: elimina pending scaduti di sessioni morte, .tmp di crash e
    .lock orfani (json assente) più vecchi di _SWEEP_AGE. Un .lock in uso su
    Windows non è cancellabile (msvcrt tiene il file aperto) e l'OSError viene
    ignorato. Chiamata solo dal percorso non comune di save_pending."""
    try:
        entries = list(os.scandir(directory))
    except OSError:
        return
    alive = {entry.name for entry in entries if entry.name.endswith(".json")}
    for entry in entries:
        try:
            if now - entry.stat().st_mtime <= _SWEEP_AGE:
                continue
            if entry.name.endswith(".json.lock") and entry.name[:-5] in alive:
                continue
            os.unlink(entry.path)
        except OSError:
            pass


def save_pending(
    directory: str,
    session_id: str,
    cwd: str,
    memories: list[dict],
    now: float | None = None,
) -> bool:
    path = _pending_path(directory, session_id, cwd)
    if path is None or not memories:
        return False
    try:
        _secure_directory(directory)
    except OSError:
        return False
    _sweep_stale(directory, time.time() if now is None else now)
    payload = {
        "created_at": time.time() if now is None else now,
        "session_id": session_id,
        "cwd": cwd,
        "memories": memories,
    }
    with _file_lock(path) as locked:
        if not locked:
            return False
        tmp = path.with_suffix(f".{os.getpid()}.tmp")
        try:
            with tmp.open("x", encoding="utf-8") as handle:
                json.dump(payload, handle, ensure_ascii=False)
            try:
                tmp.chmod(0o600)
            except OSError:
                pass
            os.replace(tmp, path)
            try:
                path.chmod(0o600)
            except OSError:
                pass
            return True
        except OSError:
            try:
                tmp.unlink()
            except OSError:
                pass
            return False


def consume_pending(
    directory: str,
    session_id: str,
    cwd: str,
    ttl: float,
    now: float | None = None,
) -> list[dict] | None:
    path = _pending_path(directory, session_id, cwd)
    # Fast-path senza lock: nel caso comune (nessun pending) si paga un solo stat.
    # Se il file compare tra il check e il return lo gestisce il prompt successivo.
    if path is None or not path.exists():
        return None
    current = time.time() if now is None else now
    with _file_lock(path) as locked:
        if not locked:
            return None
        try:
            with path.open(encoding="utf-8") as handle:
                payload = json.load(handle)
            created = float(payload["created_at"])
            memories = payload["memories"]
            valid = current - created <= ttl and isinstance(memories, list)
        except (OSError, ValueError, TypeError, KeyError, json.JSONDecodeError):
            memories = None
            valid = False
        try:
            path.unlink()
        except OSError:
            pass
    return memories if valid else None


def discard_pending_if_present(
    directory: str,
    session_id: str,
    cwd: str,
    ttl: float,
    now: float | None = None,
) -> bool:
    """Elimina atomicamente un pending valido senza separare verifica e delete."""
    path = _pending_path(directory, session_id, cwd)
    if path is None or not path.exists():
        return False
    current = time.time() if now is None else now
    with _file_lock(path) as locked:
        if not locked:
            return False
        try:
            with path.open(encoding="utf-8") as handle:
                payload = json.load(handle)
            created = float(payload["created_at"])
            valid = current - created <= ttl and isinstance(payload["memories"], list)
        except (OSError, ValueError, TypeError, KeyError, json.JSONDecodeError):
            valid = False
        try:
            path.unlink()
        except OSError:
            return False
    return valid
