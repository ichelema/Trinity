---
description: Elenca i modelli configurati in ccr e le route attuali
allowed-tools: Bash(cat:*)
---
Esegui il comando bash qui sotto col tuo Bash tool e mostra il suo output
esattamente com'è. Poi aggiungi una riga finale: «Per switchare a caldo
(senza riavvio) incolla nel prompt una delle righe `/model provider,model`.»

```bash
cat /c/msys64/home/EN27553/.claude-code-router/config.json | jq -r '
  "📋 Modelli disponibili:",
  (.Providers[] | .name as $p | .models[] | "  /model \($p),\(.)"),
  "",
  "🔀 Route attuali:",
  (.Router | to_entries[]
     | select(.key|test("Threshold")|not)
     | "  \(.key): \(.value)")
'
```
