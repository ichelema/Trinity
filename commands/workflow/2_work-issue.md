---
description:
  Prende in carico una o più issue Linear e le implementa nel worktree creato allo step 1, fino alla
  PR (senza merge); con auto, dopo l'ok al piano prosegue da solo fino alla review
argument-hint: <issue-id...> <model> [auto [review|loop]]
disable-model-invocation: true
---

Prendi in carico le issue Linear indicate e implementale nel worktree già creato da
`/1_create-worktree`.

Il worktree e il branch esistono già: **non crearli, non ricrearli, non fare checkout nel repository
principale**.

Il modello qui serve solo a identificare il worktree corretto, non a scegliere il modello di
esecuzione.

## Validazione degli argomenti

Dividi `$ARGUMENTS` in token separati da spazi (maiuscole o minuscole non contano per le parole
chiave):

- se gli ultimi due token sono `auto` e poi `review` o `loop`, toglili: `<mode>` è `auto` e
  `<review-mode>` è l'ultimo dei due;
- altrimenti, se l'ultimo token è `auto`, toglilo: `<mode>` è `auto` e `<review-mode>` è `loop`;
- senza queste parole chiave `<mode>` è manuale.

Dei token restanti l'ultimo è il modello e i precedenti sono gli issue ID (almeno uno). Se restano
meno di 2 token, fermati e mostra:

`/trinity:workflow:2_work-issue <issue-id...> <model> [auto [review|loop]]`

## Localizzazione del worktree

Non ricostruire il prefisso (`bug` / `improvments`) a partire dalla issue: è già stato deciso allo
step 1 e potrebbe essere stato scelto dall'utente. Ricava il worktree dallo stato reale di Git:

```bash
git worktree list --porcelain
```

Cerca l'entry il cui branch termina esattamente con `/<base-name>`, dove `<base-name>` segue la
regola dello step 1: una sola issue → `<issue-id>-<model>` (es. `improvments/ICH-72-fable`); più
issue → prefisso team una sola volta, poi i numeri delle successive, infine il modello (es.
`ICH-97` + `ICH-98` + `fable` → `improvments/ICH-97-98-fable`). Il match sul branch esclude da solo
i worktree di review di `/4_review-fix-loop`: sono detached e non hanno una riga `branch`.

Da quella entry ricava:

- `<wt-path>`: la riga `worktree ...`, da usare poi ESATTAMENTE come stampata;
- `<branch>`: la riga `branch refs/heads/...`.

Se non esiste nessuna entry corrispondente, fermati e mostra:

`/trinity:workflow:1_create-worktree <source-branch> <issue-id...> <model>`

Non cercare worktree simili, non riutilizzare un worktree di review, non lavorare nel repository
principale.

### Entrata persistente nel worktree esistente

Verifica **prima di entrare** nel worktree:

```bash
git -C "<wt-path>" rev-parse --abbrev-ref HEAD   # deve essere <branch>
git -C "<wt-path>" status --short                # deve essere vuoto
```

Se il working tree non è pulito, fermati ed elenca i file modificati. Le opzioni sono: committare,
mettere da parte con `git stash`, oppure annullare. Non decidere da solo e non eseguire mai
`git checkout .`, `git reset --hard` o `git stash` senza risposta: quel lavoro non versionato può
essere l'unica copia esistente.

Solo dopo questi controlli, usa lo strumento **nativo** `EnterWorktree` con
`path: "<wt-path>"` (percorso esatto ricavato da `git worktree list --porcelain`). Passa `path`,
**mai `name`**: devi entrare nel worktree esistente, senza crearne uno nuovo e senza cambiare branch.
Se il percorso è fuori da `.claude/worktrees/`, Claude Code può chiedere l'autorizzazione a
entrare: richiedila prima di presentare il piano, anche in modo `auto`.

`EnterWorktree` sposta la directory di lavoro **della sessione Claude Code**, non soltanto quella di
una singola chiamata Bash: gli strumenti di lettura/modifica e la configurazione del progetto
seguono il worktree. Non sostituirlo con un semplice `cd`: fuori dalle directory autorizzate il
cambio di directory Bash può essere annullato, e non garantisce lo stesso isolamento.

