---
description: Riflessione strategica sulla memoria persistente Hindsight del progetto
---

# Reflect

Esegui una riflessione strategica usando la memoria persistente Hindsight MCP del progetto.

## Uso

Quando viene invocato questo comando, usa il testo fornito dall’utente come query di reflect.

Se l’utente non fornisce una query specifica, usa questa query predefinita:

```text
Quali pattern, decisioni architetturali, rischi, vincoli o lezioni precedenti sono rilevanti per il lavoro corrente?
```

## Istruzioni operative

1. Usa il tool MCP Hindsight `reflect`.
2. Endpoint del progetto:

```text
http://localhost:8888/mcp/trinity-project/
```

3. Usa questi parametri:

```text
budget: high
max_tokens: 4096
tags: claude-code, project:trinity-project
tags_match: any
```

4. Tratta il risultato come memoria consultiva, non come fonte di verità.
5. Verifica sempre fatti mutabili nel repository.
6. Dopo la riflessione, sintetizza:
   - insight rilevanti
   - decisioni precedenti da rispettare
   - rischi
   - prossime azioni consigliate

## Fallback

Se il tool MCP `reflect` non è disponibile, esegui lo script locale:

```bash
"${CLAUDE_PLUGIN_ROOT}/hooks/hindsight/ops/hindsight-reflect.sh" "$ARGUMENTS"
```

Usa l’output dello script come contesto per rispondere.

## Sicurezza

Non salvare o mostrare:

- API key
- password
- token
- segreti
- dati personali sensibili non richiesti

La memoria Hindsight non sostituisce repository, test, documentazione, configurazioni e file correnti.
