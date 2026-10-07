---
description:
  Ciclo completo e senza presidio di una o più issue Linear, una dopo l'altra: per ogni issue
  worktree, implementazione fino alla PR, review singola o loop di review e fix, pulizia dei
  worktree di review e commento su Linear; alla fine report. Non fa il merge.
argument-hint: <review|loop> <source-branch> <issue-id...> [<model>]
disable-model-invocation: true
---

Porta le issue Linear indicate dal worktree fino alla PR recensita e corretta, eseguendo per ogni
issue gli step di `${CLAUDE_PLUGIN_ROOT}/commands/workflow/`. Gli step hanno
`disable-model-invocation: true`: non puoi invocarli come slash command. Per ogni step leggi il
file e seguilo con gli argomenti indicati qui al posto di `$ARGUMENTS`.

Il merge resta all'utente: questo command non lo fa mai.

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
  annotala in «Decisioni prese in autonomia» con il motivo e prosegui.
- Dubbi, specifiche ambigue, problemi non risolti e finding non fixati non fermano il ciclo: vanno
  in «Questioni aperte» nel report finale.

Interrompi il ciclo della issue corrente solo in questi casi gravi:

1. il lavoro richiede modifiche fuori dal perimetro della issue (altri moduli, architettura,
   dipendenze nuove, dati esterni diversi dalla issue);
2. il passo successivo è distruttivo o irreversibile e gli step non lo prevedono: perdita di
   modifiche non committate, `--force`, `-D`, `reset --hard`, cancellazione di branch remoti;
3. la sicurezza è a rischio: segreti nel codice o nei log, permessi, credenziali;
4. lo stato Git non è quello atteso e proseguire può danneggiare lavoro altrui (worktree o branch
   già esistenti, working tree sporco, SHA della PR diverso).

Dopo un'interruzione non toccare più il worktree di quella issue: annota lo step raggiunto, il
motivo e il comando del singolo step che permette di riprendere, poi passa alla issue seguente.

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
log="$log_dir/$(date +%Y%m%d-%H%M)-<issue-id...>.md"   # ID uniti da '-', es. ICH-97-ICH-98
printf '# issue-cycle %s %s %s\n' "<review|loop>" "<source-branch>" "<model>" > "$log"
```

Ogni «annota» di questo command significa: aggiungi subito una riga al registro, nel momento in cui
la decisione o il problema avviene, non alla fine. Una riga per voce, sotto l'intestazione della
issue corrente:

```
- [decisione] step <N>: <scelta> — <motivo>
- [questione] step <N>: <problema> (<file>:<riga> se disponibile)
- [interruzione] step <N>: <motivo> — riprendi con <comando>
- [esito] PR <url>, review <round> round, <n> fix, residui <elenco>
```

Aggiungi sempre in append (`cat >> "$log" <<'EOF' … EOF`), mai riscrivendo il file. Dopo una
compattazione della conversazione, rileggi il registro per sapere a quale issue e a quale step sei
arrivato.

## Controlli iniziali

Esegui questi controlli una volta sola, prima della prima issue.

### Scope delle issue

Leggi ogni issue con `${CLAUDE_PLUGIN_ROOT}/skills/linear/scripts/linear.py query`, in sola lettura.
Una issue che non richiede modifiche a un repository Git (configurazione di tool esterni, ricerca,
pulizia di Linear, note fuori dai repo) non entra nel ciclo: toglila dalla lista, non toccare il
suo stato e annotala sotto l'intestazione `## Escluse` con il comando
`/trinity:linear-no-repo <issue-id>`. Se non resta nessuna issue, fermati.

### Modello di implementazione

`<model>` non sceglie il modello di esecuzione: come negli step, è l'etichetta del worktree e del
branch. L'implementazione la fa questa sessione. Se il modello della sessione non corrisponde a
`<model>`, prosegui e annotalo.

Se la modalità è `review` e `<model>` è `fable`, annota che la review gira sullo stesso
modello che ha scritto il codice ed è meno indipendente.

### Proxy LiteLLM (solo `loop`)

La review GPT dello step 4 usa il proxy LiteLLM:

```bash
curl -s -o /dev/null -w '%{http_code}' http://127.0.0.1:4000/health/liveliness   # deve essere 200
```

Se la risposta non è `200`, prosegui con la sola review Fable: in ogni round dello step 4 crea solo
il worktree `review+<base-name>-fable`. Annotalo in «Questioni aperte». Ripeti il controllo
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

### Step 1 — worktree