Dopo l'ingresso, verifica con una chiamata Bash separata che `pwd -P` e
`git rev-parse --show-toplevel` identifichino il worktree previsto, non il checkout principale.
Se non coincidono, non modificare file: segnala l'errore.

Se `EnterWorktree`/`ExitWorktree` non sono disponibili (per esempio per
`permissions.blockWritesOutsideWorkingDirectories`) o l'ingresso viene negato, **fermati**:
non proseguire fingendo di essere nel worktree e non crearne un altro. Indica come alternativa
l'avvio di una nuova sessione Claude Code direttamente dalla directory `<wt-path>`; in quel caso
l'uscita automatica con `ExitWorktree` non è disponibile, perché la sessione non è entrata con
`EnterWorktree`.

### Permanenza e uscita

**Rimani nel worktree per tutta la lavorazione.** In particolare, NON eseguire `ExitWorktree` quando:

- mostri il piano e attendi l'ok, anche in modo `auto`;
- poni una domanda o attendi una decisione su specifiche o dipendenze;
- deleghi esplorazione, implementazione, test o review.

I subagent devono ricevere esplicitamente `<wt-path>` e operare sui file di quel worktree, senza
creare worktree alternativi per l'implementazione di queste issue. Per ogni comando Git usa
`git -C "<wt-path>"`; per letture e modifiche mantieni i path nel worktree. Il controllo del
percorso è una difesa aggiuntiva, non un sostituto di `EnterWorktree`.

**Esci una sola volta** quando la fase è davvero conclusa (o quando il lavoro viene
interrotto definitivamente), dopo aver fermato i processi in background avviati nel worktree e
completato i controlli previsti. Usa `ExitWorktree` con `action: "keep"`: torna alla directory
originaria conservando `<wt-path>`, branch e commit. **Mai `action: "remove"`**: l'eventuale
rimozione del worktree spetta solo allo step dedicato del workflow.

In modalità manuale esci dopo la verifica finale della PR. In modalità `auto` non uscire dopo
la sola PR: resta nel worktree durante gli step successivi che vi lavorano, poi esci al termine
della catena, **prima** di un eventuale step che rimuova fisicamente il worktree. Se uno step
successivo prevede già l'uscita, non ripeterla.

Non tentare di ripristinare la directory principale con `cd` o con operazioni Git: l'uscita
dalla sessione-worktree è responsabilità di `ExitWorktree`. Questo evita anche di lasciare il
worktree come cwd di una shell su Windows, che può impedirne la rimozione.

## Recupero delle issue

Recupera ogni issue con `${CLAUDE_PLUGIN_ROOT}/skills/linear/scripts/linear.py query`, selezionando
il campo `relations`.

Leggi:

- identificativo e titolo;
- descrizione e acceptance criteria;
- commenti rilevanti per l'implementazione (campo `comments`);
- relazioni e relazioni parent/sub-issue (campo `relations`);
- lo stato corrente (campo `state { type }`).

### Dipendenze

La query deve selezionare esplicitamente il campo `relations`: senza, il campo non compare affatto,
e una issue con dei blocker è indistinguibile da una libera: è un falso negativo silenzioso, non un
errore.

Se una delle issue è bloccata da una o più issue non completate:

1. NON iniziare l'implementazione.
2. Mostra quali issue la stanno bloccando e il loro stato.
3. Attendi una decisione esplicita dell'utente prima di procedere comunque.

Un blocco non è un divieto: l'utente può avere ragioni per procedere lo stesso — il lavoro bloccante
è quasi finito, o la parte da fare non dipende davvero da quella. Il compito qui è rendere quella
decisione informata, non prenderla.

## Segnalare l'inizio del lavoro

Il branch creato allo step 1 è `<prefix>/<base-name>`, **non** il `gitBranchName` fornito da Linear:
il collegamento automatico branch → issue non scatta. Per tutta l'implementazione la board non
mostra nulla, a meno che non lo segnali tu.

