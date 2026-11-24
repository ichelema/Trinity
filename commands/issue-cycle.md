---
description:
  Ciclo completo e senza presidio di una o più issue Linear, una dopo l'altra; per ogni issue
  worktree, implementazione fino alla PR, semplificazione, verifica, review singola o loop di review
  e fix, pulizia dei worktree di review e commento su Linear; alla fine report. Non fa il merge.
argument-hint: <review|loop> <source-branch> <issue-id...> [<model>]
disable-model-invocation: true
---

Porta le issue Linear indicate dal worktree fino alla PR recensita e corretta, eseguendo per ogni
issue gli step di `${CLAUDE_PLUGIN_ROOT}/commands/workflow/`. Gli step hanno
`disable-model-invocation: true`: non puoi invocarli come slash command. Per ogni step leggi il
file e seguilo con gli argomenti indicati qui al posto di `$ARGUMENTS`.

Il merge resta all'utente: questo command non lo fa mai.

## Gestione della sessione e del worktree

Questo command è il **coordinatore**: i comandi degli step vengono letti e seguiti nella
stessa sessione, non invocati come nuove sessioni Claude Code. Le istruzioni di uscita
standalone presenti nei singoli step non si applicano mentre questo coordinatore è attivo.

- Per ogni issue, individua il worktree esistente con `git worktree list --porcelain` e la
  regola di localizzazione di `2_work-issue.md`. Non crearne un secondo per entrarci.
- Prima dello step 2, una volta concluse le verifiche preliminari, usa
  `EnterWorktree` con `path: "<wt-path>"` **solo se la sessione non è già entrata** in
  quel worktree. Se il ciclo è stato avviato da `2_work-issue auto`, riutilizza
  l'ingresso attivo. Non usare `cd` come sostituto dell'ingresso di sessione.
- Rimani nel worktree di implementazione per gli step 2, 2b, 2c e 3/4, compresi
  i fix e i passaggi tra step. I reviewer lavorano nei propri worktree detached
  attraverso path assoluti; **la sessione principale non vi entra**.
- Le operazioni di pulizia dei worktree detached dello step 5 non devono
  rimuovere né far abbandonare il worktree di implementazione.
- Alla fine di **ogni issue**, anche se interrotta, termina i processi avviati
  per quell'issue e usa `ExitWorktree` con `action: "keep"` **se la sessione ha
  un ingresso `EnterWorktree` attivo**. Conserva worktree, branch e modifiche.
  Verifica che la sessione sia tornata alla directory di partenza prima di
  iniziare l'issue successiva. Non usare `pwd` o `cd` come surrogato di
  `ExitWorktree`.
- Quando la sessione non è stata aperta con `EnterWorktree` (per esempio sessione
  già avviata dal terminale direttamente nel worktree), `ExitWorktree` non
  garantisce un cambio di directory. In questo caso non considerare l'uscita
  riuscita: segnala il limite, interrompi l'esecuzione multi-issue se non puoi
  ripristinare in modo verificabile il contesto corretto e non eliminare il
  worktree attivo.
- Se `EnterWorktree` o `ExitWorktree` non sono disponibili, non fingere che `cd`
  ne riproduca il comportamento. Annota `[interruzione]` e non passare a un'altra
  issue senza aver ripristinato un contesto sicuro.

Questa uscita è **solo una disattivazione del contesto di sessione**, non lo step
`5_remove-worktree`: il worktree di implementazione sarà rimosso soltanto dopo
il merge, su richiesta dell'utente.


## Uso

```
/trinity:issue-cycle review master ICH-170              # una issue, review singola, modello opus
/trinity:issue-cycle loop master ICH-97 ICH-98          # due issue in serie, loop review e fix
/trinity:issue-cycle loop master ICH-97 ICH-98 fable    # modello esplicito
```

## Esecuzione senza presidio

L'utente lancia questo command e non è davanti al PC: nessuno può rispondere. Le regole di questa
sezione hanno la precedenza su ogni «chiedi» e «attendi» degli step, anche quando un «fermati» li
precede. Un «fermati» senza richiesta all'utente resta valido, con due precisazioni:

