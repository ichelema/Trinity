# Workflow git / PR / merge

Vale per ogni lavoro su issue Linear, indipendentemente dal backend.

## Checklist da copiare e spuntare

Copia questa lista nella risposta e spunta ogni passo. I dettagli sono nelle sezioni sotto.

1. [ ] Working tree pulito (`git status --short`); se non lo è, fermati e chiedi.
2. [ ] Branch di default rilevato con `gh repo view`.
3. [ ] Relazioni `blockedBy` lette; se la issue è bloccata, mostra i blocchi e attendi.
4. [ ] Branch creato con il `gitBranchName` di Linear.
5. [ ] Issue portata a In Progress (una volta sola, solo da `backlog`/`unstarted`).
6. [ ] PR aperta con riepilogo, dettagli, test eseguiti e riferimento alla issue.
7. [ ] Controllo PR: titolo e descrizione nella lingua del progetto, magic word giusta
   (closing o non-closing). Se un punto fallisce, correggi la PR e torna al passo 7.
8. [ ] Stop: merge solo su richiesta esplicita dell'utente.
9. [ ] Dopo il merge: branch di default, `git pull`, branch locale e remoto eliminati,
   working tree pulito.
10. [ ] Stato della issue controllato su Linear, non aggiornato a mano. Se doveva chiudersi
    e non si è chiusa, mostralo all'utente con la magic word usata.

Prima di consegnare, rileggi i passi 7 e 10: finisci solo quando passano entrambi.

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
- Titolo e descrizione della PR nella lingua del progetto Linear (il titolo
  finisce come attachment della issue; vedi "Lingua" in `SKILL.md`).
- **Non fare il merge**: fermati e attendi l'approvazione esplicita dell'utente.

## Merge (solo su richiesta esplicita)

- Verifica: PR ancora aperta, check superati, nessun conflitto bloccante,
  branch di destinazione = default del repo.
- Usa la strategia di merge configurata per il repo, non imporne una.
- Dopo il merge: passa al default, `git pull`, elimina branch locale e remoto,
  verifica working tree pulito.
- **Sync locale con working tree sporco.** `gh pr merge` esegue comunque il
  merge su GitHub, ma fallisce la sincronizzazione locale
  (`cannot pull with rebase: You have unstaged changes`) quando il working tree
  ha modifiche non committate e `pull.rebase` è attivo. In quel caso il merge su
  GitHub è già avvenuto: aggiorna con `git fetch origin` +
  `git merge --ff-only origin/master`, poi elimina il branch locale.
- Se le magic words erano corrette Linear chiude da sé le issue: verifica lo
  stato invece di aggiornarlo a mano.
- Mai il merge senza richiesta esplicita: è l'operazione meno reversibile del
  workflow.