Leggi e segui `${CLAUDE_PLUGIN_ROOT}/commands/workflow/1_create-worktree.md` con
`<source-branch> <issue-id> <model>`. Se il prefisso è ambiguo, usa `improvments` e annotalo.
Mostra la tabella finale senza la riga «Prossimo passo».

### Step 2 — implementazione e PR

Leggi e segui `${CLAUDE_PLUGIN_ROOT}/commands/workflow/2_work-issue.md` con `<issue-id> <model>`.
Con le regole senza presidio:

- mostra il piano e prosegui senza attendere l'ok;
- se la issue è bloccata da issue non completate, implementa solo la parte che non dipende dal
  blocco e annota il resto;
- se le specifiche sono contrastanti, scegli l'interpretazione più conservativa e annotala;
- se i test falliscono e non riesci a correggerli dentro lo scope, apri comunque la PR, dichiaralo
  nella descrizione e annotalo.

Della sezione «Non fare il merge» vale tutto tranne «in una sessione nuova»: la review parte da qui,
in un contesto separato. Mostra la tabella finale senza la riga «Prossimo passo».

### Step 3 o 4 — review

Non fare tu la review: hai scritto il codice, e il reviewer deve partire da un contesto pulito.

- `review`: tool Agent con `subagent_type: trinity:reviewer`. Nel prompt digli di leggere
  `${CLAUDE_PLUGIN_ROOT}/commands/workflow/3_independent-review.md` e di seguirlo con
  `<issue-id> <model>` al posto di `$ARGUMENTS`. Il subagente crea e rimuove da sé il worktree di
  review. Sui finding del report applica le sezioni «Triage dei finding» e «Fix minimi e
  chirurgici» di `${CLAUDE_PLUGIN_ROOT}/commands/workflow/4_review-fix-loop.md`. Un solo round:
  dopo i fix non lanciare una nuova review.
- `loop`: leggi e segui `${CLAUDE_PLUGIN_ROOT}/commands/workflow/4_review-fix-loop.md` con
  `<issue-id> <model>`. Un finding che non si risolve con un fix minimo va in «Questioni aperte»,
  non in una domanda.

Se un reviewer restituisce il verdetto `BLOCCATO: INFORMAZIONI INSUFFICIENTI`, quella review non
è avvenuta: non applicare fix sul suo report e annota in «Questioni aperte» cosa manca.

### Step 5 — pulizia dei worktree di review

Non fare il merge e non rimuovere il worktree di implementazione: lo step 5 rifiuta un branch non
mergiato, e il merge resta all'utente.

Controlla con `git worktree list --porcelain` che non resti nessun worktree
`review+<base-name>*` della issue corrente. Se ne resta uno, leggi e segui
`${CLAUDE_PLUGIN_ROOT}/commands/workflow/5_remove-worktree.md` con `$worktree_name` = quel nome.
La cartella `<review-path>/.review-tmp/` è materiale di appoggio del reviewer: cancellala prima
della rimozione, come fa lo step 3. Se lo step 5 trova altri file non tracciati o modifiche, non
rimuovere nulla e annotalo; mai `--force`.

### Commento su Linear

A fine ciclo, anche dopo un'interruzione, pubblica sulla issue un commento breve in inglese con
`linear.py`, costruito dalle righe del registro sotto `## <issue-id>`: link della PR (se esiste),
esito della review, decisioni prese in autonomia, questioni aperte e, se il ciclo è interrotto, lo
step raggiunto e il motivo. Chiudi con `Not merged: merge is left to the user.`

Regole Linear valide per tutto il ciclo:

- non spostare la issue in Done: senza merge il lavoro non è finito, e dopo il merge lo stato lo
  aggiorna l'automazione GitHub → Linear;
- non modificare titolo, parent, label o project della issue.

## Report finale

Stampalo dopo l'ultima issue. Costruiscilo rileggendo il registro, non dalla memoria della
conversazione, e indica in testa il path del registro. Sezioni, in quest'ordine:

1. **Riepilogo**: tabella markdown con una riga per issue e le colonne issue, esito del ciclo
   (completo / interrotto allo step N), branch, PR, review (round, finding fixati), worktree di
   review (rimossi / residui), commento Linear (pubblicato / fallito); sotto, le issue escluse
   dallo scope con il comando `/trinity:linear-no-repo`;
2. **Decisioni prese in autonomia**: raggruppate per issue, con la scelta e il motivo;
3. **Questioni aperte**: raggruppate per issue, con file e righe quando disponibili;
4. **Prossimi passi**: per ogni PR, i comandi esatti nell'ordine:
   ```bash
   gh pr merge "<branch>" --merge
   ```
   poi `/trinity:workflow:5_remove-worktree <prefix>+<base-name>`.
