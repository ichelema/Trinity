"""Pattern dei segreti condivisi dagli hook e dai benchmark Hindsight (ICH-159).

Una sola copia: worker del retain e benchmark del gate li importano da qui,
cosi' un fix arriva a entrambi.
"""

from __future__ import annotations

import re

# Mai portare segreti negli artefatti dei benchmark ne' negli esiti dei comandi.
SECRET_PATTERNS = (
    re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----"),
    re.compile(r"\bAuthorization\s*:\s*(?:Bearer|Basic)\s+\S+", re.I),
    re.compile(
        r"\b(?:api[_-]?key|access[_-]?token|auth[_-]?token|client[_-]?secret|password|passwd|pwd)\s*[:=]\s*['\"]?\S{8,}",
        re.I,
    ),
    re.compile(r"\b(?:gh[pousr]_[A-Za-z0-9_]{20,}|sk-ant-[A-Za-z0-9_-]{20,}|xox[baprs]-[A-Za-z0-9-]{20,})\b"),
    re.compile(r"\beyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\b"),
)

# Esiti dei comandi del worker (ICH-150): l'output dei comandi puo' contenere
# segreti, il dialogo no (filtrarlo e' fuori perimetro).
OUTCOME_SECRET_PATTERNS = SECRET_PATTERNS + (
    # Solo per gli esiti: un nome che FINISCE in api_key/_key/secret/password/
    # token (maiuscolo o minuscolo, anche tra virgolette JSON) seguito da : o =
    # e da un valore di 12+ caratteri. Copre OPENAI_API_KEY=, db_password=,
    # NPM_TOKEN:, "api_key": ...; lascia passare KeyError, key=..., --keyword=,
    # TOKENIZERS_PARALLELISM= e i valori corti. Poi chiavi sk-* e corpo base64
    # dei PEM (non solo esadecimale, cosi' gli SHA git restano).
    # Niente prefisso [A-Za-z0-9_]* davanti: con search() non serve e rende il
    # pattern quadratico sulle righe alfanumeriche lunghe (dump esadecimali).
    # ICH-155: restano le righe d'errore "unexpected token: X", "Error: cache_key=..."
    # e "duplicate primary_key: ...". Esenti solo in quel contesto: REDIS_CACHE_KEY=
    # o COSMOS_PRIMARY_KEY= (credenziali reali) restano fuori.
    re.compile(
        r"(?:api[_-]?key|(?<!: cache)(?<!duplicate primary)[_-]key|secret|passw(?:or)?d|(?<!unexpected )token)"
        r"[\"']?\s*[:=]\s*[\"']?[^\s\"']{12,}",
        re.I,
    ),
    re.compile(r"\bsk-[A-Za-z0-9_-]{20,}"),
    # Falso positivo accettato (ICH-155): scarta anche identificatori lunghi
    # non esadecimali (CamelCase di 40+ lettere). Distinguerli dal base64 dei
    # PEM vorrebbe dire far passare segreti base64 senza cifre: si perde una
    # prova, mai un segreto.
    re.compile(r"^(?=[A-Za-z0-9+/]*[G-Zg-z+/])[A-Za-z0-9+/]{40,}={0,2}$"),
)
