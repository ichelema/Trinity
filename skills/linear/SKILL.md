---
name: linear
description: Gestisce issue Linear e workflow di sviluppo tramite il server MCP di Linear.
---

# Linear

Usa il server MCP di Linear come fonte di verità per issue, progetti,
stati, priorità, label, relazioni e metadati delle issue.

Linear è un sistema vivo: stati, label e assegnatari cambiano fuori da questa
sessione, e un workspace ha i propri valori configurati. Un valore ricordato o
plausibile è quindi quasi sempre un valore sbagliato — per questo ogni workflow
parte da una lettura via MCP, non da un'assunzione.

Determina l'intento dell'utente e carica solo il riferimento pertinente:

- Creazione di una issue → `references/create-issue.md`
- Elenco, ricerca o riepilogo di issue → `references/list-issues.md`
- Lavoro su una o più issue → `references/work-issue.md`
- Merge di una PR dopo la revisione dell'utente → `references/merge-pr.md`

## Tool MCP disponibili

| Serve | Tool |
| --- | --- |
| Leggere una issue specifica | `get_issue` |
| Cercare, filtrare, elencare issue | `list_issues` |
| Creare **e** aggiornare una issue | `save_issue` |
| Valori validi del workspace | `list_projects`, `list_issue_statuses`, `list_issue_labels`, `list_teams`, `list_users` |
| Commenti | `list_comments`, `save_comment` |

`save_issue` fa sia create che update: passa un `id` esistente per aggiornare,
omettilo per creare. Non cercare un `create_issue`, non esiste.

## Regole generali

- Recupera sempre i dati correnti da Linear tramite MCP prima di agire.
- Non inventare mai ID issue, progetti, stati, label, priorità o relazioni.
  Un ID inventato non fallisce in modo rumoroso: crea silenziosamente un
  collegamento sbagliato o nessun collegamento.
- Quando un valore richiesto è ambiguo, controlla prima i valori disponibili in Linear.
- Non modificare Linear quando l'utente chiede solo di consultare, elencare o
  riepilogare informazioni. Una lettura che scrive è un effetto collaterale che
  l'utente non ha chiesto e non si aspetta di dover controllare.
- Mantieni le risposte concise e strutturate.

## Lingua

Il contenuto che finisce **dentro** Linear — campi `description` e commenti — va
sempre scritto in inglese, anche quando l'utente scrive in italiano: le issue
sono lette da altri e restano nel tempo, quindi la lingua del workspace prevale
su quella della conversazione.

La conversazione con l'utente resta in italiano: riepiloghi, domande e output a
schermo non seguono questa regola.
