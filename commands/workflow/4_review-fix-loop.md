---
description:
  Due review indipendenti in parallelo (trinity:reviewer su Fable, gpt-bridge:reviewer su GPT) su worktree isolati, loop
  di fix minimi e report finale
argument-hint: <issue-id...> <model>
disable-model-invocation: true
---

Esegui due review indipendenti e parallele della PR delle issue indicate su worktree isolati, poi
applica i fix che meritano di essere fatti in un loop, finché non emergono più finding. In uscita,
report sintetico.

Le due review usano lo stesso prompt del reviewer su due modelli diversi: `trinity:reviewer` su Fable
e `gpt-bridge:reviewer` su GPT 5.6 sol xhigh (via proxy LiteLLM, servito dalla mod gpt-bridge).
Se `gpt-bridge:reviewer` non compare tra i subagent_type disponibili, la mod non è caricata: fermati
e dillo all'utente prima di creare i worktree.

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
   reviewer, con path assoluti in formato Windows (`E:/...`) su Windows/MSYS2:
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
   `/...` nel prompt di un subagente non viene espanso.
   Ogni reviewer scrive i file di appoggio solo in `<review-wt-path>/.review-tmp/`, mai altrove.
   - review `fable`: tool Agent con `subagent_type: trinity:reviewer`; nel prompt digli
     di leggere `${CLAUDE_PLUGIN_ROOT}/commands/workflow/3_independent-review.md` e di seguirlo con
     quegli argomenti al posto di `$ARGUMENTS`;
   - review `gpt`: tool Agent con `subagent_type: gpt-bridge:reviewer`, stesso prompt della review
     `fable`. Il subagente gira su GPT via proxy LiteLLM con tool e permessi nativi, e compare nel
     pannello degli agenti come l'altro.
   Lancia le due Agent nello stesso messaggio, così girano in parallelo. Se `<model>` coincide con
   uno dei due modelli di review (`fable` o `gpt`), segnalalo: quella review gira sullo stesso
   modello che ha scritto il codice ed è meno indipendente.
3. Raccogli i due report.
4. Rimuovi i due worktree leggendo e seguendo
   `${CLAUDE_PLUGIN_ROOT}/commands/workflow/5_remove-worktree.md` (per lo stesso motivo non puoi
   invocarlo come slash command), con `$worktree_name` = `<review-wt-path>`.

Le review sono read-only: nessun reviewer modifica file.

## Triage dei finding

Fondi i due report e per ogni finding decidi se è reale e merita un fix:

- è verificabile nel codice, non un'ipotesi;
- è un difetto o una violazione di requisito, non una preferenza stilistica;
- è dentro lo scope delle issue.

L'accordo dei due reviewer è un segnale forte ma non una prova: verifica comunque ogni finding nel
codice. La discordanza non è un motivo per scartare: controlla il finding singolarmente. Scarta i
falsi positivi e le preferenze stilistiche, senza riproporli nel round successivo.

## Fix minimi e chirurgici

Sul worktree di implementazione `<wt-path>`, applica solo i finding reali:

- prima del primo fix entra con un comando a sé, `cd "<wt-path>"`; dopo il push, o se ti fermi
  prima, esci con `cd "<repo-root>"`: lo step 5 non può cancellare la cwd della sessione;
- comandi sempre con `git -C "<wt-path>"`, `mise -C "<wt-path>"` e path assoluti;
- la minima modifica che risolve il difetto;
- nessun refactoring, nessuna riscrittura, nessun cambio di architettura;
- ogni riga modificata è riconducibile a un finding verificato;
- commit in inglese, uno per fix logico;
- push per aggiornare la PR.

Se un finding non si risolve con un fix minimo, non improvvisare una soluzione più ampia: segnalalo
nel report come criticità e chiedi.

## Loop

Ripeti round → triage → fix finché un round completo non produce alcun finding da fixare, con un
massimo di 3 round. Dal secondo round in poi fixa solo `BLOCKER`, `HIGH` e `MEDIUM`: i `LOW` vanno
nel report come residui, non in un nuovo giro.

Fermati e segnala se:

- hai completato il terzo round e restano finding da fixare: elencali nel report con il motivo;
- due round consecutivi ripropongono lo stesso finding già scartato come falso positivo (i due
  reviewer non convergono: disaccordo di fondo);
- un fix ne introduce un altro a valanga (il fix non era minimo).

## Report finale

Report sintetico, solo informazioni rilevanti:

- cosa è stato fixato (finding → fix, con file e righe);
- trade-off introdotti dai fix (se presenti);
- criticità residue o finding non risolti e perché;
- verdetto finale: PR pronta per il merge o no.

Se qualcosa non è chiaro, è contraddittorio o hai dubbi, chiedi prima di procedere. Altrimenti
mettiti al lavoro.
