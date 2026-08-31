---
description: Crea una issue Linear ben formata a partire da una descrizione libera del lavoro
argument-hint: <descrizione del lavoro da fare>
disable-model-invocation: true
---

Crea una nuova issue Linear a partire da questa descrizione:

$ARGUMENTS

## Validazione dell'argomento

Se la descrizione è vuota, fermati e mostra:

`/0_create-issue <descrizione del lavoro da fare>`

Non dedurre la issue dal branch corrente, dalla cronologia Git o dal contenuto
del working tree.

## Perimetro

Questo step **crea soltanto la issue**. Non creare branch, worktree, commit o
PR: quello è compito di `/1_create-worktree` e `/2_work-issue`.

Fino alla conferma esplicita dell'utente lavora in sola lettura su Linear: nessuna
mutation, nessun commento.

## Raccolta dei dati

Determina, a partire dalla descrizione:

- titolo operativo;
- descrizione del problema;
- criteri di accettazione;
- estimate;
- team;
- progetto;
- stato;
- priorità;
- label;
- vincoli tecnici (se presenti);
- test richiesti (se presenti);
- dipendenze da altre issue (se presenti);
- eventuale parent issue.

Recupera i valori validi dal workspace via `scripts/linear.py query`, mai a memoria:

| Campo | Query GraphQL |
| --- | --- |
| Progetti | `projects` |
| Stati | `workflowStates` |
| Label | `issueLabels` |
| Team | `teams` |
| Assegnatari | `users` |
| Scala estimate | `teams` (campo `estimateScale`) |

Stati e label sono configurabili per workspace e per team: gli elenchi di un
progetto non valgono per un altro, e proporre un valore inesistente fa fallire
la creazione o la fa passare con un campo vuoto.

Se i team sono più di uno, chiedi quale usare prima di leggere stati, label e
scala estimate: dipendono dal team.

La priorità è un'enum fissa di Linear: `0` nessuna, `1` urgente, `2` alta,
`3` media, `4` bassa.

Chiedi solo i campi mancanti. Se la descrizione contiene già un valore valido,
non richiederlo di nuovo.

## Issue type

Lo step 1 ricava il prefisso del branch dal tipo della issue (`bug` o
`improvments`) e si ferma se il tipo è assente o ambiguo. Imposta quindi un
issue type esplicito, o in mancanza una label che lo renda inequivocabile, così
il passo successivo non si blocca.

## Titolo operativo

Il titolo descrive l'azione da compiere, non il sintomo. Chi lo legge nella
board deve capire cosa fare senza aprire la issue.

- Male: "Login bug"
- Bene: "Fix redirect after magic link login"

## Corpo della issue

`Problem` e `Acceptance criteria` sono obbligatori; le altre sezioni si
includono solo quando hanno contenuto utile — una sezione vuota o riempita per
obbligo è rumore.

    ## Problem

    <what is broken or missing, with enough context that the reader
    understands the why without having to ask>

    ## Acceptance criteria

    - [ ] <testable condition — the reader should be able to answer yes/no>
    - [ ] <testable condition>

    ## Technical constraints

    <architectural limitations, system dependencies, compatibility requirements>

    ## Required tests

    - [ ] <specific test to write or verify>

Gli acceptance criteria diventano la checklist verificata da `/2_work-issue` e
la base della review di `/4_independent-review`: una condizione non verificabile
con un sì/no lì a valle non è controllabile da nessuno.

## Estimate

La scala è configurata per team in Linear (lineare, fibonacci, t-shirt, ecc.) —
non è fissa come la priorità. Recuperala con una query su `teams` (campo
`estimateScale`) per conoscere la scala attiva e i valori ammessi. Se il team
non ha l'estimation attiva, salta il campo.

Passa il valore numerico a `issueCreate` nel campo `estimate`.

## Dipendenze

Se la issue dipende da altre issue Linear, usa il campo `blockedBy` di
`issueCreate` passando gli identificativi delle issue bloccanti
(es. `["ICH-42", "ICH-55"]`).

Non inventare identificativi: verifica che le issue referenziate esistano con
`scripts/linear.py query` (query `issue(id:)` o `issues(filter:)`) prima di
aggiungerle come dipendenza. Un ID
inventato non fallisce in modo rumoroso: crea silenziosamente un collegamento
sbagliato o nessun collegamento.

## Presentare le opzioni

Quando serve una scelta, mostra i valori **letti da Linear in quel momento**,
raggruppati per campo:

    Project:
    - <valori dalla query projects>
    - Nessuno

    Status:
    - <valori dalla query workflowStates>

    Labels:
    - <valori dalla query issueLabels>

    Estimate:
    - <valori dalla scala del team>

Questo è un formato di presentazione, non un elenco di valori: i nomi vanno
sempre dalla risposta delle query.

## Lingua

Titolo, descrizione ed eventuali commenti della issue vanno **sempre scritti in
inglese**, anche quando la descrizione dell'utente è in italiano: la issue resta
nel tempo e la leggono altri.

Domande, riepiloghi e output a schermo restano **in italiano**. Fa eccezione la
descrizione mostrata in conferma, che va esibita nella sua forma inglese
definitiva.

## Conferma

Prima di creare la issue mostra:

- Title
- Estimate
- Team
- Project
- Status
- Priority
- Labels
- Parent
- Blocked by
- Description (corpo completo, in inglese)

Chiedi conferma esplicita. Solo dopo la conferma crea la issue con la mutation
`issueCreate` via `scripts/linear.py mutation` (per aggiornare un'issue
esistente usa invece `issueUpdate` con l'`id`).

## Verifica finale

Rileggi la issue creata con `scripts/linear.py query` (`issue(id:)`) e verifica che i campi salvati
corrispondano a quelli confermati. Un valore rifiutato da Linear non produce
sempre un errore: può semplicemente restare vuoto.

Alla fine stampa esclusivamente questa tabella, sostituendo i segnaposto con i
valori effettivi:

```
┌────────────────────────┬──────────────────────────────────────────────────────────┐
│         Campo          │                          Valore                          │
├────────────────────────┼──────────────────────────────────────────────────────────┤
│ Issue ID               │ <issue-id>                                               │
├────────────────────────┼──────────────────────────────────────────────────────────┤
│ Title                  │ <titolo>                                                 │
├────────────────────────┼──────────────────────────────────────────────────────────┤
│ Type                   │ <bug / improvement / …>                                  │
├────────────────────────┼──────────────────────────────────────────────────────────┤
│ Estimate               │ <valore> / non attivo                                    │
├────────────────────────┼──────────────────────────────────────────────────────────┤
│ Team / Project         │ <team> / <progetto o "nessuno">                          │
├────────────────────────┼──────────────────────────────────────────────────────────┤
│ Status                 │ <stato>                                                  │
├────────────────────────┼──────────────────────────────────────────────────────────┤
│ Priority               │ <priorità>                                               │
├────────────────────────┼──────────────────────────────────────────────────────────┤
│ Labels                 │ <label o "nessuna">                                      │
├────────────────────────┼──────────────────────────────────────────────────────────┤
│ Blocked by             │ <issue bloccanti o "nessuna">                            │
├────────────────────────┼──────────────────────────────────────────────────────────┤
│ URL                    │ <url>                                                    │
├────────────────────────┼──────────────────────────────────────────────────────────┤
│ Prossimo passo         │ /1_create-worktree <default-branch> <issue-id...> <model> │
└────────────────────────┴──────────────────────────────────────────────────────────┘
```

Adatta la larghezza della colonna Valore al contenuto effettivo.
