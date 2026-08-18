---
description: Prende in carico una issue Linear e la implementa nel worktree creato allo step 1, fino alla PR (senza merge)
argument-hint: <issue-id> <model>
arguments:
  - issue_id
  - model
disable-model-invocation: true
---

Prendi in carico la issue Linear `$issue_id` e implementala nel worktree già
creato da `/1_create-worktree` per il modello `$model`.

Il worktree e il branch esistono già: **non crearli, non ricrearli, non fare
checkout nel repository principale**.

`$model` qui serve solo a identificare il worktree corretto, non a scegliere il
modello di esecuzione.

## Validazione degli argomenti

Verifica che siano presenti tutti gli argomenti:

- issue ID: `$issue_id`
- modello: `$model`

Se ne manca uno, fermati e mostra:

`/2_work-issue <issue-id> <model>`

## Localizzazione del worktree

Non ricostruire il prefisso (`bug` / `improvements`) a partire dalla issue: è
già stato deciso allo step 1 e potrebbe essere stato scelto dall'utente.
Ricava il worktree dallo stato reale di Git:

```bash
git worktree list --porcelain
```

Cerca l'entry il cui branch termina esattamente con `/$issue_id-$model`
(es. `improvements/ICH-72-claude-opus-4.1`). Il suffisso esatto è ciò che
distingue il worktree di implementazione da quello di review, che termina con
`/$issue_id-review-$model`.

Da quella entry ricava:

- `<wt-path>`: la riga `worktree ...`, da usare poi ESATTAMENTE come stampata;
- `<branch>`: la riga `branch refs/heads/...`.

Se non esiste nessuna entry corrispondente, fermati e mostra:

`/1_create-worktree <source-branch> $issue_id $model`

Non cercare worktree simili, non riutilizzare un worktree di review, non
lavorare nel repository principale.

### Tutti i comandi vanno eseguiti sul worktree

Usa `git -C "<wt-path>"` per ogni comando Git e path assoluti sotto `<wt-path>`
per ogni lettura o modifica di file. Non fare `cd` nel worktree: su
Windows la directory diventa poi non cancellabile finché la sessione la tiene
come cwd (`Device or resource busy` allo step 5).

Verifica prima di iniziare:

```bash
git -C "<wt-path>" rev-parse --abbrev-ref HEAD   # deve essere <branch>
git -C "<wt-path>" status --short                # deve essere vuoto
```

Se il working tree non è pulito, fermati ed elenca i file modificati. Le opzioni
sono: committare, mettere da parte con `git stash`, oppure annullare. Non
decidere da solo e non eseguire mai `git checkout .`, `git reset --hard` o
`git stash` senza risposta: quel lavoro non versionato può essere l'unica copia
esistente.

## Recupero della issue

Recupera `$issue_id` con `get_issue`, passando `includeRelations: true`.

Leggi:

- identificativo e titolo;
- descrizione e acceptance criteria;
- commenti rilevanti per l'implementazione (`list_comments`);
- relazioni e relazioni parent/sub-issue;
- `statusType` corrente.

### Dipendenze

`get_issue` restituisce le relazioni **solo** con `includeRelations: true`.
Senza quel flag il campo `relations` non compare affatto, e una issue con dei
blocker è indistinguibile da una libera: è un falso negativo silenzioso, non un
errore.

Se la issue è bloccata da una o più issue non completate:

1. NON iniziare l'implementazione.
2. Mostra quali issue la stanno bloccando e il loro stato.
3. Attendi una decisione esplicita dell'utente prima di procedere comunque.

Un blocco non è un divieto: l'utente può avere ragioni per procedere lo stesso —
il lavoro bloccante è quasi finito, o la parte da fare non dipende davvero da
quella. Il compito qui è rendere quella decisione informata, non prenderla.

## Segnalare l'inizio del lavoro

Il branch creato allo step 1 è `<prefix>/$issue_id-$model`, **non** il
`gitBranchName` fornito da Linear: il collegamento automatico branch → issue
non scatta. Per tutta l'implementazione la board non mostra nulla, a meno che
non lo segnali tu.

