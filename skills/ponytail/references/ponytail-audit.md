ponytail-review, su tutto il repo. Scansiona l'intero albero invece di un diff. Classifica
i finding dal taglio più grande per primo.

## Tag

Stessi di ponytail-review:

- `delete:` codice morto, flessibilità inutilizzata, feature speculativa. Sostituzione: niente.
- `stdlib:` cosa fatta a mano che la libreria standard offre. Nomina la funzione.
- `native:` dipendenza o codice che fa ciò che la piattaforma fa già. Nomina la funzionalità.
- `yagni:` astrazione con una implementazione, config che nessuno imposta, layer con un chiamante.
- `shrink:` stessa logica, meno righe. Mostra la forma più corta.

## Caccia

Dipendenze che la stdlib o la piattaforma già offrono, interface a implementazione singola,
factory con un prodotto, wrapper che solo delegano, file che esportano una
cosa, flag e config morte, stdlib rifatta a mano.

## Output

Una riga per finding, classificata: `<tag> <what to cut>. <replacement>. [path]`.
Chiudi con `net: -<N> lines, -<M> deps possible.` Niente da tagliare: `Lean already. Ship.`

## Confini

Scope: solo over-engineering e complessità. Bug di correttezza, buchi di sicurezza
e performance sono esplicitamente fuori scope. Rilinkiali a una revisione normale.
Elenca i finding, non applica niente. One-shot.
"stop ponytail-audit" o "normal mode" per ripristinare.
