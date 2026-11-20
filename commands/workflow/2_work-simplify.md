---
description:
  Semplifica il codice della PR di una o più issue Linear (riuso, semplificazione, efficienza,
  profondità) senza cambiarne il comportamento; da usare prima della review
argument-hint: <issue-id...> <model>
disable-model-invocation: true
---

Migliora la qualità del codice della PR delle issue indicate e applica i fix, senza cambiarne il
comportamento. Non cercare bug di correttezza: è il compito di `/3_independent-review` e
`/4_review-fix-loop`.

Usalo dopo `/2_work-issue` e prima della review, così la review controlla anche le semplificazioni.

Il modello qui serve solo a identificare il worktree corretto, non a scegliere il modello di
esecuzione.

## Validazione degli argomenti

Dividi `$ARGUMENTS` in token separati da spazi:

- l'ultimo token è il modello;
- i token precedenti sono gli issue ID (almeno uno).

Se i token sono meno di 2, fermati e mostra:

`/trinity:workflow:2_work-simplify <issue-id...> <model>`

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

Se il working tree non è pulito, fermati ed elenca i file: non decidere da solo e non eseguire mai
`git checkout .`, `git reset --hard` o `git stash`. Se gli SHA differiscono (commit non pushati o
push di altri) o la PR non esiste, fermati e mostralo.

Dalla PR ricavi la base `<base>` (`baseRefName`) e il comportamento voluto (titolo e corpo): quel
comportamento non si tocca. Se `gh` non risponde, usa come base il branch di default, ricavato come
in `/2_work-issue` («Pull Request»).

### Entrata e permanenza nel worktree

Dopo le verifiche iniziali, se non sei già nel worktree di implementazione, usa `EnterWorktree` passando
`<wt-path>` come `path`: entra nel worktree **già esistente**, senza crearne uno nuovo.
Controlla che la directory di lavoro della sessione sia `<wt-path>` prima di modificare file.
Se lo strumento non è disponibile, fermati e segnala il problema: non sostituirlo con un
semplice `cd`, che non garantisce il cambio della directory di lavoro dell'intera sessione.

**Rimani nel worktree durante tutta la semplificazione**: analisi, fix, test, commit e push.
Non eseguire `ExitWorktree` per un messaggio intermedio o un errore recuperabile mentre
attendi una decisione dell'utente per proseguire il lavoro.

### Uscita dal worktree

- **Comando eseguito autonomamente:** dopo aver completato le verifiche e il report finale,
  usa `ExitWorktree` con `action: "keep"`. Il worktree e il branch devono rimanere intatti.
- **Comando richiamato dalla catena `auto` di `2_work-issue`:** non uscire al termine di
  questo singolo step; lascia che il workflow coordinatore gestisca l'uscita alla fine della
  catena o prima di un eventuale step che rimuove il worktree.
- **Errore bloccante senza possibilità di proseguire:** se l'esecuzione termina davvero,
  usa `ExitWorktree(action: "keep")` prima del report d'errore, se sei entrato con
  `EnterWorktree`.

Non eliminare mai il worktree in questo comando.

## 0. Perimetro

Il perimetro è il diff della PR:

```bash
git -C "<wt-path>" diff "origin/<base>"...HEAD
```

Non rieseguire qui la suite: il punto di partenza è il giro verde di `2_work-issue`, e il
controllo degli SHA qui sopra garantisce che HEAD coincide con la PR. La esegui una sola volta
alla fine, prima del push. Fermati e mostralo solo se quel giro non esiste o era rosso.

## 1. Analisi: quattro angoli

Percorri questi angoli uno dopo l'altro, nello stesso contesto: non lanciare subagenti. Per ogni
problema annota `file:riga`, una sintesi in una frase e il costo concreto: cosa è duplicato,
sprecato o più difficile da mantenere.

- **Riuso.** Codice nuovo che reimplementa qualcosa che esiste già: nel repository (cerca con Grep
  nei moduli condivisi e di utility e nei file vicini alla modifica), nella libreria standard,
  nella piattaforma o in una dipendenza già installata. Nomina la funzione da chiamare.
- **Semplificazione.** Complessità che il diff aggiunge senza bisogno: codice non necessario,
  stato ridondante o derivabile, copia-incolla con piccole varianti, annidamento profondo, codice
  morto lasciato indietro, astrazioni o dipendenze che le issue non chiedono. Nomina la forma più
  semplice che fa lo stesso lavoro, anche una sola riga.