Una volta sola, prima di iniziare a modificare file:

- se lo `statusType` della issue è `backlog` o `unstarted`, portala a
  **In Progress** con `save_issue`;
- se è già `started`, non toccarla: qualcuno ci sta già lavorando, oppure
  l'automazione è già intervenuta.

Da qui in poi non aggiornare più lo stato a mano. Dall'apertura della PR in poi
subentra l'automazione GitHub → Linear:

| Evento | Stato risultante |
| --- | --- |
| PR aperta | In Progress |
| PR pronta per il merge (check verdi, nessun conflitto) | In Review |
| PR mergiata | Done |

Queste transizioni arrivano via webhook in pochi secondi. Una `save_issue` sugli
stessi stati è nel migliore dei casi ridondante, nel peggiore sovrascrive una
transizione appena avvenuta.

## Piano prima dell'implementazione

Prima di modificare qualsiasi file mostra:

- issue: `$issue_id` — titolo;
- branch e percorso del worktree;
- requisiti estratti dalla issue, come checklist verificabile;
- breve piano di implementazione (file coinvolti e modifiche previste);
- comandi di test che intendi eseguire.

Mostra il piano **in italiano**, anche quando la issue è scritta in inglese: il
piano è output a schermo per l'utente, non contenuto destinato a Linear o al
repository. Restano in inglese soltanto i messaggi di commit e il titolo e la
descrizione della PR. Cita pure i termini tecnici e le stringhe della issue
nella loro forma originale.

Se trovi specifiche contrastanti o hai dei dubbi che potrebbero compromettere la implementazione fermati e chiedi 
maggiori dettagli all'utente, solo quando le specifiche sono completamente chiare passa alla implementazione.

Mostra il piano ben definito ordinato chiaro non usare tecnicismi, se utile fai uso di bullet point e sottosessioni e tabelle.

Attendi l'ok dell'utente sul piano prima di scrivere codice.

## Implementazione

Obiettivo, lavorare sulla issue `$issue_id`. 

Sei il lead. 

Delega il ragionamento a trinity:deep-reasoner, il lavoro ingrato a trinity:fast-worker, i problemi con prospettiva fresca a DeepSeek. 

Mantieni tutte le modifiche entro lo scope di `$issue_id`. 
Ogni riga modificata deve essere riconducibile a un requisito della issue: le deviazioni vanno
segnalate all'utente, non incluse in silenzio.

Sono consentiti più commit quando rappresentano modifiche logiche distinte. 

Imessaggi di commit vanno scritti in inglese.

Quando l'implementazione è terminata:

1. Esegui i test e i controlli rilevanti (`mise run <task>` se il progetto li
   definisce), dal worktree.
2. Verifica che ogni requisito della checklist sia coperto.
3. Crea i commit mancanti: `git -C "<wt-path>" add ...` e
   `git -C "<wt-path>" commit -m "..."`.
4. Esegui il push: `git -C "<wt-path>" push -u origin "<branch>"`.

Se i test falliscono, mostra l'output completo dell'errore prima di tentare un
fix. Non aprire la PR con i test rossi senza dirlo esplicitamente.

## Prima di scrivere il codice

Scorri questa lista in ordine. Fermati alla prima riga che corrisponde alla tua situazione.

1. È davvero necessario? Se no, non implementarlo.
2. Questo repository lo contiene già? Riutilizza la funzione di supporto.
3. La libreria standard lo fa? Usala.
4. La piattaforma lo fa nativamente? Usala.
5. Una dipendenza installata lo fa? Usala.
6. Si può scrivere in una sola riga? Scrivi una sola riga.
7. Altrimenti, scrivi il minimo indispensabile che funzioni.

Non prendere mai una scorciatoia quando si tratta di: leggere il codice prima di modificarlo, convalidare
gli input che superano un confine di fiducia, gestire gli errori che altrimenti causerebbero la perdita
di dati, garantire la sicurezza, l'accessibilità o qualsiasi altra cosa io abbia specificato espressamente.

