Ogni scorciatoia ponytail deliberata è marcata con un commento `ponytail:` che nomina
il suo tetto e il percorso di upgrade. Questo li raccoglie in un ledger unico così un rinvio
non può diventare silenziosamente permanente.

## Scansione

Fai grep del repo per i marker di commento, saltando `node_modules`, `.git` e l'output
di build:

`grep -rnE '(#|//) ?ponytail:' .`  (aggiungi altri prefissi di commento se il tuo stack li usa)

Ogni hit è una riga del ledger. Il prefisso del commento tiene fuori dal ledger la prosa che
menziona solo la convenzione.

## Output

Una riga per marker, raggruppata per file:

`<file>:<line>, <what was simplified>. ceiling: <the limit named>. upgrade: <the trigger to revisit>.`

La convenzione è `ponytail: <ceiling>, <upgrade path>`, quindi estrai il tetto
e il trigger direttamente dal commento. Vuoi un owner per ogni riga? aggiungi
`git blame -L<line>,<line>`.

Segnala il rischio di rot: ogni commento `ponytail:` che non nomina un percorso di upgrade o
trigger riceve un tag `no-trigger`, sono quelli che marciscono in silenzio.

Chiudi con `<N> markers, <M> with no trigger.` Niente trovato: `No ponytail: debt. Clean ledger.`

## Confini

Legge e riporta solo, non cambia niente. Per persistirlo, chiedi e scrive il
ledger su un file (es. `PONYTAIL-DEBT.md`). One-shot. "stop ponytail-debt" o
"normal mode" per ripristinare.