- **Efficienza.** Lavoro sprecato che il diff introduce: calcoli ridondanti o I/O ripetuto,
  operazioni indipendenti eseguite in sequenza, lavoro bloccante aggiunto all'avvio o nei percorsi
  caldi. Segnala anche gli oggetti longevi costruiti da closure: trattengono tutto lo scope che le
  contiene, una perdita di memoria se lo scope ha valori grandi; preferisci una struttura che
  copia solo i campi che servono. Nomina l'alternativa più economica.
- **Profondità.** Controlla che ogni modifica agisca sulla causa alla profondità giusta e non
  tamponi un sintomo con una pezza fragile. Casi speciali aggiunti su infrastruttura condivisa
  indicano una modifica poco profonda: nomina la modifica più semplice e generale al meccanismo
  sottostante.

Togli i duplicati: stesso punto o stesso meccanismo → uno solo.

## 2. Fix

Applica i fix uno per volta. Salta un finding, e annota il motivo in una riga invece di
discuterne, se il fix:

- cambia il comportamento voluto, quello descritto nella PR o coperto dai test;
- richiede modifiche ben oltre il diff della PR;
- toglie una protezione: validazione di input che superano un confine di fiducia, gestione di
  errori che altrimenti perdono dati, sicurezza, accessibilità;
- risolve un falso positivo.

Una modifica di profondità che chiede un cambio di architettura non è un fix: annotala come
saltata, con la modifica che proponi.

Per ogni fix, o gruppo di fix con lo stesso motivo:

1. applica la modifica;
2. esegui i test mirati;
3. se passano, crea un commit aggiungendo i file per nome, mai con `git add -A` o `git add .`; il
   messaggio va nella lingua della PR, che è quella del progetto Linear;
4. se falliscono, annulla solo quella modifica con `git -C "<wt-path>" restore -- <file>...`,
   cancella i file nuovi che ha creato e segna il finding come saltato: una semplificazione che
   rompe un test cambia il comportamento.

Alla fine esegui la suite completa e i controlli rilevanti del progetto. Se sono verdi, esegui il
push con `git -C "<wt-path>" push origin "<branch>"`. Se sono rossi, non fare il push: fermati e
mostra l'output completo.

## Report finale

Apri con gli ID delle issue, il numero di fix e l'esito effettivo del push.
Indica i comandi di test e il loro esito finale. Se i test finali
falliscono, apri con **Push non eseguito: test falliti**, mostra l'output
completo e non suggerire il passo successivo.

Per i fix applicati usa questa tabella Markdown, una riga per fix, senza
numeri di riga. Se più fix condividono il commit, ripeti lo stesso SHA breve.

Per i fix pushati ricava una sola volta l'URL della review Linear dal commento
di `linear-code[bot]` sulla PR corrente:

```bash
gh api --paginate "repos/<owner>/<repo>/issues/<numero-PR>/comments" \
  --jq '.[] | select(.user.login == "linear-code[bot]") | .body' |
  grep -oE 'https://linear\.app/[[:alnum:]_-]+/review/[[:alnum:]_-]+' | head -1
```

Nella colonna Commit mostra lo SHA breve come link Markdown al commit su Linear:
`[SHA-breve](URL-review/changes?commit=SHA-completo)`. Usa lo SHA completo del
singolo fix, non l'HEAD per tutte le righe. Se manca l'URL o il fix non è stato
pushato, mostra solo lo SHA breve senza link.

| Cosa è cambiato | Commit |
| --- | --- |
| Descrizione della modifica | SHA breve |

Ometti la tabella se non hai applicato fix. Se il codice era già pulito,
scrivi «Nessuna semplificazione necessaria». Per ogni proposta saltata indica
in una riga il file, il simbolo se presente e il motivo; se non ce ne sono,
ometti la sezione.

In modalità manuale, a lavoro concluso senza errori, chiudi con
**Prossimo passo:** `/trinity:workflow:2_work-verify <issue-id...> <model>`
(facoltativo, se vuoi provare l'app in esecuzione), poi la review:
`/trinity:workflow:3_independent-review <issue-id...> <model>` per una review
singola oppure `/trinity:workflow:4_review-fix-loop <issue-id...> <model>` per
il loop. Sostituisci gli argomenti con quelli effettivi.
