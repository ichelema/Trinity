#!/usr/bin/env bash
# Elenca i modelli configurati in claude-code-router e le route attuali.
# Invocato da commands/ccr_model.md come comando !-embedded (singolo, così la
# allow-rule Bash(bash …/ccr-models.sh) viene rispettata dal gate degli slash command).
cat /c/msys64/home/EN27553/.claude-code-router/config.json | jq -r '
  "📋 Modelli disponibili:",
  (.Providers[] | .name as $p | .models[] | "  /model \($p),\(.)"),
  "",
  "🔀 Route attuali:",
  (.Router | to_entries[]
     | select(.key|test("Threshold")|not)
     | "  \(.key): \(.value)")
'
