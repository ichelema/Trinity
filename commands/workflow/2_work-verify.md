---
description:
  Facoltativo: verifica end-to-end che il codice della PR di una o più issue Linear funzioni,
  eseguendo l'app e osservandone il comportamento; da usare prima della review
argument-hint: <issue-id...> <model>
disable-model-invocation: true
---

Verifica che il codice della PR delle issue indicate faccia davvero quello che deve: compila e
avvia l'app, portala dove gira il codice cambiato e cattura quello che vedi. La cattura è la prova;
nient'altro lo è.

È un passo facoltativo: usalo dopo `/2_work-issue` o `/2_work-simplify` e prima della review. Non
corregge niente: osserva e riporta.

- **Non lanciare test e non fare typecheck.** Li eseguono già `/2_work-issue`, `/2_work-simplify`
  e la review: qui dimostrerebbero solo che sai rieseguire la CI.
- **Non importare e chiamare funzioni interne** (`import ./src/...` e poi stampa del risultato): è
  un test unitario scritto da te, e l'app non ha mai girato. Chi chiama quella funzione finisce in
  una CLI, in un socket o in una finestra: vai lì.

Il modello qui serve solo a identificare il worktree corretto, non a scegliere il modello di
esecuzione.

## Validazione degli argomenti

Dividi `$ARGUMENTS` in token separati da spazi:

- l'ultimo token è il modello;
- i token precedenti sono gli issue ID (almeno uno).

Se i token sono meno di 2, fermati e mostra:

`/trinity:workflow:2_work-verify <issue-id...> <model>`

## Localizzazione del worktree e della PR

Ricava `<wt-path>` e `<branch>` con la regola di `/2_work-issue` («Localizzazione del worktree»):
`git worktree list --porcelain`, entry il cui branch termina esattamente con `/<base-name>`. Se non
esiste, fermati. Usa sempre `git -C "<wt-path>"`, `mise -C "<wt-path>"` e path assoluti sotto
`<wt-path>`.

Verifica prima di iniziare:

```bash
git -C "<wt-path>" rev-parse --abbrev-ref HEAD       # deve essere <branch>
git -C "<wt-path>" status --short                    # deve essere vuoto
git -C "<wt-path>" fetch origin
git -C "<wt-path>" rev-parse HEAD "origin/<branch>"  # i due SHA devono coincidere
gh pr view "<branch>" --json url,baseRefName,title,body
```

Se il working tree non è pulito, se gli SHA differiscono o se la PR non esiste, fermati e mostralo:
verificheresti codice diverso da quello della PR. Dalla PR ricavi la base `<base>` (`baseRefName`)
e la dichiarazione, cioè cosa la PR dice di fare (titolo e corpo). Se `gh` non risponde, usa come
base il branch di default, ricavato come in `/2_work-issue` («Pull Request»).

### Entrata e permanenza nel worktree

Dopo le verifiche iniziali, se non sei già nel worktree, usa `EnterWorktree` con `path: "<wt-path>"`
per entrare nel worktree **già esistente**. Non creare altri worktree e non cambiare branch.
Verifica che la directory di lavoro attiva sia `<wt-path>` e che il branch corrisponda a `<branch>`.
Se `EnterWorktree` non è disponibile o fallisce, non considerare un semplice `cd` equivalente:
fermati e segnala il problema.

Rimani nel worktree durante l'intera verifica, comprese catture, pulizia e l'eventuale domanda
all'utente sul salvataggio della ricetta. Una domanda o un errore recuperabile non sono di per sé
un motivo per uscire. Prima di lasciare un'esecuzione definitivamente interrotta, arresta i
processi avviati e pulisci le risorse temporanee che puoi rimuovere in sicurezza.

### Uscita dal worktree

Usa `ExitWorktree` con `action: "keep"` solo quando il lavoro di questo comando è davvero
concluso, **dopo** l'eventuale salvataggio della ricetta e il relativo commit/push:

- **Esecuzione autonoma:** esci prima di consegnare il report conclusivo.
- **Catena `auto` coordinata da `issue-cycle.md`:** non uscire al termine di questo singolo step;
  lascia la sessione nel worktree per gli step successivi. L'uscita è responsabilità del
  coordinatore della catena, prima di eventuali operazioni di rimozione del worktree.

Non eliminare il worktree: `keep` ne conserva branch, file e directory.

Non modificare, creare o cancellare file nel worktree e non fare commit, salvo il salvataggio della
ricetta descritto nel report. File di appoggio, log e catture vanno in una cartella temporanea fuori
dal worktree, sotto `~/.claude/tmp/` (`mktemp -d "$HOME/.claude/tmp/verify.XXXXXX"`): Blast Radius
lascia cancellare senza conferma solo lì.