- interrompe solo il ciclo della issue corrente, come un caso grave;
- le condizioni di uscita del loop dello step 4 chiudono il loop, non il ciclo: prosegui con lo
  step 5.

«Fermati alla prima riga» nelle liste «Prima di scrivere il codice» non è uno stop: indica come
leggere la lista.

- Non usare `AskUserQuestion` e non chiudere il turno per aspettare una risposta.
- Quando uno step dice di chiedere, scegli l'opzione più prudente e dentro lo scope della issue,
  annotala come `[decisione]` con il motivo e prosegui. Non sostituire mai un consenso
  esplicito a scartare lavoro o cancellare branch: senza quel consenso non procedere.
- Dubbi, specifiche ambigue, problemi non risolti e finding non fixati non fermano il ciclo:
  annotali come `[questione]`.

Oltre agli stop espliciti degli step, interrompi la issue in questi casi gravi:

1. il lavoro richiede modifiche fuori dal perimetro della issue (altri moduli, architettura,
   dipendenze nuove, dati esterni diversi dalla issue);
2. il passo successivo è distruttivo o irreversibile e gli step non lo prevedono: perdita di
   modifiche non committate, `--force`, `-D`, `reset --hard`, cancellazione di branch remoti;
3. la sicurezza è a rischio: segreti nel codice o nei log, permessi, credenziali;
4. lo stato Git non è quello atteso e proseguire può danneggiare lavoro altrui (worktree o branch
   già esistenti, working tree sporco, SHA della PR diverso);
5. la verifica dello step 2c dà `FAIL`: recensire codice che non funziona spreca la review.

Dopo un'interruzione non modificare più i file né lo stato Git del worktree di quella issue:
annota lo step raggiunto, il motivo e il comando del singolo step che permette di riprendere.
Esegui comunque la pulizia dei processi e l'uscita di sessione prevista in «Gestione della sessione
e del worktree». Passa alla issue seguente solo se l'uscita è riuscita e il contesto è sicuro.

## Validazione degli argomenti

Dividi `$ARGUMENTS` in token separati da spazi:

- il primo token è la modalità di review: `review` (step 3) oppure `loop` (step 4);
- il secondo token è il source branch;
- gli issue ID sono i token successivi nella forma `<TEAM>-<numero>` (es. `ICH-97`), almeno uno;
- un token dopo l'ultimo issue ID è il modello; se manca, usa `opus`.

Se la modalità non è `review` o `loop`, se non c'è nessun issue ID o se resta un token non
classificato, fermati e mostra:

`/trinity:issue-cycle <review|loop> <source-branch> <issue-id...> [<model>]`

## Registro

Il registro è un file che conserva decisioni, questioni aperte ed esiti anche quando Claude Code
compatta la conversazione. Crealo subito dopo la validazione degli argomenti:

```bash
log_dir="$HOME/.claude/tmp/issue-cycle"; mkdir -p "$log_dir"
log="$(mktemp "$log_dir/$(date +%Y%m%d-%H%M)-<issue-id...>-XXXXXX.md")" || exit 1
printf '# issue-cycle %s %s %s\n' "<review|loop>" "<source-branch>" "<model>" > "$log"
```

Ogni «annota» di questo command significa: aggiungi subito una riga al registro, nel momento in cui
la decisione o il problema avviene, non alla fine. Una riga per voce, sotto l'intestazione della
issue corrente:

```
- [decisione] step <N>: <scelta> — <motivo>
- [questione] step <N>: <problema> (<file>:<riga> se disponibile)
- [interruzione] step <N>: <motivo> — riprendi con <comando>
- [fallito] step <N>: <operazione> — completa con <comando>
- [esito] PR <url>, semplificazione <n> fix, verifica <verdetto>, review <round> round, <n> fix,
  residui <severità e destinazione di ognuno>
```

Il tag decide dove la voce finisce nel report finale:

- `[decisione]`: una scelta presa al posto dell'utente che non blocca il merge. Finisce in «Da
  sapere», solo se l'utente può volerla cambiare.
