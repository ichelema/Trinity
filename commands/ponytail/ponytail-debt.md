---
description: Raccogli i commenti ponytail in un ledger di debito tracciato
---

Raccogli ogni commento `ponytail:` in questo repository in un ledger di debito, così i rinvii non marciscano in 'later means never'. Fai grep dell'intero albero per i marker di commento (grep -rnE '(#|//) ?ponytail:' ., saltando node_modules/.git/build output). Una riga per marker, raggruppata per file: <file>:<line> — <what was simplified>. ceiling: <the limit named in the comment>. upgrade: <the trigger to revisit>. Segna come no-trigger ogni marker che non nomina né un percorso di upgrade né un trigger, quelli marciscono in silenzio. Termina con il conteggio dei marker e quanti mancano di un trigger. Se non ce n'è nessuno: 'No ponytail: debt. Clean ledger.' Solo report, non cambiare nulla.
