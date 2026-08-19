---
description: Revisione delle modifiche per over-engineering, cosa si può cancellare
---

Rivedi le modifiche di codice correnti solo per over-engineering, non per correttezza. Una riga per finding: L<line>: <tag> <what to cut>. <replacement>. Tag: delete (codice morto/feature speculativa), stdlib (libreria standard reinventata), native (dipendenza che fa ciò che la piattaforma già fa), yagni (astrazione con una sola implementazione), shrink (stessa logica, meno righe). Termina con il totale delle righe rimovibili. Se non c'è nulla da tagliare: 'Lean already. Ship.'