Non aggiungere un'astrazione che non ho richiesto. Non aggiungere una dipendenza strettamente necessaria.

 È preferibile eliminare codice piuttosto che aggiungerne.

## Pull Request

Determina il branch di default senza dipendere da `gh`, che nella shell di
Claude può non essere loggato:

```bash
git symbolic-ref -q --short refs/remotes/origin/HEAD || git remote show origin | sed -n 's/.*HEAD branch: /origin\//p'
```

Crea una sola PR verso il branch di default, senza `cd` nel worktree:

```bash
gh repo view --json nameWithOwner -q .nameWithOwner
gh pr create -R "<owner/repo>" --base "<default>" --head "<branch>" --title "..." --body "..."
```

### Magic words

Poiché il branch non contiene l'ID nel formato riconosciuto da Linear, il
collegamento PR → issue dipende interamente dalle magic words nel titolo o nel
corpo. Senza, la PR resta scollegata e nessuna transizione di stato avviene.

**Per chiudere** la issue al merge: `close` / `closes` / `fix` / `fixes` /
`resolve` / `resolves` / `complete` / `completes` / `implement` / `implements`
(anche nelle forme `-d` e `-ing`).

    Fixes $issue_id

**Per collegare senza chiudere** — issue correlate, parent, contesto:
`ref` / `refs` / `references` / `part of` / `related to` / `relates to` /
`contributes to` / `toward` / `towards`.

    Refs ICH-100

Usa la forma non-closing quando la PR contribuisce a una issue senza esaurirla:
la magic word sbagliata chiude lavoro ancora aperto, e riaprirlo a mano perde la
traccia dell'automazione. Non usare mai una magic word verso una issue già
chiusa: la riapre.

La PR deve contenere:

- riepilogo conciso;
- dettagli di implementazione importanti;
- test eseguiti;
- riferimento a `$issue_id`.

Titolo e descrizione della PR vanno sempre scritti in inglese: Linear usa il
titolo della PR come titolo dell'attachment agganciato alla issue, quindi
diventa testo del workspace a tutti gli effetti.

## Non fare il merge

Fermati qui. Il passo successivo è la review indipendente
(`/3_create-review-worktree <branch> $issue_id <model-reviewer>`), poi il merge
resta all'utente.

## Verifica finale

```bash
git -C "<wt-path>" status --short          # deve essere vuoto
git -C "<wt-path>" log --oneline "<default>".."<branch>"
```

Alla fine stampa esclusivamente questa tabella, sostituendo i segnaposto con i
valori effettivi, <model> è quello che ha eseguito il lavoro $model:

```
┌────────────────────────┬──────────────────────────────────────────────────────────┐
│         Campo          │                          Valore                          │
├────────────────────────┼──────────────────────────────────────────────────────────┤
│ Issue Linear           │ <issue-id> — <titolo-issue>                              │
├────────────────────────┼──────────────────────────────────────────────────────────┤
│ Stato Linear           │ <stato-precedente> → <stato-attuale> / invariato: <motivo>│
├────────────────────────┼──────────────────────────────────────────────────────────┤
│ Worktree               │ <wt-path>                                                │
├────────────────────────┼──────────────────────────────────────────────────────────┤
│ Branch                 │ <branch> (pushato: sì/no)                                │
├────────────────────────┼──────────────────────────────────────────────────────────┤
│ Commit                 │ <n> commit — <elenco sintetico>                          │
├────────────────────────┼──────────────────────────────────────────────────────────┤
│ Requisiti coperti      │ <n>/<tot> — <eventuali scoperti>                         │
├────────────────────────┼──────────────────────────────────────────────────────────┤
│ Test                   │ <comando> — <esito>                                      │
├────────────────────────┼──────────────────────────────────────────────────────────┤
│ Pull Request           │ <url> (magic word: <Fixes/Refs> <issue-id>)              │
├────────────────────────┼──────────────────────────────────────────────────────────┤
│ Prossimo passo         │ /3_create-review-worktree <branch> <issue-id> <$model>   │
└────────────────────────┴──────────────────────────────────────────────────────────┘
```

Adatta la larghezza della colonna Valore al contenuto effettivo.