Una volta sola, prima di iniziare a modificare file:

- per ogni issue: se lo stato (`state { type }`) è `backlog` o `unstarted`, portala a **In
  Progress** con `issueUpdate`;
- se è già `started`, non toccarla: qualcuno ci sta già lavorando, oppure l'automazione è già
  intervenuta.

Da qui in poi non aggiornare più lo stato a mano. Dall'apertura della PR in poi subentra
l'automazione GitHub → Linear:

| Evento                                                 | Stato risultante |
| ------------------------------------------------------ | ---------------- |
| PR aperta                                              | In Progress      |
| PR pronta per il merge (check verdi, nessun conflitto) | In Review        |
| PR mergiata                                            | Done             |

Queste transizioni arrivano via webhook in pochi secondi. Una `issueUpdate` sugli stessi stati è nel
migliore dei casi ridondante, nel peggiore sovrascrive una transizione appena avvenuta.

## Piano prima dell'implementazione

Se il codice coinvolto non ti è familiare e prevedi di leggere più di 3 file che non hai già letto,
delega l'esplorazione a `trinity:scoper`. Nel prompt passagli titolo, descrizione, criteri di
accettazione e commenti rilevanti delle issue, e il percorso del worktree. Il suo report è un input,
non una decisione: verifica a campione i file che indica. Se il report segnala il task come
complesso, leggi tu i file chiave prima di scrivere il piano.

Prima di modificare qualsiasi file mostra:

- le issue: ID e titolo, una per riga;
- branch e percorso del worktree;
- requisiti estratti dalla issue, come checklist verificabile;
- breve piano di implementazione (file coinvolti e modifiche previste);
- comandi di test che intendi eseguire.

Mostra il piano **in italiano**, anche quando la issue è scritta in inglese: il piano è output a
schermo per l'utente, non contenuto destinato a Linear o al repository. Messaggi di commit, titolo
e descrizione della PR seguono la lingua del progetto Linear (sezione "Lingua" della skill
`linear`). Cita pure i termini tecnici e le stringhe della issue nella loro forma originale.

Se trovi specifiche contrastanti o hai dei dubbi che potrebbero compromettere la implementazione
fermati e chiedi maggiori dettagli all'utente, solo quando le specifiche sono completamente chiare
passa alla implementazione.

Mostra il piano ben definito ordinato chiaro non usare tecnicismi, se utile fai uso di bullet point
e sottosessioni e tabelle.

Attendi l'ok dell'utente sul piano prima di scrivere codice.

In modo `auto` aggiungi al piano la catena che seguirà dopo la PR (sezione «Modo auto») e la
modalità di review: dopo l'ok non farai altre domande.

## Implementazione

Obiettivo: implementare tutte le issue indicate.

Sei il lead.

Delega il ragionamento a trinity:deep-reasoner, l'implementazione già definita a trinity:fast-worker (se la
sessione è già Sonnet, fallo tu: fast-worker è lo stesso modello).
Il lavoro ripetitivo in volume con una regola esatta va a trinity:bulk-worker.
Per una decisione di design con trade-off reali, chiedi lo stesso quesito anche a gpt-bridge:deep-reasoner
(GPT via LiteLLM, se disponibile) e confronta le due conclusioni prima di scegliere.

Mantieni tutte le modifiche entro lo scope delle issue. Ogni riga modificata deve essere
riconducibile a un requisito di una delle issue: le deviazioni vanno segnalate all'utente, non
incluse in silenzio.

Sono consentiti più commit quando rappresentano modifiche logiche distinte.

I messaggi di commit vanno scritti nella lingua del progetto Linear.

Quando l'implementazione è terminata:

1. Esegui i test e i controlli rilevanti sul worktree: `mise -C "<wt-path>" run <task>`
   se il progetto li definisce, altrimenti il comando di test con path assoluti sotto `<wt-path>`.
