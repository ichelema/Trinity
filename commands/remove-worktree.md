---
description: Rimuove un worktree finito (dopo il merge), il suo branch e fa pulizia, evitando le trappole note su Windows/MSYS2
argument-hint: <worktree-name>
arguments:
  - worktree_name
disable-model-invocation: true
---

Rimuovi il worktree `$worktree_name` (directory sotto `.claude/worktrees/`, es.
`improvements+ICH-73-review-GPT` o `ich-73-verifica-fattibilita-5df44e`) e il branch
che vi è agganciato, poi fai pulizia. Funziona sia su Windows/MSYS2 sia su Linux:
i comandi sono Bash puro e portabile; i passi solo-Windows sono marcati.

## Validazione dell'argomento

Se `$worktree_name` manca, fermati e mostra:

`/remove-worktree <worktree-name>`

Accetta anche un path assoluto: in quel caso usalo com'è. Altrimenti il worktree
è `<repo-root>/.claude/worktrees/$worktree_name`.

## Da dove lanciare i comandi (obbligatorio)

Lavora dal **worktree principale** del repository, MAI dall'interno del worktree
da rimuovere. Determina la root con:

```bash
git rev-parse --path-format=absolute --git-common-dir   # <repo-root>/.git
```

`<repo-root>` è quel valore senza il suffisso `/.git`. Se la cwd corrente è
dentro il worktree da rimuovere (`git rev-parse --show-toplevel` = path del
worktree), fermati: su Windows la directory non è cancellabile finché una shell
o la sessione Claude Code la tiene come cwd (`Device or resource busy`); su
Linux funziona ma è comunque fragile. Chiedi all'utente di rilanciare il comando
da una sessione aperta nella root del repository.

**Windows/MSYS2, drive `subst`.** Se `git worktree list` mostra il worktree
con una lettera di drive diversa da quella della tua cwd (es. entry `E:/AI/...`
ma cwd `/d/AI/...`, con `E:` alias `subst` di `D:`), spostati sulla root vista
con la **stessa lettera dell'entry** (`cd /e/AI/Claude/Trinity`): git confronta i
path testualmente e non risolve i `subst`.

## Ispezione prima di toccare qualcosa

```bash
git fetch --prune origin
git worktree list --porcelain
```

