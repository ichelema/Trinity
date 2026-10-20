Ogni scorciatoia ponytail deliberata è marcata con un commento `ponytail:` o `shortcut:` che
nomina il suo tetto e il percorso di upgrade.
Questo li raccoglie in un ledger unico così un rinvio non può diventare silenziosamente
permanente.

## Scansione

Fai grep del repo per i marker di commento, saltando `node_modules`, `.git` e l'output di build:

`grep -rnE --exclude-dir=.git --exclude-dir=node_modules --exclude-dir=dist --exclude-dir=build '(#|//|/[*]) ?(shortcut|ponytail):' .`  (aggiungi altri prefissi di commento se il tuo stack li usa)

Se l'utente nomina una sua parola marker (`/trinity:ponytail:ponytail-debt TODO`), fai grep di
quella parola.

Ogni hit è una riga del ledger. Il prefisso del commento tiene fuori dal ledger la prosa che
menziona solo la convenzione. Salta gli hit che non sono un rinvio, come una nota su una
scorciatoia da tastiera.

## Output

Una riga per marker, raggruppata per file:

`<file>:<line>, <what was simplified>. ceiling: <the limit named>. upgrade: <the trigger to revisit>.`

La convenzione è `ponytail: <ceiling>, <upgrade path>`, quindi estrai il tetto e il trigger
direttamente dal commento. Vuoi un owner per ogni riga? aggiungi `git blame -L<line>,<line>`.

Segnala il rischio di rot: ogni commento marker che non nomina un percorso di upgrade o un
trigger riceve un tag `no-trigger`, sono quelli che marciscono in silenzio.

Chiudi con `<N> markers, <M> with no trigger.` Niente trovato: `No shortcut debt. Clean ledger.`

## Confini

Legge e riporta solo, non cambia niente. Per persistirlo, chiedi e scrive il ledger su un file
(es. `PONYTAIL-DEBT.md`). One-shot: non cambia alcuna modalità.
