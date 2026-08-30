# Workflow git / PR / merge

Vale per ogni lavoro su issue Linear, indipendentemente dal backend.

## Branch

- Più issue correlate: una issue principale, un solo branch, una sola PR.
  Più branch per un lavoro unitario producono PR che si sovrappongono.
- Prima di toccare il codice verifica che il working tree sia pulito
  (`git status --short`). Se non lo è, fermati e chiedi come procedere
  (commit, stash, o annulla). Non decidere da solo, mai `git checkout .` /
  `reset --hard` / `stash` senza risposta.
- Rileva il branch di default, non assumere `master`/`main`:
  `gh repo view --json defaultBranchRef -q .defaultBranchRef.name`.
- Usa esattamente il `gitBranchName` di Linear quando disponibile: è il campo
  da cui Linear riconosce il collegamento branch→PR→issue. Se manca,
  costruiscilo nello stesso formato `<utente>/<id-issue-minuscolo>-<titolo-kebab>`
  mantenendo l'ID issue.
- Dopo il branch, se la issue è `backlog`/`unstarted`, portala a In Progress
  (una volta sola). Da lì non aggiornare più lo stato a mano: le transizioni
  PR aperta → In Review → Done arrivano via webhook.

## Dipendenze (blocked by)

- Prima di iniziare leggi le relazioni `blockedBy` della issue (nel GraphQL:
  seleziona il campo `relations` o `blockedBy`).
- Se è bloccata da issue non completate, NON iniziare: mostra quali bloccano e
  il loro stato, e attendi una decisione esplicita.
- Un blocco non è un divieto: l'utente può procedere comunque. La decisione è
  sua, il tuo compito è renderla informata.

## Pull Request

- Magic words nel titolo/descrizione:
  - Per chiudere: `close`/`closes`/`fix`/`fixes`/`resolve`/`resolves`/
    `complete`/`completes`/`implement`/`implements` (anche forme -d/-ing).
  - Per collegare senza chiudere: `ref`/`refs`/`references`/`part of`/
    `related to`/`relates to`/`contributes to`/`toward`/`towards`.
  - Usa la forma non-closing quando la PR contribuisce senza esaurire la issue:
    la magic word sbagliata chiude lavoro ancora aperto.
- La PR contiene: riepilogo conciso, dettagli implementativi, test eseguiti,
  riferimenti alle issue Linear.
- Titolo e descrizione della PR in inglese (il titolo finisce come attachment
  della issue).
- **Non fare il merge**: fermati e attendi l'approvazione esplicita dell'utente.

## Merge (solo su richiesta esplicita)

- Verifica: PR ancora aperta, check superati, nessun conflitto bloccante,
  branch di destinazione = default del repo.
- Usa la strategia di merge configurata per il repo, non imporne una.
- Dopo il merge: passa al default, `git pull`, elimina branch locale e remoto,
  verifica working tree pulito.
- Se le magic words erano corrette Linear chiude da sé le issue: verifica lo
  stato invece di aggiornarlo a mano.
- Mai il merge senza richiesta esplicita: è l'operazione meno reversibile del
  workflow.