- `[questione]`: un problema che l'utente deve guardare prima del merge. Rende la issue ⚠ e
  finisce in «Cosa fai ora».
- `[interruzione]` e `[fallito]`: finiscono in «Cosa fai ora» con il loro comando.

Aggiungi sempre in append (`cat >> "$log" <<'EOF' … EOF`), mai riscrivendo il file. Dopo una
compattazione della conversazione, rileggi il registro per sapere a quale issue e a quale step sei
arrivato.

## Controlli iniziali

Esegui questi controlli una volta sola, prima della prima issue.

### Scope delle issue

Leggi ogni issue con `${CLAUDE_PLUGIN_ROOT}/skills/linear/scripts/linear.py query`, in sola lettura.
Una issue che non richiede modifiche a un repository Git (configurazione di tool esterni, ricerca,
pulizia di Linear, note fuori dai repo) non entra nel ciclo: toglila dalla lista, non toccare il
suo stato e annotala sotto l'intestazione `## Escluse` con il motivo. Se non resta nessuna issue,
fermati.

### Modello di implementazione

`<model>` non sceglie il modello di esecuzione: come negli step, è l'etichetta del worktree e del
branch. L'implementazione la fa questa sessione, anche quando la delega a `trinity:implementer`:
l'agente eredita il modello della sessione. Se il modello della sessione non corrisponde a
`<model>`, prosegui e annotalo come `[decisione]`.

Se la sessione gira su Fable, annota come `[decisione]` che la review Fable gira sullo stesso modello che ha scritto
il codice ed è meno indipendente: conta il modello della sessione, non `<model>`. In `loop` questo
controllo sostituisce quello su `<model>` di `4_review-fix-loop.md`.

### Proxy LiteLLM (solo `loop`)

La review GPT dello step 4 usa il proxy LiteLLM:

```bash
curl -s -o /dev/null -w '%{http_code}' http://127.0.0.1:4000/health/liveliness   # deve essere 200
```

Se la risposta non è `200`, prosegui con la sola review Fable: per quella issue crea e rimuovi
solo il suo worktree, lancia solo quell'agente e usa solo il suo report, senza attendere GPT.
Annotalo come `[decisione]`. Ripeti il controllo
all'inizio della review di ogni issue: il proxy può partire o fermarsi durante il ciclo.

## Ciclo per issue

Lavora le issue in serie, nell'ordine ricevuto, una alla volta. Inizia la issue seguente solo
quando il ciclo della issue corrente è finito o interrotto. Non lanciare in parallelo step di issue
diverse.

Ogni issue ha il suo worktree, il suo branch e la sua PR, e parte da `<source-branch>`. Nei passi
sotto, `<issue-id>` è la issue corrente. Se la issue è bloccata da un'altra issue della lista, il
suo codice non è nel branch (nessun merge): applica la regola dello step 2 sulle dipendenze.

All'inizio di ogni issue aggiungi al registro l'intestazione `## <issue-id>`. Alla fine del ciclo,
anche dopo un'interruzione, aggiungi la riga `[esito]`.

Alla fine del ciclo, anche dopo un'interruzione, applica la procedura di uscita di
«Gestione della sessione e del worktree» usando `ExitWorktree(action: "keep")` quando
l'ingresso è attivo. Prima della issue seguente verifica il ritorno al contesto di
partenza e la disponibilità del repository corretto; non usare `cd` o il solo
output di `pwd` come prova dell'uscita di sessione.

### Step 1 — worktree

Leggi e segui `${CLAUDE_PLUGIN_ROOT}/commands/workflow/1_create-worktree.md` con
`<source-branch> <issue-id> <model>`. Se il prefisso è ambiguo, usa `improvments` e annotalo come
`[decisione]`.
Mostra la tabella finale senza la riga «Prossimo passo».

Dopo la creazione verifica che il nuovo worktree sia registrato da Git; poi, dopo le
verifiche richieste dallo step 2, entra con `EnterWorktree(path: "<wt-path>")` come
indicato nella sezione di gestione della sessione. Non entrare durante la creazione
con un semplice `cd`.

### Step 2 — implementazione e PR

