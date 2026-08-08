# Elencare e Riepilogare le Issue

Usa questo workflow quando l'utente chiede di elencare, consultare, cercare,
filtrare o riepilogare issue Linear.

Usa `list_issues` per recuperare i dati correnti, o `get_issue` quando l'utente
nomina una singola issue.

Non modificare alcuna issue: qui l'utente sta guardando, non decidendo.

Applica i filtri con i parametri nativi di `list_issues` invece di scaricare
tutto e filtrare a valle — il filtro lato server è più veloce e non tronca
risultati rilevanti oltre il `limit`:

| Filtro | Parametro |
| --- | --- |
| Progetto | `project` |
| Stato | `state` |
| Priorità | `priority` |
| Label | `label` |
| Parent issue | `parentId` |
| Assegnatario | `assignee` (`"me"` per l'utente corrente) |
| Testo libero | `query` |

Chiedi con `fields` solo le colonne che mostrerai: la risposta completa di una
issue include la descrizione integrale, che qui non serve e occupa contesto.

Se non viene specificato alcun filtro, mostra le issue attive.

Per ogni issue mostra:

- ID
- titolo
- project
- status
- priority
- labels
- parent issue, se presente
- breve riepilogo in una sola frase

Preferisci il raggruppamento per stato:

1. In Progress
2. In Review
3. Todo
4. Backlog
5. Done

Escludi le issue Done per impostazione predefinita quando l'utente chiede il lavoro attivo.

Non mostrare descrizioni lunghe salvo richiesta esplicita.

Puoi riepilogare in italiano per l'utente, anche se la descrizione originale della issue è in inglese.
