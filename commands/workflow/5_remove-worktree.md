---
description:
  Rimuove un worktree finito (dopo il merge), il suo branch e fa pulizia, evitando le trappole note
  su Windows/MSYS2
argument-hint: <worktree-name>
arguments:
  - worktree_name
disable-model-invocation: true
---

Rimuovi il worktree `$worktree_name` (directory sotto `.claude/worktrees/`, es.
`review+ICH-73-fable-gpt` o `ich-73-verifica-fattibilita-5df44e`) e il branch che vi è
agganciato, poi fai pulizia. Funziona sia su Windows/MSYS2 sia su Linux: i comandi sono Bash puro e
portabile; i passi solo-Windows sono marcati.

## Validazione dell'argomento

Se il nome del worktree manca, fermati e mostra:

`/trinity:workflow:5_remove-worktree <worktree-name>`

Accetta anche un path assoluto: in quel caso usalo com'è. Altrimenti il worktree è
`<repo-root>/.claude/worktrees/$worktree_name`.

## Contesto della sessione e directory di esecuzione (obbligatorio)

**Non usare `cd` come meccanismo per uscire da un worktree gestito da Claude Code.**
`cd` in Bash non garantisce di modificare la directory di lavoro degli altri tool della sessione.

Ricava il repository principale senza assumere che la directory corrente sia già la root:

```bash
git rev-parse --path-format=absolute --git-common-dir   # normalmente <repo-root>/.git
```

`<repo-root>` è il percorso restituito senza il suffisso `/.git`. Se il comando non restituisce
il percorso atteso, fermati e identifica correttamente il repository: non ricostruire path a caso.

**Prima di eliminare qualsiasi worktree**, identifica `<wt-path>` usando l'entry esatta di
`git -C "<repo-root>" worktree list --porcelain` (vedi sezione seguente). Se la sessione Claude Code è entrata
in **quel** worktree con `EnterWorktree`, esci usando `ExitWorktree` con `action: "keep"`:
questo conserva i file e restituisce la sessione alla directory precedente. Verifica quindi che
la directory di lavoro effettiva della sessione e la cwd della shell non siano dentro `<wt-path>`.
Se la sessione è già fuori, non chiamare `ExitWorktree` per un altro worktree. Se il tool non è
presente, l'uscita fallisce o non puoi verificarla, **non tentare di cancellare il worktree attivo**:
fermati e chiedi di uscire dalla sessione o riaprire Claude dal repository principale.

Il tool `ExitWorktree` non garantisce di chiudere terminali, editor, server o altri processi che
abbiano ancora quel worktree come cwd: controlla e termina **solo i processi avviati da questo
workflow** prima di rimuoverlo. Non terminare processi altrui automaticamente.

Esegui tutti i comandi Git successivi sul repository principale con `git -C "<repo-root>" ...`,
indipendentemente dalla cwd corrente. Usa il path `<wt-path>` esatto per le operazioni sul worktree.
Su Windows/MSYS2 conserva la stessa forma di path e lettera di drive mostrata dall'entry Git
(anche in presenza di drive `subst`); non forzare conversioni o `cd` su drive diversi.

## Ispezione prima di toccare qualcosa

```bash
git -C "<repo-root>" fetch --prune origin
git -C "<repo-root>" worktree list --porcelain
```

Non procedere se il bersaglio è il worktree principale o se il path non coincide con il nome/path richiesto.
Dalla entry del worktree ricava `<wt-path>` (riga `worktree ...`, usalo poi ESATTAMENTE così com'è
stampato) e `<branch>` (riga `branch refs/heads/...`). Se la entry ha `detached` al posto di
`branch` (worktree di review di `/3_independent-review` o `/4_review-fix-loop`), non c'è branch:
salta i controlli sul branch, il default branch e i passi 3 e 4; resta obbligatorio
`status --short` vuoto. Se non c'è
nessuna entry per `$worktree_name` ma la directory esiste, vedi "Directory orfana" più sotto.

Solo per un worktree con branch, determina il default branch senza `gh` (che nella shell di Claude può non essere loggato):

```bash
git -C "<repo-root>" symbolic-ref -q --short refs/remotes/origin/HEAD || git -C "<repo-root>" remote show origin | sed -n 's/.*HEAD branch: /origin\//p'
```

Controlla sempre lo stato del worktree:

```bash
git -C "<wt-path>" status --short              # deve essere vuoto
git -C "<wt-path>" ls-files --others --ignored --exclude-standard --directory
```

**Solo se non è detached**, esegui i controlli sul branch:

```bash
git -C "<repo-root>" log --oneline <default>..<branch>            # commit NON ancora sul default (deve essere vuoto)
git -C "<repo-root>" merge-base --is-ancestor <branch> <default> && echo MERGED || echo UNMERGED
git -C "<repo-root>" ls-remote --heads origin "refs/heads/<branch>"
```