Leggi e segui `${CLAUDE_PLUGIN_ROOT}/commands/workflow/2_work-issue.md` con `<issue-id> <model>`.
Con le regole senza presidio:

- mostra il piano e prosegui senza attendere l'ok;
- se la issue è bloccata da issue non completate, implementa solo la parte che non dipende dal
  blocco e annota il resto come `[questione]`;
- se le specifiche sono contrastanti, scegli l'interpretazione più conservativa e annotala come
  `[decisione]`;
- se i test falliscono e non riesci a correggerli dentro lo scope, apri comunque la PR, dichiaralo
  nella descrizione e annotalo come `[questione]`;
- se un subagente riporta una scelta aperta, interrompi la issue quando la scelta rientra in un
  caso grave; altrimenti scegli l'opzione più prudente dentro lo scope, annotala come
  `[decisione]` e fai completare il lavoro. Annota come `[decisione]` anche le deviazioni dal piano
  che l'utente può voler cambiare.

Della sezione «Non fare il merge» resta il divieto di merge, non lo stop standalone: si prosegue da qui
con gli step 2b e 2c, poi con la review eseguita da reviewer in contesti separati.
**Non eseguire l'uscita standalone di `2_work-issue`** alla fine di questo step.
Mostra la tabella finale senza la riga «Prossimo passo».

### Step 2b — semplificazione

Leggi e segui `${CLAUDE_PLUGIN_ROOT}/commands/workflow/2_work-simplify.md` con
`<issue-id> <model>`. Se i test sono rossi già prima di iniziare, salta lo step e annotalo come
`[questione]`: non è un'interruzione. Non uscire dal worktree al termine dello
step, anche se il file dello step prevede un'uscita standalone.

### Step 2c — verifica

Leggi e segui `${CLAUDE_PLUGIN_ROOT}/commands/workflow/2_work-verify.md` con `<issue-id> <model>`.
Non salvare la ricetta: lasciala nel report e annotala come `[decisione]`. Con `BLOCKED` annota il
verdetto come `[questione]` e prosegui: l'app non è stata provata. Con `SKIP` il verdetto va solo
nella riga `[esito]`. Con `FAIL` interrompi il ciclo della issue (caso grave 5).
Non eseguire l'uscita standalone di `2_work-verify`: la sessione resta nel worktree
fino alla conclusione del ciclo della issue.

### Step 3 o 4 — review

Non fare tu la review: hai scritto il codice, e il reviewer deve partire da un contesto pulito.

- `review`: tool Agent con `subagent_type: trinity:reviewer`. Nel prompt digli di leggere
  `${CLAUDE_PLUGIN_ROOT}/commands/workflow/3_independent-review.md` e di seguirlo con
  `<issue-id> <model>` al posto di `$ARGUMENTS`, con il formato completo del report. Il subagente
  crea e rimuove da sé il worktree di
  review. Sui finding del report applica le sezioni «Triage dei finding» e «Fix minimi e
  chirurgici» di `${CLAUDE_PLUGIN_ROOT}/commands/workflow/4_review-fix-loop.md`. Un solo round:
  dopo i fix non lanciare una nuova review. I fix si applicano nel worktree di
  implementazione già attivo, senza un nuovo `EnterWorktree` né un'uscita intermedia.
- `loop`: leggi e segui `${CLAUDE_PLUGIN_ROOT}/commands/workflow/4_review-fix-loop.md` con
  `<issue-id> <model>`. Un finding che non si risolve con un fix minimo va annotato come
  `[questione]`, non in una domanda. Il coordinatore mantiene attivo il worktree
  di implementazione fino al completamento della pulizia dello step 5.

Se un reviewer restituisce il verdetto `BLOCCATO: INFORMAZIONI INSUFFICIENTI`, quella review non
è avvenuta: non applicare fix sul suo report e annota come `[questione]` cosa manca.
Lo stesso vale se un agente atteso non consegna il report: la review resta incompleta.

### Step 5 — pulizia dei worktree di review

Non fare il merge e non rimuovere il worktree di implementazione: lo step 5 rifiuta un branch non
mergiato, e il merge resta all'utente.

