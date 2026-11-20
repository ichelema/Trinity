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

## Da dove lanciare i comandi (obbligatorio)

Lavora dal **worktree principale** del repository, MAI dall'interno del worktree da rimuovere.
Determina la root con:

```bash
git rev-parse --path-format=absolute --git-common-dir   # <repo-root>/.git
```

`<repo-root>` è quel valore senza il suffisso `/.git`. Se la cwd corrente è dentro il worktree da
rimuovere (`git rev-parse --show-toplevel` = path del worktree, confronta i due path dopo
`cygpath -m`), esci con un comando a sé, `cd "<repo-root>"`, e verifica con `pwd`: su Windows git
non cancella una directory che fa da cwd alla shell (`Device or resource busy`, vedi più sotto).

**Windows/MSYS2, drive `subst`.** Se `git worktree list` mostra il worktree con una lettera di drive
diversa da quella della tua cwd (es. entry `E:/AI/...` ma cwd `/d/AI/...`, con `E:` alias `subst` di
`D:`), spostati sulla root vista con la **stessa lettera dell'entry** (`cd /e/AI/Claude/Trinity`):
git confronta i path testualmente e non risolve i `subst`.

## Ispezione prima di toccare qualcosa

```bash
git fetch --prune origin
git worktree list --porcelain
```

Dalla entry del worktree ricava `<wt-path>` (riga `worktree ...`, usalo poi ESATTAMENTE così com'è
stampato) e `<branch>` (riga `branch refs/heads/...`). Se la entry ha `detached` al posto di
`branch` (worktree di review di `/3_independent-review` o `/4_review-fix-loop`), non c'è branch:
salta i controlli sul branch e il passo 4; resta obbligatorio `status --short` vuoto. Se non c'è
nessuna entry per `$worktree_name` ma la directory esiste, vedi "Directory orfana" più sotto.

Default branch senza `gh` (che nella shell di Claude può non essere loggato):

```bash
git symbolic-ref -q --short refs/remotes/origin/HEAD || git remote show origin | sed -n 's/.*HEAD branch: /origin\//p'
```

Poi, sul worktree e sul branch:

```bash
git -C "<wt-path>" status --short              # deve essere vuoto
git log --oneline <default>..<branch>            # commit NON ancora sul default (deve essere vuoto)
git merge-base --is-ancestor <branch> <default> && echo MERGED || echo UNMERGED
git ls-remote --heads origin "refs/heads/<branch>"
```

Fermati e chiedi conferma esplicita se: `status` non è vuoto, ci sono commit unici, il branch è
UNMERGED. La sola presenza del remoto non richiede conferma. Conserva lo SHA
remoto esatto letto sopra per il passo 4 (output vuoto con successo = assente).
Non usare `--force`/`-D` senza conferma.

Prima di procedere mostra i bersagli esatti: `<wt-path>`, `<branch>` con ultimo commit, stato
merged/unmerged, presenza del branch remoto.

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

```bash
git worktree remove "<wt-path>"
```

Solo se `status` non era vuoto E l'utente ha confermato di scartare le modifiche:
`git worktree remove --force "<wt-path>"`.

**Non usare `git worktree prune`** né come scorciatoia né come passo di routine: su Windows/MSYS2
con path `D:/...` nelle entry ha già cancellato worktree e branch estranei (li considera
"mancanti"). `git worktree remove` toglie già la sua entry. Per sola diagnosi è ammesso
`git worktree prune --dry-run`.

**Windows: `error: failed to delete '...': Device or resource busy`.** Git ha già deregistrato il
worktree (verifica: sparisce da `git worktree list`) ma la directory è ancora aperta da un processo
(sessione Claude Code, terminale, editor). Non ripetere il comando: chiudi chi la tiene e poi
cancella la sola directory con `rm -rf "<wt-path>"`.

### 3. Allinea il default branch locale

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

### 4. Elimina il branch

```bash
git branch -d <branch>
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

## Directory orfana (nessuna entry in `git worktree list`)

Succede dopo un `remove` andato a metà (vedi "resource busy"). La cartella non è più un worktree:
`rm -rf "<repo-root>/.claude/worktrees/$worktree_name"`. Prima controlla che dentro non ci siano
file da salvare (`ls -la`; con il file `.git` presente puoi provare `git -C <dir> status --short`,
ma se punta a un gitdir già rimosso fallirà: in quel caso confronta a mano). Niente `prune`.

## Verifica finale

```bash
git worktree list
git branch --list
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
  scritto, senza aspettare che l'utente la chieda;
- se quei file esistono ma senza una procedura, chiedi all'utente se aggiornarli e se salvare
  decisioni e cause radice in Hindsight;
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
- `Chiusura del lavoro`: solo per un worktree di implementazione rimosso;
  eseguita (con commit, se creato), da fare, non prevista o saltata, con motivo;
- `Cosa fai ora`: solo se serve un intervento. Indica il prossimo passo sicuro:
  per modifiche locali, ispezionarle e salvarle; per una directory residua,
  verificare cosa la tiene aperta e se contiene file da conservare.

Ometti i branch eliminati, il remoto già assente, il ripristino del `gitdir`
POSIX, il default branch allineato e i worktree di altre issue.
