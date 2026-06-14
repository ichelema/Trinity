---
description: Elenca i modelli configurati in ccr e le route attuali
allowed-tools: Bash(jq:*)
---
Modelli configurati in ccr (config.json) e route attive.
Per switchare a caldo copia una riga `/model …` qui sotto e incollala nel prompt.

!`jq -r '
  "📋 Modelli disponibili:",
  (.Providers[] | .name as $p | .models[] | "  /model \($p),\(.)"),
  "",
  "🔀 Route attuali:",
  (.Router | to_entries[]
     | select(.key|test("Threshold")|not)
     | "  \(.key): \(.value)")
' /c/msys64/home/EN27553/.claude-code-router/config.json`