Fermati e chiedi conferma esplicita se: ci sono file ignorati da salvare o scartare,
`status` non è vuoto, ci sono commit unici, il branch è
UNMERGED. La sola presenza del remoto non richiede conferma. Conserva lo SHA
remoto esatto letto sopra per il passo 4 (output vuoto con successo = assente).
Non usare `--force`/`-D` senza conferma.

Prima di procedere mostra i bersagli esatti: `<wt-path>` e, per un worktree non detached,
`<branch>` con ultimo commit, stato merged/unmerged e presenza del branch remoto. Per un worktree
detached indica il commit HEAD e che nessun branch verrà eliminato.

## Rimozione

### 1. (Windows/MSYS2) ripristina il `gitdir` POSIX nel file `.git` del worktree

I worktree creati con `/1_create-worktree`, `/3_independent-review` o `/4_review-fix-loop` (o
toccati da SmartGit) hanno nel file `<wt-path>/.git` un `gitdir:` in forma Windows (`D:/AI/...`).
Il git MSYS ci lavora (status, commit), ma `git worktree remove` fa una validazione testuale e
fallisce con
`validation failed, cannot remove working tree: '...' does not point back to '.git/worktrees/<nome>'`.

Ripristino in Bash puro (no `sed`: su MSYS la conversione dei path lo rompe). Il backup va FUORI
dal worktree: un `.git.bak` dentro è un file non tracciato e `git worktree remove` lo rifiuta
("contains modified or untracked files"). Su Linux il pattern non matcha ed è un no-op:

```bash
gf="<wt-path>/.git"; IFS= read -r line < "$gf"; gd="${line#gitdir: }"
case "$gd" in
  [A-Za-z]:/*) mkdir -p "$HOME/.claude/tmp"; cp -p "$gf" "$HOME/.claude/tmp/<nome>.git.bak"
               d="${gd%%:*}"; printf 'gitdir: /%s%s\n' "${d,,}" "${gd#?:}" > "$gf" ;;
esac
cat "$gf"     # atteso: gitdir: /<lettera>/.../.git/worktrees/<nome>
```

Verificato il 2026-08-15: prima del ripristino la rimozione fallisce con l'errore sopra, dopo riesce
al primo colpo.

### 2. Rimuovi il worktree

Prima di chiamare Git, ripeti il controllo: Claude Code, Bash e i processi avviati dal workflow
non devono avere `<wt-path>` come directory corrente. La conferma all'eliminazione di modifiche
non autorizza a cancellare un worktree ancora attivo.

```bash
git -C "<repo-root>" worktree remove "<wt-path>"
```

Solo se `status` non era vuoto E l'utente ha confermato di scartare le modifiche:
`git -C "<repo-root>" worktree remove --force "<wt-path>"`.

**Non usare `git -C "<repo-root>" worktree prune`** né come scorciatoia né come passo di routine: su Windows/MSYS2
con path `D:/...` nelle entry ha già cancellato worktree e branch estranei (li considera
"mancanti"). `git -C "<repo-root>" worktree remove` toglie già la sua entry. Per sola diagnosi è ammesso
`git -C "<repo-root>" worktree prune --dry-run`.

**Windows: `error: failed to delete '...': Device or resource busy`.** Git ha già deregistrato il
worktree (verifica: sparisce da `git -C "<repo-root>" worktree list`) ma la directory è ancora aperta da un processo
(sessione Claude Code, terminale, editor). Non ripetere il comando: chiudi chi la tiene, verifica che Git non registri più quel worktree,
controlla che il path sia esattamente quello atteso sotto `.claude/worktrees/` e soltanto dopo
cancella la directory residua con `rm -rf "<wt-path>"`. Se non puoi confermare queste condizioni,
fermati senza usare `rm -rf`.

### 3. Allinea il default branch locale (solo worktree con branch)

Il merge è avvenuto su GitHub, quindi il default branch locale è indietro rispetto a `<default>`,
appena aggiornato dal `fetch`. Portalo avanti, solo in fast-forward:

```bash
default="<default>"; branch_name="${default#origin/}"   # origin/master -> master
if [ "$(git -C "<repo-root>" symbolic-ref -q --short HEAD)" = "$branch_name" ]; then
  git -C "<repo-root>" merge --ff-only "<default>"
fi
```

Fallo prima del passo 4: `git branch -d` accetta il branch solo se è già contenuto in `HEAD` (il
suo upstream remoto è già stato cancellato da GitHub). Se il worktree principale è su un altro
branch, non fare checkout: salta il passo e segnalalo nella tabella finale. Se `merge --ff-only`
fallisce (storia divergente o modifiche locali che verrebbero sovrascritte), non forzare: mostra
l'errore e prosegui.

### 4. Elimina il branch (solo worktree con branch)

```bash
git -C "<repo-root>" branch -d <branch>
```

