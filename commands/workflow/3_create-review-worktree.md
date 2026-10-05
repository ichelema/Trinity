---
description: Crea un branch e un worktree pulito per una review indipendente
argument-hint: <source-branch> <issue-id...> <model>
disable-model-invocation: true
---

Crea un branch e un worktree separato per la review del branch remoto
indicato, relativo a una o più issue Linear.

Il modello che eseguirà la review è l'ultimo argomento.

## Validazione degli argomenti

Dividi `$ARGUMENTS` in token separati da spazi:

- il primo token è il source branch;
- l'ultimo token è il modello;
- i token intermedi sono gli issue ID (almeno uno).

Se i token sono meno di 3, fermati e mostra:

`/3_create-review-worktree <source-branch> <issue-id...> <model>`

## Determinazione del tipo dalle issue

Recupera ogni issue da Linear (via `scripts/linear.py query`) in modalità esclusivamente read-only.

Esamina:

- issue type;
- label;
- titolo;
- descrizione.

Determina il prefisso usando queste regole:

- se la issue è esplicitamente un bug, usa `bug`;
- se la issue è esplicitamente un miglioramento o un refactoring
  (es. label `Refactor`), usa `improvments`;
- se il tipo è assente, diverso o ambiguo, fermati e chiedi quale prefisso
  utilizzare.

Con più issue, tutte devono risolvere allo stesso prefisso. Se i prefissi
differiscono, fermati e chiedi quale usare.

Dai priorità all'issue type strutturato di Linear. Usa label, titolo e
descrizione solo come conferma, non per sovrascrivere un tipo esplicito.

Non modificare la issue, i commenti, lo stato o altri dati Linear.

## Nomi da creare

Costruisci il nome base:

- una sola issue: `<issue-id>-review-<model>` (es. `ICH-72-review-fable`);
- più issue con lo stesso prefisso team: prefisso una sola volta, poi i
  numeri delle successive in ordine, quindi `review` e il modello
  (`ICH-97` + `ICH-98` → `ICH-97-98-review-fable`);
- issue con prefissi team diversi: fermati e chiedi come nominare.

Nel resto del comando questo valore è `<base-name>`.

Costruisci il branch di review:

`<prefix>/<base-name>`

Esempi:

- `bug/ICH-72-review-gpt-5.6-sol`
- `improvments/ICH-97-98-review-fable`

La directory del worktree deve chiamarsi:

`<prefix>+<base-name>`

Il `+` sostituisce il `/` del branch (che non è valido nei nomi di
directory) e mantiene il raggruppamento visivo coerente con gli altri
worktree (es. `improvments+ICH-97-98-review-fable`).

Verifica il nome del branch con:

`git check-ref-format --branch "<review-branch>"`

Se non è valido, fermati. Non correggerlo automaticamente.

## Risoluzione del branch sorgente

Non modificare il working tree corrente.

Esegui:

`git fetch origin`

Non eseguire `git pull`.

Accetta il source branch con o senza il prefisso `origin/` e rimuovi
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

`<repo-root>/.claude/worktrees/<prefix>+<base-name>`

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

`<repo-root>/.claude/worktrees/<prefix>+<base-name>`

Esempio: se la root è `E:/AI/Claude/Trinity` e il prefisso è
`improvments`, il worktree sarà
`E:/AI/Claude/Trinity/.claude/worktrees/improvments+ICH-97-98-review-fable`.

Crea il branch e il worktree usando il percorso assoluto Windows:

`git worktree add -b "<review-branch>" "<percorso-assoluto-Windows>" "<SHA>"`

Non eseguire checkout, reset, stash o modifiche nel working tree originale.

## Compatibilità SmartGit

SmartGit legge solo il back-pointer `<repo-root>/.git/worktrees/<prefix>+<base-name>/gitdir`.
Avendo passato a `git worktree add` il percorso Windows, quel file è già in
formato `E:/...`: non serve altro.

Verifica che il back-pointer inizi con `<LETTERA>:/`; se è in formato POSIX
(`/e/...`), fermati e segnalalo.

**Non toccare il file `.git` dentro il worktree.** `git worktree remove` lo
valida, e se è in formato Windows la rimozione fallisce ("does not point
back to '.git/worktrees/<nome>'"). Il formato che git scrive lì non è
deterministico: lascialo com'è, ci pensa `/5_remove-worktree` prima della
rimozione. Non usare mai `git worktree prune` come scorciatoia: su questa
macchina ha già cancellato worktree e branch estranei.

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
│ Issue Linear           │ <issue-id> — <titolo-issue> (una riga per issue)        │
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
│ SmartGit               │ back-pointer gitdir in formato Windows                  │
├────────────────────────┼──────────────────────────────────────────────────────────┤
│ Stato                  │ Pulito — nessun file modificato                         │
└────────────────────────┴──────────────────────────────────────────────────────────┘
```

Nell'output scrivila come tabella markdown a due colonne (`| Campo | Valore |`), non con i caratteri di disegno del riquadro: fuori da un blocco di codice il renderer unisce le righe `│` in un paragrafo e le manda a capo. Il riquadro sopra indica solo campi e ordine. Con più
issue, la cella «Issue Linear» contiene una riga per ogni issue.

Non iniziare la review e non modificare file nel nuovo worktree.