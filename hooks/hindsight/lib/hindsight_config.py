"""Loader di configurazione condiviso per gli hook Hindsight.

Fonte unica di verita' per i valori tunabili (URL bank, parametri recall/retain/
reflect). Ordine di caricamento (gli ultimi vincono):
  1. DEFAULTS hardcoded qui sotto
  2. file hindsight.config.json (stessa cartella; override via HS_CONFIG_FILE)
  3. override da variabili d'ambiente (retrocompatibilita' coi nomi gia' usati)

Uso da Python:   from hindsight_config import load_config; cfg = load_config()
Uso da bash:     python hindsight_config.py --get api_url
                 python hindsight_config.py            # dump completo (debug)
"""

from __future__ import annotations

import json
import os
import sys

DEFAULTS = {
    "api_url": "http://127.0.0.1:8888/v1/default/banks/trinity-project",
    # Interruttori master dell'automazione hook. False => l'hook esce subito,
    # senza chiamate di rete ne' estrazione LLM. Default: attivi (comportamento
    # storico invariato). Override anche via HS_CFG_RECALL_ENABLED / HS_CFG_RETAIN_ENABLED.
    "recall_enabled": True,
    "retain_enabled": True,
    "recall_budget": "low",
    "recall_max_tokens": 800,
    "recall_max_results": 8,
    # Filtra i tipi di fatto cercati dal server. Vuoto => tutti (world+experience+
    # observation), default API. Valori validi: "world", "experience", "observation".
    "recall_types": [],
    # Entita' nei risultati recall. L'API REST le include di DEFAULT (a differenza
    # di GUI/MCP che le tengono spente): la lista entita' per-fatto e' rumore nel
    # contesto iniettato e non serve al ragionamento. False => il payload manda
    # include.entities=null e il server le spegne alla fonte (salta pure la SQL).
    "recall_include_entities": False,
    "recall_min_prompt_chars": 20,
    # Tetto MAX alla query di recall: il query-embedder rifiuta query > 500 token
    # (HTTP 400 "Query too long"). Su prompt con grossi incollati (codice, commit,
    # HTML) il recall fallirebbe silenziosamente. Tronchiamo la query (non il prompt
    # inviato a Claude) alla parte iniziale, che di norma contiene l'intento.
    # ~1500 char ≈ 375 tok di prosa; per codice (più denso) abbassare se rivedi 400.
    "recall_max_prompt_chars": 1500,
    "recall_tags": ["claude-code"],
    "recall_tags_match": "any",
    "recall_cache_ttl": 300,
    "recall_cache_dir": "/tmp/hs-recall-cache",
    "recall_timeout": 6,
    # Parametri di chunking del retain, consumati da hindsight-retain-worker.py.
    # Devono stare nei DEFAULTS o load_config li scarta dalla whitelist (riga "if
    # k in cfg"). I valori coincidono coi fallback hardcoded del worker.
    "retain_mode": "chunked",
    "retain_overlap_turns": 1,
    "retain_tool_calls": False,
    "retain_every_n_turns": 3,
    "retain_max_files": 15,
    "retain_max_cmds": 10,
    "retain_text_truncate": 2000,
    # context: dominio/i del task da mettere nel campo `context` del retain
    # (schema "claude-code/<dom1>[/<dom2>][/<dom3>]"). NB: in Hindsight il context
    # e' descrittivo (frame per l'LLM estrattore), NON strutturale: relazioni ed
    # observation-scope si reggono su entita' e tag, non sul context. Quindi qui
    # puntiamo solo a un frame d'estrazione piu' utile del vecchio repo/branch.
    #   context_extraction          master switch (False => context piano "claude-code")
    #   context_extraction_strategy "llm" usa il modello; "heuristic" deriva i domini
    #                               dai path dei file modificati (zero rete). "llm"
    #                               ricade automaticamente su "heuristic" se fallisce.
    #   context_extraction_model    modello per la strategia "llm"
    "context_extraction": False,
    "context_extraction_strategy": "llm",
    "context_extraction_model": "gpt-4.1-nano",
    "reflect_budget": "mid",
    "reflect_max_tokens": 2000,
    "recall_compose_enabled": False,
    "recall_compose_max_chars": 60,
    "recall_compose_context_turns": 1,
    "recall_compose_min_context_chars": 40,
    "recall_compose_deictics": [
        "questo",
        "questa",
        "questi",
        "queste",
        "quello",
        "quella",
        "quelli",
        "quelle",
        "qui",
        "qua",
        "adesso",
        "ora",
        "poi",
        "cosi",
        "ciò",
        "cio",
    ],
    "recall_compose_continuations": [
        "e adesso",
        "e poi",
        "e ora",
        "e quindi",
        "vai avanti",
        "continua",
        "prosegui",
        "riprova",
    ],
    "mental_model_max_tokens": 1024,
    "mental_models_inject_on_start": False,
    "mental_models_inject_ids": ["user-profile", "project-conventions"],
    "mental_models": [],
    # Debug: se attivo, recall/retain scrivono un evento JSONL per ispezione.
    # debug_log_file vuoto => <project_root>/logs/hindsight-debug.log (vedi hindsight_debug.py)
    "debug_log_enabled": False,
    "debug_log_file": "",
}

# Nomi env legacy gia' usati nel codebase -> chiave di config. Mantengono il
# comportamento esistente (hanno precedenza sul file JSON).
ENV_OVERRIDES = {
    "HINDSIGHT_API_URL": "api_url",
    "HINDSIGHT_CACHE_DIR": "recall_cache_dir",
    "HINDSIGHT_CACHE_TTL": "recall_cache_ttl",
    "HS_RETAIN_EVERY_N": "retain_every_n_turns",
}


def _cast(value: str, sample):
    """Converte la stringa env al tipo del default. Liste accettano JSON o CSV."""
    try:
        if isinstance(sample, bool):
            return value.lower() in ("1", "true", "yes")
        if isinstance(sample, int):
            return int(value)
        if isinstance(sample, list):
            value = value.strip()
            if value.startswith("["):
                return json.loads(value)
            return [v.strip() for v in value.split(",") if v.strip()]
        return value
    except (ValueError, json.JSONDecodeError):
        return sample


def _config_path() -> str:
    return os.environ.get("HS_CONFIG_FILE") or os.path.join(
        os.path.dirname(os.path.abspath(__file__)), "hindsight.config.json"
    )


def load_config() -> dict:
    cfg = dict(DEFAULTS)

    # 2. file JSON
    try:
        with open(_config_path(), encoding="utf-8") as f:
            data = json.load(f)
        for k, v in data.items():
            if k in cfg and v is not None:
                cfg[k] = v
    except (OSError, ValueError):
        pass

    # 3. override env (nomi legacy + generico HS_CFG_<CHIAVE>)
    for env_name, key in ENV_OVERRIDES.items():
        val = os.environ.get(env_name)
        if val:
            cfg[key] = _cast(val, DEFAULTS[key])
    for key in DEFAULTS:
        val = os.environ.get("HS_CFG_" + key.upper())
        if val:
            cfg[key] = _cast(val, DEFAULTS[key])

    return cfg


if __name__ == "__main__":
    cfg = load_config()
    if len(sys.argv) >= 3 and sys.argv[1] == "--get":
        v = cfg.get(sys.argv[2], "")
        print(json.dumps(v) if isinstance(v, (list, dict)) else v)
    else:
        print(json.dumps(cfg, indent=2, ensure_ascii=False))