`-d` rifiuta un branch non mergiato: è la rete di sicurezza voluta. `-D` solo dopo conferma
esplicita dell'utente.

Il lancio manuale dello step autorizza, senza seconda domanda, a eliminare da
`origin` solo il branch di implementazione del worktree richiesto. Non vale
per chiamate interne, worktree detached o directory orfane. Non eliminare mai
il default branch. Se il branch locale non risultava mergiato, conserva il remoto.

Usa lo SHA remoto rilevato nell'ispezione iniziale, senza ricalcolarlo.
Se era assente, non fare nulla. Prima del push verifica il default corrente
con `git ls-remote --symref origin HEAD`: deve identificare un branch diverso
dal bersaglio e il suo SHA deve coincidere con il default aggiornato dal fetch.
Verifica che `git merge-base --is-ancestor "<sha-remoto>" "<sha-default>"`
riesca. Se un controllo fallisce o un dato manca, mantieni il remoto.
Altrimenti esegui dalla root del repository:

```bash
git push --force-with-lease="refs/heads/<branch>:<sha-remoto>" \
  origin ":refs/heads/<branch>"
```

Se il lease o il server rifiuta il push, segnala il motivo e non ritentare.

## Directory orfana (nessuna entry in `git -C "<repo-root>" worktree list`)

Succede dopo un `remove` andato a metà (vedi "resource busy"). La cartella non è più un worktree:
`rm -rf "<wt-path>"` **solo dopo aver verificato che `<wt-path>` sia sotto
`<repo-root>/.claude/worktrees/`, non sia il repository principale e non sia la cwd di alcuna
sessione o processo noto**. Prima controlla che dentro non ci siano
file da salvare (`ls -la`; con il file `.git` presente puoi provare `git -C <dir> status --short`,
ma se punta a un gitdir già rimosso fallirà: in quel caso confronta a mano). Niente `prune`.

## Verifica finale

```bash
git -C "<repo-root>" worktree list
git -C "<repo-root>" branch --list
ls "<repo-root>/.claude/worktrees/"
git -C "<repo-root>" status -sb | head -1
```

## Chiusura del lavoro nel progetto

Salta questa sezione se il worktree era detached (worktree di review) o se il branch non è stato
mergiato.

Il workflow finisce qui, ma il progetto può chiedere altro dopo il merge: note di ripresa, log
delle decisioni, memorie. Nessun command precedente lo fa: è questo il momento. Cerca in
`<repo-root>`:

- file di passaggio tra sessioni (`RIPRESA.md`, `RICONSEGNA.md`, `HANDOFF.md` o simili) e una
  cartella `memory/`;
- una procedura di chiusura scritta in quei file o in `CLAUDE.md` (es. «dopo ogni merge chiudi il
  lotto»).

Poi:

- se il progetto definisce una procedura di chiusura, eseguila ora, per intero e nell'ordine
  scritto, senza aspettare che l'utente la chieda; annota i file che aggiorni e i commit creati;
- se quei file esistono ma senza una procedura, chiedi all'utente se aggiornarli e se salvare
  decisioni e cause radice in Hindsight; annota i file aggiornati dopo la risposta;
- se non esiste nulla, non creare file.

## Report finale

Anche se il comando termina senza rimuovere nulla, stampa una tabella Markdown:

| Campo | Valore |
| --- | --- |
| Worktree | Esito verificato e percorso del bersaglio |

Distingui **Rimosso** (entry Git e directory assenti), **Non rimosso** (con il
motivo) e **Rimosso da Git, directory ancora presente**. Se non puoi verificare
lo stato, indica cosa non hai potuto controllare, senza dichiarare il successo.
Per un worktree detached rimosso senza anomalie basta la riga `Worktree`.

Aggiungi queste righe solo quando pertinenti:

- `Branch locale`: `<branch>` mantenuto, con il motivo;
- `Branch remoto`: ancora presente e mantenuto;
- `Default branch`: fast-forward saltato o fallito, con il motivo;
- `Worktree residui`: solo quelli di review della stessa operazione che
  avrebbero dovuto essere rimossi, identificati dal percorso esatto;
- `Chiusura del lavoro`: solo per un worktree di implementazione rimosso. Indica
  eseguita, da fare, non prevista o saltata, con il motivo, e in ogni caso elenca i
  file aggiornati con il percorso relativo, oppure scrivi `nessun file aggiornato`.
  Con `eseguita` aggiungi il commit creato, se c'è.
- `Cosa fai ora`: solo se serve un intervento. Indica il prossimo passo sicuro:
  per modifiche locali, ispezionarle e salvarle; per una directory residua,
  verificare cosa la tiene aperta e se contiene file da conservare.

Ometti i branch eliminati, il remoto già assente, il ripristino del `gitdir`
POSIX, il default branch allineato e i worktree di altre issue.
