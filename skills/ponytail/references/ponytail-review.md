Revisiona i diff per complessità non necessaria. Una riga per finding: posizione, cosa
tagliare, cosa lo sostituisce. Il miglior esito di un diff è farlo più corto.

## Format

`L<line>: <tag> <what>. <replacement>.`, oppure `<file>:L<line>: ...` per
diff multi-file.

Tag:

- `delete:` codice morto, flessibilità inutilizzata, feature speculativa. Sostituzione: niente.
- `stdlib:` cosa fatta a mano che la libreria standard offre. Nomina la funzione.
- `native:` dipendenza o codice che fa ciò che la piattaforma fa già. Nomina la funzionalità.
- `yagni:` astrazione con una implementazione, config che nessuno imposta, layer con un chiamante.
- `shrink:` stessa logica, meno righe. Mostra la forma più corta.

## Esempi

❌ "Questa classe EmailValidator potrebbe essere più complessa del necessario, hai
considerato se tutte queste regole di validazione servono in questa fase?"

✅ `L12-38: stdlib: classe validator di 27 righe. "@" nell'email, 1 riga, la validazione vera è la mail di conferma.`

✅ `L4: native: moment.js importata per una chiamata di format. Intl.DateTimeFormat, 0 deps.`

✅ `repo.py:L88: yagni: AbstractRepository con una implementazione. Inlinala finché non ne esiste una seconda.`

✅ `L52-71: delete: retry wrapper attorno a una chiamata locale idempotente. Niente la sostituisce.`

✅ `L30-44: shrink: il loop manuale costruisce il dict. dict(zip(keys, values)), 1 riga.`

## Punteggio

Chiudi con l'unica metrica che conta: `net: -<N> lines possible.`

Se non c'è niente da tagliare, dì `Lean already. Ship.` e fermati.

## Confini

Scope: solo over-engineering e complessità. Bug di correttezza, buchi di sicurezza
e performance sono esplicitamente fuori scope. Rilinkiali a una revisione normale,
non a questa. Un singolo smoke test o un self-check
basato su `assert` è il minimo ponytail, non bloat, non segnalarlo mai per la cancellazione.
Non applica i fix, solo li elenca.
"stop ponytail-review" o "normal mode": ripristina lo stile di revisione verboso.