2. Verifica che ogni requisito della checklist sia coperto.
3. Controlla `git -C "<wt-path>" status --short --untracked-files=all`: se ci sono file non
   correlati alle issue, fermati e segnalali. Poi crea i commit mancanti aggiungendo i file per
   nome, mai con `git add -A` o `git add .`: `git -C "<wt-path>" add <file>...` e
   `git -C "<wt-path>" commit -m "..."`.
4. Esegui il push: `git -C "<wt-path>" push -u origin "<branch>"`.

Se i test falliscono, mostra l'output completo dell'errore prima di tentare un fix. Non aprire la PR
con i test rossi senza dirlo esplicitamente.

## Prima di scrivere il codice

Scorri questa lista in ordine. Fermati alla prima riga che corrisponde alla tua situazione.

1. È davvero necessario? Se no, non implementarlo.
2. Questo repository lo contiene già? Riutilizza la funzione di supporto.
3. La libreria standard lo fa? Usala.
4. La piattaforma lo fa nativamente? Usala.
5. Una dipendenza installata lo fa? Usala.
6. Si può scrivere in una sola riga? Scrivi una sola riga.
7. Altrimenti, scrivi il minimo indispensabile che funzioni.

Non prendere mai una scorciatoia quando si tratta di: leggere il codice prima di modificarlo,
convalidare gli input che superano un confine di fiducia, gestire gli errori che altrimenti
causerebbero la perdita di dati, garantire la sicurezza, l'accessibilità o qualsiasi altra cosa io
abbia specificato espressamente.

Non aggiungere un'astrazione che non ho richiesto. Non aggiungere una dipendenza non strettamente
necessaria.

È preferibile eliminare codice piuttosto che aggiungerne.

## Pull Request

Determina il branch di default senza dipendere da `gh`, che nella shell di Claude può non essere
loggato:

```bash
git -C "<wt-path>" symbolic-ref -q --short refs/remotes/origin/HEAD || git -C "<wt-path>" remote show origin | sed -n 's/.*HEAD branch: /origin\//p'
```

Crea una sola PR verso il branch di default. Se parti da un altro branch,
controlla il diff verso `<default>`: fermati se include lavoro fuori scope.
Per `gh pr create --base` usa il nome senza `origin/` (es. `master`):

```bash
gh repo view --json nameWithOwner -q .nameWithOwner
gh pr create -R "<owner/repo>" --base "<default senza origin/>" --head "<branch>" --title "..." --body "..."
```

### Magic words

Poiché il branch non contiene l'ID nel formato riconosciuto da Linear, il collegamento PR → issue
dipende interamente dalle magic words nel titolo o nel corpo. Senza, la PR resta scollegata e
nessuna transizione di stato avviene.

**Per chiudere** la issue al merge: `close` / `closes` / `fix` / `fixes` / `resolve` / `resolves` /
`complete` / `completes` / `implement` / `implements` (anche nelle forme `-d` e `-ing`).

    Fixes ICH-97
    Fixes ICH-98

Con più issue, una magic word per ogni issue, ciascuna sulla propria riga.

**Per collegare senza chiudere** — issue correlate, parent, contesto: `ref` / `refs` / `references`
/ `part of` / `related to` / `relates to` / `contributes to` / `toward` / `towards`.

    Refs ICH-100

Usa la forma non-closing quando la PR contribuisce a una issue senza esaurirla: la magic word
sbagliata chiude lavoro ancora aperto, e riaprirlo a mano perde la traccia dell'automazione. Non
usare mai una magic word verso una issue già chiusa: la riapre.

La PR deve contenere:

- riepilogo conciso;
- dettagli di implementazione importanti;
- test eseguiti;
- riferimento a ogni issue.

Titolo e descrizione della PR vanno scritti nella lingua del progetto Linear: Linear usa il titolo
della PR come titolo dell'attachment agganciato alla issue, quindi diventa testo del workspace a
tutti gli effetti.

## Non fare il merge

Fermati qui. Il passo successivo è `/trinity:workflow:2_work-simplify <issue-id...> <model>`: ogni
command della catena indica il proprio passo successivo, fino alla review
(`/trinity:workflow:3_independent-review` oppure `/trinity:workflow:4_review-fix-loop`). Il merge
resta all'utente.

