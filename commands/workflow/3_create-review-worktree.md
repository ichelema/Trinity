---
description: Crea un branch e un worktree pulito per una review indipendente
argument-hint: <source-branch> <issue-id> <model>
arguments:
  - source_branch
  - issue_id
  - model
disable-model-invocation: true
---

Crea un branch e un worktree separato per la review del branch remoto
`$source_branch`, relativo alla issue Linear `$issue_id`.

Il modello che eseguirà la review è `$model`.

## Validazione degli argomenti

Verifica che siano presenti tutti gli argomenti:

- source branch: `$source_branch`
- issue ID: `$issue_id`
- modello: `$model`

Se ne manca uno, fermati e mostra:

`/3_create-review-worktree <source-branch> <issue-id> <model>`

## Determinazione del tipo dalla issue

Recupera la issue `$issue_id` da Linear in modalità esclusivamente read-only.

Esamina:

- issue type;
- label;
- titolo;
- descrizione.

Determina il prefisso usando queste regole:

- se la issue è esplicitamente un bug, usa `bug`;
- se la issue è esplicitamente un miglioramento, usa `improvments`;
- se il tipo è assente, diverso o ambiguo, fermati e chiedi quale prefisso
  utilizzare.

Dai priorità all'issue type strutturato di Linear. Usa label, titolo e
descrizione solo come conferma, non per sovrascrivere un tipo esplicito.

Non modificare la issue, i commenti, lo stato o altri dati Linear.

## Nomi da creare

Costruisci il nome base:

`$issue_id-review-$model`

Costruisci il branch di review:

`<prefix>/$issue_id-review-$model`

Esempi:

- `bug/ICH-72-review-gpt-5.6-sol`
- `improvments/ICH-72-review-claude-opus-4.1`

La directory del worktree deve chiamarsi:

`<prefix>+$issue_id-review-$model`

Il `+` sostituisce il `/` del branch (che non è valido nei nomi di
directory) e mantiene il raggruppamento visivo coerente con gli altri
worktree (es. `improvements+ICH-72-retain-gate-dedup`).

Verifica il nome del branch con:

`git check-ref-format --branch "<review-branch>"`

Se non è valido, fermati. Non correggerlo automaticamente.

## Risoluzione del branch sorgente

Non modificare il working tree corrente.

Esegui:

`git fetch origin`

Non eseguire `git pull`.

Accetta `$source_branch` con o senza il prefisso `origin/` e rimuovi
l'eventuale prefisso prima di costruire il riferimento remoto.

Verifica che esista esattamente:

`refs/remotes/origin/<source-branch>`

Non utilizzare automaticamente branch locali e non cercare branch simili.

Risolvi lo SHA aggiornato con:

`git rev-parse --verify "origin/<source-branch>^{commit}"`

## Controlli prima della creazione

Verifica che non esista già il branch locale:

`refs/heads/<review-branch>`

Verifica inoltre che non esista già un worktree associato allo stesso
branch.

Determina la root del repository.

La directory di destinazione è dentro `.claude/worktrees/`:

`<repo-root>/.claude/worktrees/<prefix>+$issue_id-review-$model`

Se il branch o la directory esistono già, fermati senza modificarli,
riutilizzarli o eliminarli.

Prima della creazione mostra:

- tipo recuperato da Linear;
- prefisso selezionato;
- branch sorgente remoto;
- SHA sorgente;
- branch di review;
- percorso assoluto del worktree.

## Creazione

Risolvi il percorso assoluto del worktree in formato Windows dentro
`.claude/worktrees/`:

`<repo-root>/.claude/worktrees/<prefix>+$issue_id-review-$model`

Esempio: se la root è `E:/AI/Claude/Trinity` e il prefisso è
`improvements`, il worktree sarà
`E:/AI/Claude/Trinity/.claude/worktrees/improvements+ICH-72-review-Fable`.

Crea il branch e il worktree usando il percorso assoluto Windows:

`git worktree add -b "<review-branch>" "<percorso-assoluto-Windows>" "<SHA>"`

Non eseguire checkout, reset, stash o modifiche nel working tree originale.

## Compatibilità SmartGit

Dopo la creazione, git MSYS2 scrive un path POSIX (es. `/e/AI/...`) nel
file `.git` del worktree. SmartGit non riconosce quel formato.

Converti il path in formato Windows:

1. Leggi il file `<worktree-path>/.git`.
2. Nel valore `gitdir:`, sostituisci il prefisso `/<lettera>/` con
   `<LETTERA>:/` (es. `/e/` → `E:/`).
3. Riscrivi il file.
4. Verifica che `git -C "<worktree-path>" status` funzioni ancora.

> **Nota — rimozione del worktree.** `git worktree remove` valida il
> file `.git` interno del worktree e lo esige in formato POSIX: con il
> path convertito in formato Windows la rimozione fallisce. Prima di
> rimuovere il worktree, ripristina il valore `gitdir:` al formato POSIX
> (es. `E:/` → `/e/`), poi esegui `git worktree remove`. Non usare mai
> `git worktree prune` come scorciatoia: su questa macchina ha già
> cancellato worktree e branch estranei.

## Verifica finale

Nel nuovo worktree verifica che:

- il branch attivo sia `<review-branch>`;
- `HEAD` corrisponda allo SHA del branch sorgente;
- `git status --short` non produca output.

Se un comando fallisce, fermati. Non eseguire cleanup o operazioni
distruttive automaticamente.

Alla fine stampa esclusivamente questa tabella, sostituendo i segnaposto
con i valori effettivi:

```
┌────────────────────────┬──────────────────────────────────────────────────────────┐
│         Campo          │                          Valore                          │
├────────────────────────┼──────────────────────────────────────────────────────────┤
│ Issue Linear           │ <issue-id> — <titolo-issue>                             │
├────────────────────────┼──────────────────────────────────────────────────────────┤
│ Tipo rilevato          │ <tipo> (<sorgente: label/type>)                         │
├────────────────────────┼──────────────────────────────────────────────────────────┤
│ Prefisso               │ <prefisso>                                              │
├────────────────────────┼──────────────────────────────────────────────────────────┤
│ Branch sorgente remoto │ origin/<source-branch>                                  │
├────────────────────────┼──────────────────────────────────────────────────────────┤
│ SHA sorgente           │ <sha-completo>                                          │
├────────────────────────┼──────────────────────────────────────────────────────────┤
│ Commit                 │ <messaggio-commit>                                      │
├────────────────────────┼──────────────────────────────────────────────────────────┤
│ Branch di review       │ <review-branch>                                         │
├────────────────────────┼──────────────────────────────────────────────────────────┤
│ Worktree               │ <percorso-assoluto-Windows>                             │
├────────────────────────┼──────────────────────────────────────────────────────────┤
│ SmartGit               │ gitdir convertito a formato Windows                     │
├────────────────────────┼──────────────────────────────────────────────────────────┤
│ Stato                  │ Pulito — nessun file modificato                         │
└────────────────────────┴──────────────────────────────────────────────────────────┘
```

Adatta la larghezza della colonna Valore al contenuto effettivo.

Non iniziare la review e non modificare file nel nuovo worktree.