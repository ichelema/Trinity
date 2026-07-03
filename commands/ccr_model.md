---
description: Elenca i modelli configurati in ccr e le route attuali
allowed-tools: Bash(bash:*)
---
Esegui col tuo Bash tool il comando seguente e mostra il suo output
esattamente com'è (è un elenco di righe `/model provider,model` e le route
ccr). Poi aggiungi una riga finale: «Per switchare a caldo (senza riavvio)
incolla nel prompt una delle righe `/model provider,model`.»

```bash
bash "$TRINITY_PLUGIN_DIR/scripts/ccr-models.sh"
```