## 1. Perimetro

```bash
git -C "<wt-path>" log --oneline "origin/<base>"..HEAD
git -C "<wt-path>" diff "origin/<base>"...HEAD --stat
```

Guarda quanti commit contiene la PR. Il diff è la verità; la descrizione della PR è una
dichiarazione sul diff. Leggili entrambi: se non coincidono in modo sostanziale, è un problema da
riportare nella tabella.

## 2. Superficie

La superficie è il punto in cui un utente, persona o programma, incontra la modifica. Lì osservi.

| La modifica arriva a | Superficie | Cosa fai |
|---|---|---|
| CLI / TUI | terminale | lanci il comando, catturi il pannello |
| Server / API | socket | mandi la richiesta, catturi la risposta |
| GUI | pixel | la guidi con Playwright o xvfb, fai uno screenshot |
| Libreria | confine del pacchetto | codice d'esempio con l'export pubblico, non con `./src/...` |
| Prompt / configurazione di un agente | l'agente | esegui l'agente, catturi il comportamento |
| Workflow CI | Actions | lanci il workflow, leggi l'esecuzione |

Una funzione interna non è una superficie: segui chi la chiama fino a una delle righe sopra. I test
nel diff sono le prove dell'autore, non una superficie; puoi leggerli per capire cosa controllare.

Senza superficie (solo documentazione, solo tipi, solo test, configurazione di build senza effetti
sul comportamento) il verdetto è `SKIP`, con il motivo in una riga. Non riempire il vuoto con i
test.

## 3. Come avviare l'app

Cerca prima le skill del progetto, alla radice di `<wt-path>` e nelle directory toccate dal diff:
`.claude/skills/verifier-*`, `.claude/skills/run-*` e `.claude/skills/verify/`. Usa quella che
corrisponde alla superficie. Una skill che fallisce per motivi estranei alla modifica non è un
`FAIL` della modifica: segnalalo.

Senza skill, parti da README, `mise.toml`, `package.json` o `Makefile`, con un limite di circa 15
minuti. Se non ci arrivi, il verdetto è `BLOCKED`: indica dove ti sei fermato. Se ci arrivi, metti
nel report la ricetta che ha funzionato: comandi di build e avvio, flussi da guidare, trappole.

## 4. Guida l'app

Scegli il percorso più breve che fa eseguire il codice cambiato: un flag cambiato si lancia con il
flag, un handler cambiato si chiama sulla sua route, una gestione d'errore cambiata si prova
provocando l'errore.

Rileggi il piano prima di eseguirlo: se ogni passo è build, typecheck o test, hai pianificato un
giro di CI, non una verifica. Trova un passo che arriva alla superficie oppure dai `BLOCKED`.

Passa dall'interfaccia reale, end-to-end: se gli utenti cliccano bottoni, clicca bottoni.

Isola lo stato che condividi con l'host: sessione tmux dedicata (`tmux -L <nome>`), porte libere,
cartelle temporanee sotto `~/.claude/tmp/`.

Se la modifica tocca codice che cancella, pubblica, invia o scrive fuori dal workspace e non c'è un
dry-run o un bersaglio sicuro, non eseguirlo dal vivo: verifica quello che puoi intorno e scrivi
quale percorso non hai eseguito e perché.

## 5. Prova i bordi

Confermare la dichiarazione è solo la prima metà. Sulla stessa superficie prova i dintorni della
modifica, scegliendo quelli che la modifica suggerisce:

- flag o opzione nuova: valore vuoto, passata due volte, insieme a un flag in conflitto, scritta
  male (l'errore la nomina?);
- handler o route nuova: metodo sbagliato, body malformato, campo obbligatorio mancante, payload
  troppo grande;
- percorso d'errore cambiato: gli errori vicini che il diff non tocca;
- interfaccia interattiva o TUI: Ctrl-C a metà operazione, resize, testo spazzatura incollato,
  tasto premuto a raffica, Esc nel momento sbagliato;
- stato e persistenza: due volte di seguito, con stato vecchio sotto, in due sessioni insieme;
- dintorni: cosa c'è vicino, cosa ti è sembrato strano mentre confermavi.

Se la superficie è raggiungibile, fai almeno una prova ai bordi.
Contala nel report anche se il comportamento osservato è corretto.

## 6. Cattura e pulizia

Cattura output, risposte, screenshot e contenuto del pannello: la prova è la cattura, non la
memoria. Un comportamento inatteso non si aggira: catturalo e decidi se dipende dalla modifica o
dall'ambiente. Un guasto non collegato alla modifica entra nei Problemi solo se è `CRITICO`.

Alla fine ferma i processi che hai avviato (server, sessioni tmux), cancella le cartelle temporanee
e controlla che `git -C "<wt-path>" status --short` sia vuoto. Non uscire ancora: potrebbe essere
necessario salvare la ricetta descritta nel report. Segui la sezione «Uscita dal worktree» dopo
aver concluso anche quell'eventuale operazione.

## Report finale

Il report lo legge una persona che deve capire in pochi secondi se la modifica funziona e cosa
fare. Mostra solo ciò che non va: le prove riuscite si contano, non si elencano.

**Prima riga**: il verdetto in grassetto e una frase. Niente prima del verdetto, né il metodo né
la skill usata.

- `PASS` — quale comportamento hai verificato sull'app in esecuzione.
- `FAIL` — il problema più grave: cosa ti aspettavi e cosa è successo invece.
- `BLOCKED` — dove ti sei fermato e cosa serve per riprovare.
- `SKIP` — perché non c'è una superficie da eseguire. Basta questa riga.

**Seconda riga**, se hai provato l'app: `<n> prove, <k> ok, <m> con problemi` e il metodo in poche
parole (skill di progetto o avvio da zero). Build, installazione, checkout, test e typecheck non
sono prove dell'app e non entrano nel conteggio.

**Problemi**, solo con `FAIL`: una riga per prova con un problema, prima i `CRITICO`.

| # | Gravità | Problema | Prova |
| --- | --- | --- | --- |
| 1 | `CRITICO` | Cosa non va, in una frase | Azione → risultato osservato, in breve |

- `CRITICO`: la dichiarazione principale della issue non è rispettata, oppure la modifica rompe
  qualcosa che prima funzionava, causa un crash, una perdita di dati o un problema di sicurezza.
- `FALLITO`: comportamento diverso dall'atteso senza quelle conseguenze. Un difetto che c'era già
  prima della modifica entra solo se la modifica lo tocca o lo rende più visibile: scrivi «già sul
  branch base» nel Problema.

Ogni cella sta su una riga: niente confronti lunghi, né byte, conteggi o valori che non servono a
capire il problema. Se un problema ha bisogno della cattura grezza (per esempio un output
ambiguo), mettila sotto la tabella in un blocco di codice, al massimo una decina di righe per
problema, invece di dare solo un path locale.

Le prove riuscite e i casi limite corretti non vanno né nella tabella né altrove: bastano nel
conteggio della seconda riga.

**Non verificato**: una riga con ciò che non hai potuto provare e il motivo (per esempio nessun
display), solo se c'è.

**Ricetta**: solo se hai avviato l'app senza skill di progetto: comandi di build e avvio, flussi
provati e trappole da evitare.

Nient'altro: niente osservazioni generiche e niente proposte di correzione con alternative tra
cui scegliere. Questo comando osserva, non corregge.

Verdetti:

- `PASS`: hai eseguito l'app e la modifica fa quello che deve sulla sua superficie. Non basta che i
  test passino o che il codice sembri giusto.
- `FAIL`: l'hai eseguita e non lo fa, oppure rompe altro, oppure diff e dichiarazione non
  coincidono in modo sostanziale.
- `BLOCKED`: non sei arrivato a uno stato in cui la modifica è osservabile (build rotta, dipendenza
  mancante, app che non parte). Non è un giudizio sulla modifica: indica dove ti sei fermato.
- `SKIP`: non esiste una superficie da eseguire.

Niente pass parziali: «3 su 4» è `FAIL` finché il quarto non passa o non è spiegato. Nel dubbio,
`FAIL`: un falso `PASS` porta in produzione codice rotto, un falso `FAIL` costa solo un altro
sguardo. Un output ambiguo è `FAIL`, con la cattura grezza allegata.

Se hai scritto una ricetta, chiedi all'utente se salvarla: con un sì, scrivila in
`<wt-path>/.claude/skills/verify/SKILL.md`, poi fai un commit separato e il push sul branch della
PR, così le prossime verifiche partono da lì. Senza risposta (sessione headless o subagente) non
salvarla.

Dopo la decisione sulla ricetta e ogni eventuale commit/push, verifica di nuovo lo stato Git e
applica la sezione «Uscita dal worktree»: in esecuzione autonoma esci con `ExitWorktree` e
`action: "keep"`; in una catena `auto` rimani nel worktree per lo step successivo.

Chiudi il report con la riga **Prossimo passo**: con `PASS` o `SKIP`,
`/trinity:workflow:3_independent-review <issue-id...> <model>` oppure
`/trinity:workflow:4_review-fix-loop <issue-id...> <model>`; con `FAIL`, correggi prima della
review, partendo dal problema #1; con `BLOCKED`, sistema l'ambiente o la ricetta e rilancia. Se
devi chiedere se salvare la ricetta, la domanda è l'ultima riga, dopo il prossimo passo.
