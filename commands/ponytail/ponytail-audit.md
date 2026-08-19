---
description: Audit dell'intero repo per over-engineering, cosa si può cancellare
---

Audita l'intero repository solo per over-engineering, non per correttezza. Scansiona l'intero albero, non un diff. Una riga per finding, in ordine dal taglio più grande: <tag> <what to cut>. <replacement>. [path]. Tag: delete (codice morto/feature speculativa), stdlib (libreria standard reinventata), native (dipendenza che fa ciò che la piattaforma già fa), yagni (astrazione con una sola implementazione), shrink (stessa logica, meno righe). Termina con il totale delle righe e delle dipendenze rimovibili. Se non c'è nulla da tagliare: 'Lean already. Ship.'
