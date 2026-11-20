---
description:
  Due review indipendenti in parallelo (trinity:reviewer su Fable, gpt-bridge:reviewer su GPT) su
  worktree isolati, loop di fix minimi e report finale
argument-hint: <issue-id...> <model>
disable-model-invocation: true
---

Esegui due review indipendenti e parallele della PR delle issue indicate su worktree isolati, poi
applica i fix dei finding reali in un loop di al massimo 3 round. In uscita, smista i finding
residui (fix, issue Linear o PR in draft) senza perderne nessuno e scrivi un report sintetico.

Le due review usano lo stesso prompt del reviewer su due modelli diversi: `trinity:reviewer` su
Fable e `gpt-bridge:reviewer` sul modello GPT fissato da `gpt-model` in `agents/reviewer.md` (via
proxy LiteLLM, servito dalla mod gpt-bridge). Se `gpt-bridge:reviewer` non compare tra i
subagent_type disponibili, la mod non è caricata: fermati e dillo all'utente prima di creare i
worktree.

L'ultimo argomento è il modello: identifica il worktree di implementazione creato da
`/1_create-worktree` (e quindi il branch della PR). Non sceglie il modello di esecuzione.

## Validazione degli argomenti

Dividi `$ARGUMENTS` in token separati da spazi:

- l'ultimo token è il modello di implementazione;
- i token precedenti sono gli issue ID (almeno uno).

Se i token sono meno di 2, fermati e mostra:

`/trinity:workflow:4_review-fix-loop <issue-id...> <model>`

## Localizzazione del worktree e della PR

Non ricostruire il prefisso: ricava il worktree dallo stato reale di Git.

```bash
git worktree list --porcelain
```

Cerca l'entry il cui branch termina esattamente con `/<base-name>`, dove `<base-name>` segue la
regola dello step 1: una sola issue → `<issue-id>-<model>` (es. `improvments/ICH-84-fable`); più
issue → prefisso team una sola volta, poi i numeri delle successive, infine il modello (es.
`improvments/ICH-97-98-fable`). Da quella entry ricava `<wt-path>` e `<branch>`.

Se non esiste, fermati: il worktree di implementazione va creato prima con `/1_create-worktree`.

Verifica che esista una PR aperta per `<branch>`:

```bash
gh pr view "<branch>" --json url,state,title -q '.url'
```

Se non esiste, fermati e chiedi all'utente di aprirla o di passarti l'URL: la review parte dalla PR,
non da un branch orfano.

## Round di review parallela

Per ogni round:

1. Crea due worktree di review isolati e detached (senza branch: il reviewer non committa), uno per
   reviewer, con path assoluti in formato Windows (`D:/...`) su Windows/MSYS2:
   ```bash
   git fetch origin
   repo_root="$(git rev-parse --path-format=absolute --git-common-dir)"; repo_root="${repo_root%/.git}"
   command -v cygpath >/dev/null && repo_root="$(cygpath -m "$repo_root")"   # solo Windows/MSYS2
   sha="$(git rev-parse --verify "origin/<branch>^{commit}")"
   git worktree add --detach "$repo_root/.claude/worktrees/review+<base-name>-gpt" "$sha"
   git worktree add --detach "$repo_root/.claude/worktrees/review+<base-name>-fable" "$sha"
   ```
   Se una delle directory esiste già (round precedente non ripulito), fermati. Non toccare il file
   `.git` dentro i worktree.
