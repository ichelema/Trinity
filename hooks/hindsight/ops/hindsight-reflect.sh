#!/usr/bin/env bash
# Script utility (NON hook): invoca reflect per ottenere sintesi strategica dalle memorie.
# Uso: bash hindsight-reflect.sh "domanda strategica"
# Default query se omessa.
set -euo pipefail

# Config centralizzata in hindsight.config.json (vedi hindsight_config.py).
HOOKS_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
QUERY="${*:-What strategic project memory is relevant now?}"

export HOOKS_DIR QUERY

PYTHONUTF8=1 python <<'PY'
import json, os, sys, urllib.request

sys.path.insert(0, os.path.join(os.environ["HOOKS_DIR"], "..", "lib"))
from hindsight_config import load_config

cfg = load_config()

payload = {
    "query": os.environ["QUERY"],
    "context": "Claude Code project-level reflection",
    "budget": cfg["reflect_budget"],
    "max_tokens": cfg["reflect_max_tokens"],
    "tags": cfg["recall_tags"],
    "tags_match": cfg["recall_tags_match"],
}

req = urllib.request.Request(
    cfg["api_url"] + "/reflect",
    data=json.dumps(payload).encode("utf-8"),
    headers={"Content-Type": "application/json"},
    method="POST",
)

with urllib.request.urlopen(req, timeout=60) as res:
    body = json.loads(res.read().decode("utf-8", errors="replace"))

# Output pulito invece del JSON envelope grezzo.
text = body.get("text") if isinstance(body, dict) else None
if text:
    print(text)
else:
    print(json.dumps(body, indent=2, ensure_ascii=False))
PY