Dalla entry del worktree ricava `<wt-path>` (riga `worktree ...`, usalo poi
ESATTAMENTE così com'è stampato) e `<branch>` (riga `branch refs/heads/...`).
Se non c'è nessuna entry per `$worktree_name` ma la directory esiste, vedi
"Directory orfana" più sotto.

Default branch senza `gh` (che nella shell di Claude può non essere loggato):

```bash
git symbolic-ref -q --short refs/remotes/origin/HEAD || git remote show origin | sed -n 's/.*HEAD branch: /origin\//p'
```

Poi, sul worktree e sul branch:

```bash
git -C "<wt-path>" status --short              # deve essere vuoto
git log --oneline <default>..<branch>            # commit NON ancora sul default (deve essere vuoto)
git merge-base --is-ancestor <branch> <default> && echo MERGED || echo UNMERGED
git ls-remote --heads origin <branch>            # vuoto = GitHub ha già cancellato il branch remoto
```

Fermati e chiedi conferma esplicita se: `status` non è vuoto, ci sono commit
unici, il branch è UNMERGED, oppure il branch remoto esiste ancora. Non usare
mai `--force`/`-D` senza quel sì.

Prima di procedere mostra i bersagli esatti: `<wt-path>`, `<branch>` con ultimo
commit, stato merged/unmerged, presenza del branch remoto.

## Rimozione

### 1. (Windows/MSYS2) ripristina il `gitdir` POSIX nel file `.git` del worktree

I worktree creati con `/create-review-worktree` (o toccati da SmartGit) hanno
nel file `<wt-path>/.git` un `gitdir:` in forma Windows (`E:/AI/...`). Il git
MSYS ci lavora (status, commit), ma `git worktree remove` fa una validazione
testuale e fallisce con
`validation failed, cannot remove working tree: '...' does not point back to '.git/worktrees/<nome>'`.

Ripristino in Bash puro (no `sed`: su MSYS la conversione dei path lo rompe;
crea prima il `.bak`; su Linux il pattern non matcha ed è un no-op):

```bash
gf="<wt-path>/.git"; cp -p "$gf" "$gf.bak"
IFS= read -r line < "$gf"; gd="${line#gitdir: }"
case "$gd" in
  [A-Za-z]:/*) d="${gd%%:*}"; printf 'gitdir: /%s%s\n' "${d,,}" "${gd#?:}" > "$gf" ;;
esac
cat "$gf"     # atteso: gitdir: /<lettera>/.../.git/worktrees/<nome>
```

Verificato il 2026-08-15: prima del ripristino la rimozione fallisce con
l'errore sopra, dopo riesce al primo colpo.

### 2. Rimuovi il worktree

```bash
git worktree remove "<wt-path>"
```

Solo se `status` non era vuoto E l'utente ha confermato di scartare le
modifiche: `git worktree remove --force "<wt-path>"`.

**Non usare `git worktree prune`** né come scorciatoia né come passo di
routine: su Windows/MSYS2 con path `E:/...` nelle entry ha già cancellato
worktree e branch estranei (li considera "mancanti"). `git worktree remove`
toglie già la sua entry. Per sola diagnosi è ammesso `git worktree prune
--dry-run`.

**Windows: `error: failed to delete '...': Device or resource busy`.** Git ha
già deregistrato il worktree (verifica: sparisce da `git worktree list`) ma la
directory è ancora aperta da un processo (sessione Claude Code, terminale,
editor). Non ripetere il comando: chiudi chi la tiene e poi cancella la sola
directory con `rm -rf "<wt-path>"`. Vale anche per un `.git.bak` residuo.

### 3. Elimina il branch

```bash
git branch -d <branch>
```

`-d` rifiuta un branch non mergiato: è la rete di sicurezza voluta. `-D` solo
dopo conferma esplicita dell'utente. Il branch remoto, se esiste ancora ed è
mergiato (`git merge-base --is-ancestor <branch> <default>`), si elimina solo
su richiesta esplicita con `git push origin --delete <branch>`.

## Directory orfana (nessuna entry in `git worktree list`)

Succede dopo un `remove` andato a metà (vedi "resource busy"). La cartella non
è più un worktree: `rm -rf "<repo-root>/.claude/worktrees/$worktree_name"`.
Prima controlla che dentro non ci siano file da salvare (`ls -la`; con il file
`.git` presente puoi provare `git -C <dir> status --short`, ma se punta a un
gitdir già rimosso fallirà: in quel caso confronta a mano). Niente `prune`.

## Verifica finale

```bash
git worktree list
git branch --list
ls "<repo-root>/.claude/worktrees/"
git -C "<repo-root>" status -sb | head -1
```

Alla fine stampa esclusivamente questa tabella, sostituendo i segnaposto:

```
┌──────────────────────┬──────────────────────────────────────────────────────────┐
│        Campo         │                          Valore                          │
├──────────────────────┼──────────────────────────────────────────────────────────┤
│ Worktree             │ <wt-path> — rimosso / directory residua da cancellare    │
├──────────────────────┼──────────────────────────────────────────────────────────┤
│ Branch locale        │ <branch> — eliminato (era <sha>) / mantenuto: <motivo>   │
├──────────────────────┼──────────────────────────────────────────────────────────┤
│ Branch remoto        │ già assente / eliminato / mantenuto                      │
├──────────────────────┼──────────────────────────────────────────────────────────┤
│ gitdir POSIX         │ ripristinato (.bak creato) / non necessario              │
├──────────────────────┼──────────────────────────────────────────────────────────┤
│ Default branch       │ <default> = <sha> (allineato a origin: sì/no)            │
├──────────────────────┼──────────────────────────────────────────────────────────┤
│ Worktree residui     │ <elenco o "nessuno">                                     │
└──────────────────────┴──────────────────────────────────────────────────────────┘
```

Adatta la larghezza della colonna Valore al contenuto effettivo.