2. Esegui `/trinity:workflow:3_independent-review` sui due worktree in parallelo, uno per reviewer,
   con argomenti `<issue-id...> <model> <review-wt-path>`. Il command ha
   `disable-model-invocation: true`: né tu né un subagente potete invocarlo come slash command, e un
   `/...` nel prompt di un subagente non viene espanso. Ogni reviewer scrive i file di appoggio solo
   in `<review-wt-path>/.review-tmp/`, mai altrove.
   - review `fable`: tool Agent con `subagent_type: trinity:reviewer`; nel prompt digli di leggere
     `${CLAUDE_PLUGIN_ROOT}/commands/workflow/3_independent-review.md` e di seguirlo con quegli
     argomenti al posto di `$ARGUMENTS`;
   - review `gpt`: tool Agent con `subagent_type: gpt-bridge:reviewer`, stesso prompt della review
     `fable`. Il subagente gira su GPT via proxy LiteLLM con tool e permessi nativi, e compare nel
     pannello degli agenti come l'altro.

   Dal secondo round aggiungi a entrambi i prompt la lista degli scarti dei round precedenti (vedi
   «Triage dei finding»), uno per riga con file, simbolo o snippet e motivo, e questa istruzione:
   «Se un tuo candidato coincide con uno di questi scarti, controlla il motivo nel codice attuale:
   se regge, metti il candidato in `REFUTED` citando la riga che lo prova; se non regge,
   riproponilo e spiega perché il motivo non vale più».

   Lancia le due Agent nello stesso messaggio, così girano in parallelo. Se `<model>` coincide con
   uno dei due modelli di review (`fable` o `gpt`), segnalalo: quella review gira sullo stesso
   modello che ha scritto il codice ed è meno indipendente.

3. Raccogli i due report. I reviewer girano come subagenti, quindi scrivono il formato completo
   di `3_independent-review.md`, con le prove che servono al triage.
4. Rimuovi i due worktree leggendo e seguendo
   `${CLAUDE_PLUGIN_ROOT}/commands/workflow/5_remove-worktree.md` (per lo stesso motivo non puoi
   invocarlo come slash command), con `$worktree_name` = `<review-wt-path>`.

Le review sono read-only: nessun reviewer modifica file.

## Triage dei finding

Fondi i due report. Un finding presente in entrambi (stesso difetto, stesso punto, stesso motivo)
va tenuto una volta sola, con lo scenario più concreto e l'esito più forte (`CONFIRMED` prevale su
`PLAUSIBLE`), segnando che l'hanno trovato tutti e due.

Per ogni finding decidi se è reale e merita un fix:

- il meccanismo è verificabile nel codice, non è un'ipotesi; un innesco incerto (`PLAUSIBLE`) non
  basta per scartarlo;
- è un difetto o una violazione di requisito, non una preferenza stilistica;
- è dentro lo scope delle issue.

L'accordo dei due reviewer è un segnale forte ma non una prova: verifica comunque ogni finding nel
codice, partendo dalla prova del report (`file:riga`, scenario ed esito del verify) invece di rifare
l'analisi da zero. La discordanza non è un motivo per scartare: se l'altro reviewer ha confutato lo
stesso candidato (riga `REFUTED` in «Aspetti verificati senza anomalie»), confronta le due prove
nel codice. Scarta le preferenze stilistiche e, solo con una prova come per `REFUTED`, i falsi
positivi: la riga che contraddice il finding, la guard che lo gestisce o l'invariante che lo rende
impossibile. Tieni la lista degli scarti, ognuno con file, simbolo o snippet e il motivo in una
riga. Nel loop la passi ai reviewer dal secondo round e la riporti nel commento sulla PR.

## Fix minimi e chirurgici

Sul worktree di implementazione `<wt-path>`, applica solo i finding reali:

- prima del primo fix entra con un comando a sé, `cd "<wt-path>"`; dopo il push, o se ti fermi
  prima, esci con `cd "<repo-root>"`: lo step 5 non può cancellare la cwd della sessione;
- comandi sempre con `git -C "<wt-path>"`, `mise -C "<wt-path>"` e path assoluti;
- la minima modifica che risolve il difetto;
- nessun refactoring, nessuna riscrittura, nessun cambio di architettura;
- ogni riga modificata è riconducibile a un finding verificato;
- commit nella lingua del progetto Linear, uno per fix logico;
- push per aggiornare la PR.

Se un finding non si risolve con un fix minimo, non improvvisare una soluzione più ampia: trattalo
come finding residuo (sezione "Finding residui").

## Loop

