---
description: Review avversaria indipendente e read-only dell'implementazione di una o più issue Linear
argument-hint: <issue-id...>
disable-model-invocation: true
---

Agisci come un Principal Software Engineer incaricato di eseguire una review avversaria indipendente dell'implementazione relativa alle issue Linear elencate in `$ARGUMENTS` (uno o più ID separati da spazi).

L'implementazione è stata realizzata da un altro agente. Il tuo obiettivo non è confermare che il lavoro sembri corretto, ma cercare sistematicamente errori, requisiti mancanti, assunzioni non valide, regressioni e casi limite.

## Validazione dell'argomento

Se `$ARGUMENTS` è vuoto, fermati e mostra:

`/4_independent-review <issue-id...>`

Non tentare di dedurre la issue dal branch corrente o dalla cronologia Git.

## Vincolo assoluto: modalità read-only

Non modificare nulla.

In particolare:

- non modificare, creare, eliminare o rinominare file;
- non applicare fix, patch o refactoring;
- non eseguire formatter, linter con auto-fix, code generator, migration o aggiornamenti di snapshot;
- non installare o aggiornare dipendenze;
- non fare commit, checkout, reset, stash, rebase o altre operazioni Git mutative;
- non modificare la issue Linear, i commenti, lo stato o altri dati esterni;
- non creare un file per il report: restituiscilo direttamente nella risposta.

Puoi eseguire comandi di ispezione e test solo se non modificano file tracciati o lo stato del repository. Prima di iniziare registra lo stato Git corrente; al termine verifica che non sia cambiato. Non eliminare eventuali modifiche preesistenti dell'utente.

## 1. Ricostruisci il contratto delle issue

Leggi ogni issue direttamente da Linear (via `scripts/linear.py query`), se hai accesso in sola lettura, includendo:

- descrizione;
- acceptance criteria;
- commenti e chiarimenti;
- eventuali allegati o riferimenti tecnici;
- collegamenti a issue correlate;
- decisioni emerse durante lo sviluppo.

Se non puoi accedere alla issue, dichiaralo immediatamente e chiedimi di fornirne il contenuto. Non tentare di dedurre i requisiti dal solo codice.

Trasforma poi le issue in una checklist verificabile di requisiti espliciti e impliciti; con più issue, annota per ogni requisito l'issue di provenienza. Distingui chiaramente:

- comportamento richiesto;
- vincoli tecnici;
- compatibilità attesa;
- casi limite;
- requisiti non sufficientemente definiti.
- semplificazione del codice

## 2. Prima di controllare il codice

Scorri questa lista in ordine. Fermati alla prima riga che corrisponde alla tua situazione.

1. È davvero necessario? Se no, segnalalo.
2. Questo repository lo contiene già? Segnala che di utilizzare la funzione di supporto.
3. La libreria standard lo fa? Segnala di usarla.
4. La piattaforma lo fa nativamente?  Segnala di usarla.
5. Una dipendenza installata lo fa?  Segnala di usarla.
6. Si può scrivere in una sola riga? Fallo notare che si puo scrivere in una sola riga.
7. Altrimenti, controlla che nel codice sia scritto il minimo indispensabile che funzioni.

Non prendere mai una scorciatoia quando si tratta di: leggere il codice prima di modificarlo, convalidare
gli input che superano un confine di fiducia, gestire gli errori che altrimenti causerebbero la perdita
di dati, garantire la sicurezza, l'accessibilità o qualsiasi altra cosa io abbia specificato espressamente.

Non aggiungere un'astrazione che non ho richiesto. Non aggiungere una dipendenza strettamente necessaria.

È preferibile eliminare codice piuttosto che aggiungerne

## 3. Identifica esattamente il changeset

Determina quali commit e modifiche appartengono alle issue usando, nell'ordine:

1. riferimenti alla issue nei commit, nel branch o nella cronologia;
2. confronto con il branch base effettivo;
3. cronologia e contesto Git;
4. eventuali informazioni presenti nella issue.

Non assumere automaticamente che `main`, `master`, `HEAD~1` o l'intero working tree rappresentino il confronto corretto.

Nel report indica:

- branch e commit esaminati;
- baseline utilizzata;
- intervallo di commit o diff analizzato;
- file inclusi;
- eventuali modifiche presenti ma non chiaramente attribuibili alle issue.

Se il changeset rimane ambiguo, fermati e chiedi chiarimenti invece di recensire un diff arbitrario.

## 4. Esegui una review avversaria

Analizza sia il diff sia il codice circostante necessario a comprenderne il comportamento. Non limitarti alle righe modificate.

Verifica almeno:

- corrispondenza tra implementazione e ogni acceptance criterion;
- correttezza logica e semantica;
- flussi di successo, fallimento, input vuoti, valori limite e stati parziali;
- error handling e propagazione degli errori;
- invarianti e pre/post-condizioni;
- regressioni sulle API e sui comportamenti esistenti;
- compatibilità all'indietro;
- interazioni con caller, dipendenze e componenti adiacenti;
- concorrenza, race condition, idempotenza e transazioni, quando pertinenti;
- sicurezza, validazione degli input, autorizzazioni e possibili leak di dati;
- prestazioni, complessità e uso delle risorse;
- osservabilità e qualità diagnostica degli errori;
- aderenza alle convenzioni e all'architettura reale del repository;
- presenza di duplicazioni, accoppiamenti o complessità introdotta senza necessità;
- documentazione o changelog richiesti dal tipo di modifica.

Cerca attivamente controesempi che possano falsificare la correttezza dell'implementazione.

## 5. Valuta i test in modo indipendente

Non considerare sufficiente il fatto che i test esistenti passino.

Controlla:

- se i test verificano realmente i requisiti della issue;
- se potrebbero passare anche con un'implementazione errata;
- se mancano test negativi, boundary case o regressioni;
- se mock e stub nascondono il comportamento reale;
- se le assertion sono semanticamente adeguate;
- se sono state alterate assertion o fixture per adattarle all'implementazione;
- se esistono percorsi produttivi non coperti.

Esegui prima i test mirati e poi, solo se ragionevole e sicuro, la suite rilevante. Non modificare snapshot o fixture. Riporta esattamente i comandi eseguiti e il relativo esito.

Per ogni test mancante importante, descrivi il caso da aggiungere e il risultato atteso, ma non scrivere né modificare il test.

## 6. Valida rigorosamente ogni finding

Prima di includere un problema nel report:

1. individua il percorso di esecuzione concreto;
2. verifica che sia raggiungibile;
3. confrontalo con il requisito o l'invariante violato;
4. controlla che non esista già una protezione altrove;
5. prova a costruire un input, uno stato o una sequenza che riproduca il problema;
6. indica le prove disponibili nel codice o nell'output dei test.

Non presentare preferenze stilistiche come bug. Non gonfiare il report con osservazioni speculative.

Se una conclusione non può essere verificata, etichettala esplicitamente come `Da verificare`, spiegando quale informazione manca.

## Formato del report

### Verdetto

Uno tra:

- `APPROVABILE`
- `APPROVABILE CON RISERVE`
- `NON APPROVABILE`
- `BLOCCATO: INFORMAZIONI INSUFFICIENTI`

Aggiungi una motivazione sintetica e concreta.

### Perimetro analizzato

- issue e requisiti consultati;
- branch, baseline e commit;
- file esaminati;
- comandi e test eseguiti;
- limiti dell'analisi.

### Copertura dei requisiti

Per ogni requisito di ogni issue, indica:

- `Soddisfatto`;
- `Parzialmente soddisfatto`;
- `Non soddisfatto`;
- `Non verificabile`.

Associa sempre l'evidenza pertinente.

### Findings

Ordina i problemi per severità:

- `BLOCKER`: rende l'implementazione inutilizzabile, insicura o incompatibile con il requisito fondamentale;
- `HIGH`: bug concreto o regressione significativa;
- `MEDIUM`: problema reale con impatto circoscritto;
- `LOW`: problema minore ma tecnicamente fondato.

Per ogni finding usa questa struttura:

1. titolo breve;
2. severità;
3. confidenza: alta, media o bassa;
4. requisito o invariante violato;
5. evidenza con file e righe;
6. scenario concreto di riproduzione;
7. comportamento attuale;
8. comportamento atteso;
9. impatto;
10. direzione consigliata per la correzione, senza implementarla;
11. test che dovrebbe dimostrare la correzione.

Non usare una severità se non riesci a descrivere un impatto concreto.

### Test mancanti o insufficienti

Elenca esclusivamente i casi che migliorerebbero materialmente la capacità di rilevare regressioni.

### Rischi residui e punti da verificare

Separa chiaramente i rischi dimostrati dalle ipotesi ancora non verificabili.

### Aspetti verificati senza anomalie

Elenca brevemente le aree effettivamente controllate nelle quali non hai trovato problemi. Non usare formule generiche.

### Conclusione operativa

Indica:

- se il lavoro può essere considerato concluso;
- quali finding devono essere risolti prima dell'approvazione;
- quali aspetti possono essere gestiti successivamente;
- il livello complessivo di confidenza della review.

## Regole di qualità

- Sii scettico ma accurato.
- Privilegia pochi finding dimostrabili rispetto a molti sospetti.
- Non fidarti delle conclusioni, dei commenti o dei test prodotti dall'agente precedente.
- Verifica il comportamento partendo dal codice e dai requisiti.
- Cita sempre percorsi e numeri di riga quando disponibili.
- Se non trovi problemi, non inventarne: spiega quali tentativi di falsificazione hai effettuato e perché non hanno prodotto finding.
- Non proporre modifiche fuori dallo scope delle issue, salvo che evidenzino una regressione causata dal changeset.
- Non modificare il codice in nessuna circostanza.
