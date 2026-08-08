# Merge della Pull Request

Usa questo workflow solo quando l'utente chiede esplicitamente di fare il merge
di una Pull Request precedentemente revisionata.

Prima del merge:

1. Identifica la Pull Request corrente.
2. Verifica che sia ancora aperta.
3. Verifica che i check richiesti siano superati.
4. Verifica che non ci siano conflitti bloccanti.
5. Conferma che il branch di destinazione sia quello di default del repository
   (`gh repo view --json defaultBranchRef -q .defaultBranchRef.name`, non
   assumere `master` né `main`).

Usa la strategia di merge configurata per il repository, invece di imporne una:
la strategia è una scelta del progetto, e forzarne un'altra sporca una storia
che il repository mantiene in un certo modo per un motivo.

Dopo un merge riuscito:

1. Passa al branch di default.
2. Esegui il pull dello stato aggiornato dal remoto.
3. Elimina il branch locale della feature.
4. Elimina il branch remoto della feature, se esiste ancora.
5. Verifica che il working tree sia pulito.

Se le magic words erano corrette, Linear chiude da sé le issue collegate al
merge: verifica lo stato invece di aggiornarlo a mano, così eviti di
sovrascrivere una transizione già avvenuta.

Se viene aggiunto un commento finale su Linear, deve essere sempre in inglese.

Mostra:

- PR mergiata
- risultato del merge
- branch eliminato
- stato corrente del branch di default
- stato delle issue collegate

Non eseguire mai il merge senza una richiesta esplicita dell'utente: è
l'operazione meno reversibile del workflow, ed è il punto in cui la revisione
umana smette di poter intervenire.