Ripeti round → triage → fix finché un round completo non produce alcun finding da fixare, con un
massimo di 3 round di review. In ogni round fixa tutti i finding reali, `LOW` compresi.

Esci dal loop e passa ai finding residui se:

- hai completato la review del terzo round: i suoi finding sono finding residui;
- due round consecutivi ripropongono lo stesso finding già scartato come falso positivo (i due
  reviewer non convergono: disaccordo di fondo);
- un fix ne introduce un altro a valanga (il fix non era minimo).

Non avviare mai un quarto round di review.

## Finding residui

Nessun finding si perde: ogni finding residuo finisce in un fix, in una issue Linear o nel commento
sulla PR. Gestisci i residui in quest'ordine:

1. `LOW`: fixali subito come in "Fix minimi e chirurgici", senza un nuovo round di review. Un `LOW`
   senza fix minimo diventa una issue come un `MEDIUM`.
2. `MEDIUM`: crea una issue Linear per finding.
3. `BLOCKER` e `HIGH`: la PR non è pronta. Mettila in draft con `gh pr ready "<branch>" --undo`; se
   il piano GitHub non supporta le draft, basta il commento.
4. Scrivi il commento sulla PR, sempre.

### Issue Linear

Crea le issue senza chiedere conferma, con `issueCreate` via
`${CLAUDE_PLUGIN_ROOT}/skills/linear/scripts/linear.py mutation`:

- team e progetto della issue di origine (quella nel cui scope cade il finding);
- titolo operativo e corpo con `Problem` e `Acceptance criteria` come in `/0_create-issue`, più file
  e righe del finding e il suo esito: `CONFIRMED`, oppure `PLAUSIBLE` con cosa rende incerto
  l'innesco;
- tipo `bug`; priorità `3` per `MEDIUM`, `4` per `LOW`;
- lingua del progetto Linear.

Collega ogni issue alla issue di origine con `issueRelationCreate` di tipo `related`, non con
`parentId`: una sub-issue può chiudersi in automatico con la issue padre al merge della PR. Rileggi
ogni issue creata e controlla che team, progetto e relazione siano salvati.

### Commento sulla PR

Scrivi un solo commento, nella lingua del progetto Linear, con
`gh pr comment "<branch>" --body-file -` (corpo da stdin). Il commento elenca:

- i finding fixati, in breve;
- i `LOW` fixati senza review dopo il terzo round, segnati come non riverificati;
- i `BLOCKER` e `HIGH` aperti, con file e righe;
- le issue create, con link;
- i finding scartati come falsi positivi, con il motivo in una riga.

Accanto a ogni finding fixato o aperto scrivi l'esito del verify, `CONFIRMED` o `PLAUSIBLE`.

## Report finale

Il report lo legge una persona, che deve capire in pochi secondi cosa fare. Al massimo 15 righe,
in quest'ordine:

1. Il verdetto in grassetto, `PRONTA PER IL MERGE` oppure `NON PRONTA`, e una frase con il
   motivo.
2. **Cosa fai ora**: da 1 a 3 azioni numerate, ognuna aperta da un verbo all'imperativo, con i
   comandi in un blocco di codice con il tag del linguaggio. Con la PR pronta:
   ```bash
   gh pr merge "<branch>" --merge
   ```
   poi `/trinity:workflow:5_remove-worktree <prefix>+<base-name>`. Con la PR non pronta: il
   finding `BLOCKER` o `HIGH` da risolvere, con `file:riga`.
3. **Fix**: una riga per fix, `file:riga` → cosa cambia. Ometti la sezione se non ci sono fix.
4. **Aperti**: una riga per finding residuo, con la sua destinazione: issue creata (con link), PR
   in draft o `LOW` fixato senza review. Ometti la sezione se non ci sono residui.
5. **Trade-off**: solo se un fix ne introduce uno, una riga ciascuno.

In fondo metti il link al commento sulla PR: contiene i dettagli, compresi i finding scartati.
Non elencare round, worktree rimossi, comandi di test o finding scartati.
