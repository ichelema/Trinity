Fai l'audit dell'intero repo come lo sviluppatore senior che lo ha appena ereditato e sarà
chiamato quando si rompe. Ordine di importanza: corretto, sicuro, regge il carico, testato,
veloce, snello. Snello conta ancora: ogni riga in più va letta, testata e corretta più avanti.
Questo è un report che l'utente ha chiesto, quindi dallo per intero.

## 1. Prima la mappa

- Fai l'audit di ciò che l'utente nomina: una cartella, un package, o l'intero repo. Niente di
  nominato: l'intero repo.
- Leggi il README, la config di deploy e di build, la lista delle dipendenze, i punti di ingresso
  (main, route, handler, job, comandi CLI) e i test.
- Trova il carico atteso: una persona che lancia uno script, oppure molti utenti e processi
  insieme. Giudica la scala su quello e di' quale carico hai assunto.
- Traccia i flussi principali da un capo all'altro: dove entrano i dati, cosa viene salvato, cosa
  esce. Leggi per intero quei percorsi: input degli utenti, soldi, auth, scritture di dati, job in
  background, tutto ciò che è condiviso tra processi.
- Repo grande: vai in profondità dove un errore costa di più, non file per file. Di' quali parti
  non hai letto.

## 2. Cerca

1. **Bug:** risultato sbagliato, crash, caso limite mancato (vuoto, zero, ultimo elemento,
   arrotondamenti, fusi orari), chiamanti che non concordano con ciò che una funzione ritorna, la
   stessa regola applicata in modo diverso in due posti.
2. **Rischio:** buchi di sicurezza (injection, casualità debole, segreti nel codice, controlli
   mancanti sull'input degli utenti), perdita di dati (errori ingoiati, scritture nell'ordine
   sbagliato, nessuna transazione).
3. **Scala:** va bene per un utente, sbagliato per molti: race check-then-write, lo stesso lavoro
   fatto da ogni processo, memoria o liste che solo crescono, una query per elemento, O(n^2) su
   input grandi, stato per-processo che va condiviso.
4. **Test mancante:** logica a rischio (un branch, un parser, soldi, sicurezza, scritture di
   dati) senza un test che fallisce quando si rompe. Un buon test, non copertura.
5. **Velocità:** i grossi rallentamenti sono problemi. Le piccole vittorie (lavoro ripetuto in un
   hot loop) sono suggerimenti; certo software conta ogni millisecondo.
6. **Snello:** codice che non dovrebbe esistere o dovrebbe essere più piccolo.
   - delete: codice morto, opzioni, flag e config inutilizzati, feature speculative
   - reuse: due helper che fanno la stessa cosa (tienine uno, nomina il path)
   - stdlib / native: la libreria standard o la piattaforma lo fanno già; una dipendenza che fa
     ciò che poche righe o la piattaforma possono fare
   - yagni: interface con una implementazione, factory con un prodotto, wrapper che solo passa le
     chiamate
   - merge: quasi-copie che devono cambiare insieme
   - split: una funzione o classe che fa più lavori non correlati, quindi difficile da leggere o
     testare. Dividi per lavoro, mai per numero di righe, e mai in helper che esistono solo per
     accorciare una funzione.

## 3. Controlla prima di riportare

- Ogni finding richiede un caso concreto: "questo input o questa situazione porta a questo
  risultato sbagliato". Niente caso, niente finding.
- Prima di dire che il codice è inutilizzato, fai grep dell'intero albero, compresi test,
  fixture, config e riferimenti come stringa o dinamici.
- Una scorciatoia marcata con un commento `ponytail:` (o `shortcut:`, la forma neutra più
  recente) che nomina il suo limite è una decisione, non un finding, a meno che il carico atteso
  non lo superi già.
- Proponi la correzione più piccola che funziona. Preferisci le correzioni che cancellano codice.
  Non aggiungere mai layer, framework o config di cui il problema non ha bisogno.
- Niente gusti di stile, niente "valuta", niente preoccupazioni vaghe.

## 4. Output

Italiano molto semplice: frasi corte, parole di tutti i giorni. Spiega un termine tecnico la
prima volta che lo usi. Chi legge potrebbe non aver mai visto questo codice.

Inizia con `Cosa fa questo repo:` in due o tre frasi, e il carico che hai assunto.

Poi i finding in tre gruppi, i più importanti per primi, salta i gruppi vuoti:
- **Da correggere subito:** bug, sicurezza, perdita di dati, si rompe al carico atteso.
- **Da correggere:** codice a rischio senza test, lentezza reale, duplicazione, una funzione che
  mescola lavori, codice che non dovrebbe esistere.
- **Bello da avere:** piccoli aumenti di velocità, forme più corte.

Numera i finding attraverso tutti i gruppi, così l'utente può dire "correggi 2 e 5". Al massimo
20 finding; se ne hai lasciati fuori di più piccoli, di' quanti.
Ogni finding ha tutte e quattro le parti, ciascuna di una o due frasi corte:

2. **Gli ordini finiscono nel giorno sbagliato** (`billing/close_day.py:L40-52`)
   - **Cos'è:** A mezzanotte questo job chiude il giorno e fattura tutti gli ordini di quel giorno.
   - **Problema:** Prende "oggi" dall'orologio del server, che gira in UTC. Un ordine fatto alle
     00:30 a Berlino viene fatturato il giorno prima.
   - **Correzione:** Calcola il giorno una volta nel fuso orario del negozio:
     `datetime.now(ZoneInfo("Europe/Berlin")).date()`. Una riga, nient'altro cambia.
   - **Se lo saltiamo:** Gli ordini tardivi mostrano la data sbagliata e la contabilità li
     corregge a mano.

Chiudi con:
- `Verdetto:` una riga: sano, oppure cosa correggere per primo.
- `Snello: -<N> righe, -<M> dipendenze possibili.` quando esistono finding di tipo snello.
- `Non controllato:` le parti che non hai letto o non hai potuto eseguire.

Niente trovato: `Cosa fa questo repo:`, poi `Sano. Niente da correggere.` e una riga su cosa hai
controllato.

Report one-shot, non cambia codice.
