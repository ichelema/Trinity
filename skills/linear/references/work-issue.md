# Lavorare su una o più Issue

Usa questo workflow quando l'utente vuole implementare una o più issue Linear.

## Recupero delle issue

Recupera ogni issue richiesta con `get_issue` (o `list_issues` se l'utente le
descrive invece di nominarle).

Leggi:

- identificativo
- titolo
- descrizione
- commenti rilevanti per l'implementazione (`list_comments`)
- relazioni
- relazioni parent/sub-issue
- `gitBranchName`, quando disponibile

Se vengono indicate più issue:

- considera la prima issue come issue principale
- usa un solo branch
- implementa tutte le issue richieste nello stesso branch
- crea una sola Pull Request

Più branch per un lavoro unitario producono PR che si sovrappongono e vanno
riconciliate a mano: è la ragione per cui qui si tiene tutto insieme.

## Dipendenze

Prima di iniziare qualsiasi issue:

1. Recuperare le relazioni `blocked by` tramite Linear MCP.
2. Se una issue è bloccata da una o più issue non completate, NON iniziare
   l'implementazione.
3. Mostrare quali issue la stanno bloccando e il loro stato.
4. Attendere una decisione esplicita dell'utente prima di procedere comunque.

`get_issue` restituisce le relazioni **solo** se lo chiami con
`includeRelations: true`. Senza quel flag il campo `relations` non compare
affatto, e una issue con dei blocker è indistinguibile da una libera: è un
falso negativo silenzioso, non un errore.

Un blocco non è un divieto: l'utente può avere ragioni per procedere lo stesso —
il lavoro bloccante è quasi finito, o la parte da fare non dipende davvero da
quella. Per questo la decisione resta sua, e il compito della skill è renderla
informata invece di scoprire a metà implementazione che mancava un pezzo.

## Preparazione Git

Prima di modificare il codice:

1. Verifica che il working tree sia pulito (`git status --short`).
2. Passa al branch di default del repository.
3. Esegui il pull delle ultime modifiche remote.
4. Determina il branch name Linear della issue principale (campo `gitBranchName`).
5. Usa esattamente il branch name fornito da Linear, quando disponibile.
6. Crea e passa a quel branch.
7. Segnala su Linear che il lavoro è iniziato (vedi sotto).

### Segnalare l'inizio del lavoro

Creare il branch non cambia nulla su Linear: l'automazione GitHub si attiva
solo dall'apertura della PR in poi. Nella finestra fra il branch e la PR — cioè
per tutta l'implementazione — la issue resterebbe in Backlog o Todo, e chi
guarda la board non vede che ci stai lavorando.

Colma tu quella finestra, una volta sola, subito dopo aver creato il branch:

- Se lo `statusType` della issue principale è `backlog` o `unstarted`,
  portala a **In Progress** con `save_issue`.
- Se è già `started`, non toccarla: qualcuno ci sta già lavorando, oppure
  l'automazione è già intervenuta.

Da qui in poi non aggiornare più lo stato a mano. Il resto è automatico:

| Evento | Stato risultante |
| --- | --- |
| PR aperta | In Progress |
| PR pronta per il merge (check verdi, nessun conflitto) | In Review |
| PR mergiata | Done |

Queste transizioni arrivano via webhook in pochi secondi. Una `save_issue`
sugli stessi stati è nel migliore dei casi ridondante, nel peggiore
sovrascrive una transizione appena avvenuta.

### Se il working tree non è pulito

Fermati e chiedi all'utente come procedere, elencando i file modificati.
Le opzioni sono: committare le modifiche, metterle da parte con `git stash`,
oppure annullare il workflow.

Non decidere da solo e non eseguire mai `git checkout .`, `git reset --hard` o
`git stash` senza risposta: quel lavoro non versionato può essere l'unica copia
esistente, e nessuna issue vale la sua perdita.

### Branch di default

Non assumere `master` né `main`. Rilevalo:

```bash
gh repo view --json defaultBranchRef -q .defaultBranchRef.name
```

Questa skill è disponibile in tutti i progetti, e i repository non concordano
sul nome del branch principale.

### Perché il branch name di Linear conta

Linear riconosce le proprie issue dal nome del branch e collega
automaticamente branch, PR e issue, aggiornando lo stato lungo il percorso.
Un nome ricostruito a mano, anche se simile, rompe quel collegamento: il lavoro
prosegue ma su Linear non risulta nulla.

Se Linear non fornisce un `gitBranchName`, costruiscilo tu nello stesso formato
(`<utente>/<id-issue-minuscolo>-<titolo-in-kebab-case>`) mantenendo l'ID issue,
che è la parte da cui dipende il riconoscimento.

Prima dell'implementazione mostra:

- issue coinvolte
- issue principale
- branch
- breve piano di implementazione

## Implementazione

Mantieni tutte le modifiche entro lo scope delle issue richieste.

Sono consentiti più commit quando rappresentano modifiche logiche distinte.
I messaggi di commit vanno scritti in inglese, come il resto di ciò che resta
nel repository e su Linear.

Quando l'implementazione è terminata:

1. Esegui i test e i controlli rilevanti.
2. Verifica che tutte le issue richieste siano state coperte.
3. Crea eventuali commit mancanti.
4. Esegui il push del branch sul repository remoto.
5. Crea una sola Pull Request verso il branch di default.

## Pull Request

La PR deve fare riferimento a tutte le issue Linear coinvolte, tramite le
magic words che Linear riconosce nel titolo e nella descrizione.

**Per chiudere** una issue quando la PR viene mergiata:
`close` / `closes` / `fix` / `fixes` / `resolve` / `resolves` /
`complete` / `completes` / `implement` / `implements` (anche nelle forme
`-d` e `-ing`).

    Fixes ICH-101
    Fixes ICH-102

**Per collegare senza chiudere** — issue correlate, parent, contesto:
`ref` / `refs` / `references` / `part of` / `related to` / `relates to` /
`contributes to` / `toward` / `towards`.

    Refs ICH-100

Usa la forma non-closing quando la PR contribuisce a una issue senza esaurirla:
la magic word sbagliata chiude lavoro ancora aperto, e riaprirlo a mano perde
la traccia dell'automazione.

La Pull Request deve contenere:

- riepilogo conciso
- dettagli di implementazione importanti
- test eseguiti
- riferimenti alle issue Linear

Titolo e descrizione della Pull Request devono essere sempre in inglese, come i
commenti aggiunti alle issue Linear durante il lavoro. Il titolo conta quanto il
corpo: Linear lo usa come titolo dell'attachment che aggancia alla issue, quindi
finisce dentro il workspace esattamente come una description.

Dopo aver creato la PR mostra:

- URL della PR
- issue Linear collegate
- risultato dei test
- breve riepilogo

## Non fare il merge

Fermati qui e attendi l'approvazione esplicita dell'utente.

La revisione umana è il punto di controllo di questo workflow: una PR mergiata
è già entrata nella storia del branch di default, mentre una PR aperta si
corregge senza costo. Per il merge vedi `merge-pr.md`.