In modo `auto` non ti fermi qui: dopo la «Verifica finale» prosegui con «Modo auto».
Il merge resta comunque all'utente.

## Verifica finale

```bash
git -C "<wt-path>" status --short          # deve essere vuoto
git -C "<wt-path>" log --oneline "<default>".."<branch>"
```

In modo manuale, ferma gli eventuali processi in background ed esci con
`ExitWorktree(action: "keep")` come indicato in «Permanenza e uscita». In modo `auto` **non uscire
qui**: prosegui nella catena e uscirai alla sua conclusione, prima di qualsiasi rimozione fisica
del worktree.

In modo `auto` la tabella si stampa solo alla fine di «Modo auto». Alla fine stampa
esclusivamente questa tabella, sostituendo i segnaposto con i valori effettivi; `<model>` è il
modello ricavato in «Validazione degli argomenti»:

```
┌────────────────────────┬──────────────────────────────────────────────────────────┐
│         Campo          │                          Valore                          │
├────────────────────────┼──────────────────────────────────────────────────────────┤
│ Issue Linear           │ <issue-id> — <titolo-issue> (una riga per issue)         │
├────────────────────────┼──────────────────────────────────────────────────────────┤
│ Pull Request           │ [#<numero>](<url>)                                       │
├────────────────────────┼──────────────────────────────────────────────────────────┤
│ Test                   │ <comando> — <esito>                                      │
├────────────────────────┼──────────────────────────────────────────────────────────┤
│ Prossimo passo         │ /trinity:workflow:2_work-simplify <issue-id...> <model>  │
└────────────────────────┴──────────────────────────────────────────────────────────┘
```

Aggiungi una riga, prima di «Prossimo passo», solo per queste anomalie:

- `Stato Linear`: lo stato è rimasto invariato, con il motivo;
- `Requisiti coperti`: non tutti, con `<n>/<tot>` e i requisiti scoperti;
- `Branch`: il push non è avvenuto, con il motivo.

Non mettere in tabella worktree, branch pushato, elenco dei commit e magic words. Il prossimo passo
è uno solo: ogni command della catena stampa il proprio passo successivo.

Nell'output scrivila come tabella markdown a due colonne (`| Campo | Valore |`), non con i caratteri
di disegno del riquadro: fuori da un blocco di codice il renderer unisce le righe `│` in un
paragrafo e le manda a capo. Il riquadro sopra indica solo campi e ordine. Con più issue, la cella
«Issue Linear» diventa una riga della tabella per ogni issue, e così la riga «Stato Linear» quando
c'è.

## Modo auto

Solo con `<mode>` = `auto`. Dopo l'ok al piano l'utente non è più davanti al PC: non fare altre
domande. Da lì in poi segui `${CLAUDE_PLUGIN_ROOT}/commands/issue-cycle.md`:

- le regole di «Esecuzione senza presidio» e del «Registro»: crea il registro subito dopo l'ok al
  piano, con intestazione `# 2_work-issue auto <review-mode> <model>`; «il ciclo della issue
  corrente» è questa catena;
- prima della review, «Proxy LiteLLM (solo `loop`)» e l'ultimo paragrafo di «Modello di
  implementazione»;
- dopo la «Verifica finale», nell'ordine, gli step 2b, 2c, 3 o 4 e 5 di «Ciclo per issue», con
  `<review-mode>` come modalità di review e tutti gli issue ID di questo command al posto di
  `<issue-id>`.

Non pubblicare il commento su Linear di `issue-cycle` e non fare mai il merge.

Al termine della catena, anche se interrotta, ferma i processi avviati per il lavoro ed esci
con `ExitWorktree(action: "keep")` se l'ingresso è attivo. Qui lo step 5 rimuove solo i
worktree detached della review, mai quello di implementazione.

Poi stampa la tabella di «Verifica finale» senza la riga «Prossimo passo», seguita dalle sezioni
«Cosa fai ora» e «Da sapere» e dalla riga «Dettagli» del «Report finale» di `issue-cycle`,
costruite rileggendo il registro.