Controlla con `git worktree list --porcelain` i path esatti dei worktree detached creati per
questa review. Non rimuovere residui preesistenti o di provenienza incerta: segnalali.
Per ciascun worktree residuo di questa esecuzione, leggi e segui
`${CLAUDE_PLUGIN_ROOT}/commands/workflow/5_remove-worktree.md` con `$worktree_name` = quel nome.
Cancella `<review-path>/.review-tmp/` solo se creata da questa review. Se restano file
di provenienza incerta, ignorati, non tracciati o modificati, non
rimuovere nulla e annotalo come `[fallito]`; mai `--force`.

Non chiamare `ExitWorktree` per cancellare un worktree di review: non è stato
attivato dalla sessione principale. Usa la rimozione Git prevista dallo step 5,
passando il path esatto. Terminata la pulizia dei review worktree, completa il
commento Linear e il registro. L'uscita dal worktree di implementazione
avviene **una sola volta**, nella chiusura del ciclo per issue descritta sopra,
con `ExitWorktree(action: "keep")`. Non rimuovere mai il worktree di
implementazione in questo ciclo.

### Commento su Linear

A fine ciclo, anche dopo un'interruzione, pubblica sulla issue un commento breve, nella lingua delle
issue del progetto Linear, con
`linear.py`, costruito dalle righe del registro sotto `## <issue-id>`: link della PR (se esiste),
esito di semplificazione, verifica e review, decisioni prese in autonomia, questioni aperte e, se
il ciclo è interrotto, lo step raggiunto e il motivo. Chiudi con
`Non mergiato: il merge resta all'utente.` oppure `Not merged: merge is left to the user.` Se la
pubblicazione fallisce, annotala come `[fallito]` con il comando che la ripete.

Regole Linear valide per tutto il ciclo:

- non spostare la issue in Done: senza merge il lavoro non è finito, e dopo il merge lo stato lo
  aggiorna l'automazione GitHub → Linear;
- non modificare titolo, parent, label o project della issue.

## Report finale

Stampalo dopo l'ultima issue. Costruiscilo rileggendo il registro, non dalla memoria della
conversazione. Il report lo legge una persona, che deve capire in pochi secondi cosa fare: mostra
solo esiti e azioni, il resto resta nel registro. In quest'ordine:

1. **Una riga per issue**, con simbolo, issue, esito e PR:
   - `✓ ICH-325 pronta per il merge — PR #12 (2 fix dalla review)`
   - `⚠ ICH-326 da guardare prima del merge — PR #13 — <la questione in una frase>`
   - `✗ ICH-327 interrotta allo step 2c — <motivo in una frase>`

   `✗` ha precedenza se il ciclo è interrotto; altrimenti usa `⚠` se ci sono `[questione]`
   e `✓` se non ce ne sono. Le issue escluse dallo scope vanno in una sola riga:
   `Escluse: <issue-id> (<motivo>)`.
2. **Cosa fai ora**: le azioni numerate, nell'ordine in cui farle:
   - per ogni issue `⚠`, prima le sue righe `[questione]`, come decisione o azione, con
     `file:riga` quando disponibili;
   - solo a review completata e senza `BLOCKER` o `HIGH` aperti (riga `[esito]`),
     per le PR `✓` o `⚠` (per queste ultime, dopo aver risolto le questioni), i comandi in
     un blocco:
     ```bash
     gh pr merge "<branch>" --merge
     ```
     poi `/trinity:workflow:5_remove-worktree <prefix>+<base-name>`;
   - per ogni issue `✗`, il comando della riga `[interruzione]`;
   - per ogni riga `[fallito]`, il comando che completa l'operazione.
3. **Da sapere**: solo le righe `[decisione]` che l'utente può voler cambiare (per esempio
   un'interpretazione della specifica o la review su un solo modello). Una riga ciascuna. Ometti
   la sezione se è vuota.
4. In fondo, una riga con il path del registro: `Dettagli: <path>`.

Non scrivere branch, numero di round, worktree rimossi, esito della semplificazione o commenti
Linear pubblicati: sono nel registro e nel commento sulla issue.
