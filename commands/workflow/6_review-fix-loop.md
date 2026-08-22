---
description: Due review indipendenti in parallelo (deepseek + trinity:deep-reasoner) su worktree isolati, loop di fix minimi e report finale
argument-hint: <issue-id...> <model>
disable-model-invocation: true
---

Esegui due review indipendenti e parallele della PR delle issue indicate su
worktree isolati, poi applica i fix che meritano di essere fatti in un loop,
finché non emergono più finding. In uscita, report sintetico.

Le due review girano su modelli diversi: `deepseek` e `trinity:deep-reasoner`.

L'ultimo argomento è il modello: identifica il worktree di implementazione
creato da `/1_create-worktree` (e quindi il branch della PR). Non sceglie il
modello di esecuzione.

## Validazione degli argomenti

Dividi `$ARGUMENTS` in token separati da spazi:

- l'ultimo token è il modello di implementazione;
- i token precedenti sono gli issue ID (almeno uno).

Se i token sono meno di 2, fermati e mostra:

`/6_review-fix-loop <issue-id...> <model>`

## Localizzazione del worktree e della PR

Non ricostruire il prefisso: ricava il worktree dallo stato reale di Git.

```bash
git worktree list --porcelain
```

Cerca l'entry il cui branch termina esattamente con `/<base-name>`, dove
`<base-name>` segue la regola dello step 1: una sola issue →
`<issue-id>-<model>` (es. `improvments/ICH-84-fable`); più issue → prefisso
team una sola volta, poi i numeri delle successive, infine il modello
(es. `improvments/ICH-97-98-fable`). Da quella entry ricava `<wt-path>` e
`<branch>`.

Se non esiste, fermati: il worktree di implementazione va creato prima con
`/1_create-worktree`.

Verifica che esista una PR aperta per `<branch>`:

```bash
gh pr view "<branch>" --json url,state,title -q '.url'
```

Se non esiste, fermati e chiedi all'utente di aprirla o di passarti l'URL:
la review parte dalla PR, non da un branch orfano.

## Round di review parallela

Per ogni round:

1. Crea due worktree di review isolati, uno per modello:
   `/3_create-review-worktree <branch> <issue-id...> deepseek`
   `/3_create-review-worktree <branch> <issue-id...> deep-reasoner`
2. Lancia `/4_independent-review <issue-id...>` sui due worktree in parallelo
   (due subagent separati, uno per worktree).
3. Raccogli i due report.
4. Rimuovi i due worktree con `/5_remove-worktree`.

Le review sono read-only: nessun reviewer modifica file.

## Triage dei finding

Fondi i due report e per ogni finding decidi se è reale e merita un fix:

- è verificabile nel codice, non un'ipotesi;
- è un difetto o una violazione di requisito, non una preferenza stilistica;
- è dentro lo scope delle issue.

L'accordo dei due reviewer è un segnale forte ma non una prova: verifica
comunque ogni finding nel codice. La discordanza non è un motivo per scartare:
controlla il finding singolarmente. Scarta i falsi positivi e le preferenze
stilistiche, senza riproporli nel round successivo.

## Fix minimi e chirurgici

Sul worktree di implementazione `<wt-path>`, applica solo i finding reali:

- la minima modifica che risolve il difetto;
- nessun refactoring, nessuna riscrittura, nessun cambio di architettura;
- ogni riga modificata è riconducibile a un finding verificato;
- commit in inglese, uno per fix logico;
- push per aggiornare la PR.

Se un finding non si risolve con un fix minimo, non improvvisare una soluzione
più ampia: segnalalo nel report come criticità e chiedi.

## Loop

Ripeti round → triage → fix finché un round completo non produce alcun finding
da fixare.

Fermati e segnala se:

- due round consecutivi ripropongono lo stesso finding già scartato come falso
  positivo (i due reviewer non convergono: disaccordo di fondo);
- un fix ne introduce un altro a valanga (il fix non era minimo).

## Report finale

Report sintetico, solo informazioni rilevanti:

- cosa è stato fixato (finding → fix, con file e righe);
- trade-off introdotti dai fix (se presenti);
- criticità residue o finding non risolti e perché;
- verdetto finale: PR pronta per il merge o no.

Se qualcosa non è chiaro, è contraddittorio o hai dubbi, chiedi prima di
procedere. Altrimenti mettiti al lavoro.
