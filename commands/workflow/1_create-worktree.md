---
description: Crea un branch e un worktree pulito per implementare una o più issue Linear
argument-hint: <source-branch> <issue-id...> <model>
disable-model-invocation: true
---

Crea un branch e un worktree separato del branch remoto indicato, relativo a una o più issue Linear.

## Validazione degli argomenti

Dividi `$ARGUMENTS` in token separati da spazi:

- il primo token è il source branch;
- l'ultimo token è il modello;
- i token intermedi sono gli issue ID (almeno uno).

Se i token sono meno di 3, fermati e mostra:

`/trinity:workflow:1_create-worktree <source-branch> <issue-id...> <model>`

## Determinazione del tipo dalle issue

Recupera ogni issue da Linear (via `${CLAUDE_PLUGIN_ROOT}/skills/linear/scripts/linear.py query`) in
modalità esclusivamente read-only.

Esamina:

- issue type;
- label;
- titolo;
- descrizione.

Leggi anche commenti, stima e priorità: servono solo per la stima dell'effort.

Determina il prefisso usando queste regole:

- se la issue è esplicitamente un bug, usa `bug`;
- se la issue è esplicitamente un miglioramento o un refactoring (es. label `Refactor`), usa
  `improvments`;
- se manca il tipo, usa una label solo se indica senza ambiguità uno dei due prefissi;
  altrimenti chiedi. Chiedi anche se il tipo esplicito è diverso o ambiguo.

Con più issue, tutte devono risolvere allo stesso prefisso. Se i prefissi differiscono, fermati e
chiedi quale usare.

Non usare label, titolo o descrizione per sovrascrivere un tipo esplicito.

Non modificare la issue, i commenti, lo stato o altri dati Linear.

## Nomi da creare

Costruisci il nome base:

- una sola issue: `<issue-id>-<model>` (es. `ICH-72-fable`);
- più issue con lo stesso prefisso team: prefisso una sola volta, poi i numeri delle successive in
  ordine (`ICH-97` + `ICH-98` → `ICH-97-98`), infine il modello: `ICH-97-98-fable`;
- issue con prefissi team diversi: fermati e chiedi come nominare.

Nel resto del comando questo valore è `<base-name>`.

Costruisci il branch di implementazione:

`<prefix>/<base-name>`

Esempi:

- `bug/ICH-72-gpt-5.6-sol`
- `improvments/ICH-97-98-fable`

La directory del worktree deve chiamarsi:

`<prefix>+<base-name>`

Il `+` sostituisce il `/` del branch (che non è valido nei nomi di directory) e mantiene il
raggruppamento visivo coerente con gli altri worktree (es. `improvments+ICH-97-98-fable`).

Verifica il nome del branch con:

`git check-ref-format --branch "<branch>"`

Se non è valido, fermati. Non correggerlo automaticamente.

## Risoluzione del branch sorgente

Non modificare il working tree o branch corrente.

Esegui:

`git fetch origin`

Non eseguire `git pull`.

Accetta il source branch con o senza il prefisso `origin/` e rimuovi l'eventuale prefisso prima di
costruire il riferimento remoto.

Verifica che esista esattamente:

`refs/remotes/origin/<source-branch>`

Non utilizzare automaticamente branch locali e non cercare branch simili.

Risolvi lo SHA aggiornato con:

`git rev-parse --verify "origin/<source-branch>^{commit}"`

## Controlli prima della creazione

Verifica che non esista già il branch locale:

`refs/heads/<branch>`

Verifica inoltre che non esista già un worktree associato allo stesso branch.

Determina la root del repository dal worktree principale, non da un altro worktree:

```bash
set -e
common_dir="$(git rev-parse --path-format=absolute --git-common-dir)"
case "$(uname -s)" in
  Linux) ;;  # Git Linux, anche sotto WSL: mantieni il percorso POSIX
  MINGW*|MSYS*|CYGWIN*)
    common_dir="$(cygpath -am "$common_dir")"
    [[ "$common_dir" == [A-Za-z]:/* ]] || exit 1 ;;
  *) echo "Sistema non supportato" >&2; exit 1 ;;
esac
repo_root="${common_dir%/.git}"
```

La directory di destinazione è dentro `.claude/worktrees/`:

`<repo-root>/.claude/worktrees/<prefix>+<base-name>`

Se il branch o la directory esistono già, fermati senza modificarli, riutilizzarli o eliminarli.

Prima della creazione mostra:

- tipo recuperato da Linear;
- prefisso selezionato;
- branch sorgente remoto;
- SHA sorgente;
- branch di implementazione;
- percorso assoluto del worktree.

## Creazione

Crea il branch e il worktree usando il percorso verificato sopra, senza
ulteriori conversioni: `/...` su Linux, `<LETTERA>:/...` su Windows.

`git worktree add -b "<branch>" "<percorso-assoluto>" "<SHA>"`

Non eseguire checkout, reset, stash o modifiche nel working tree originale.

## Compatibilità SmartGit

Leggi il back-pointer `<repo-root>/.git/worktrees/<prefix>+<base-name>/gitdir`.
Su Linux deve iniziare con `/`: non cercare una lettera di unità e non usare
`cygpath`. Su Windows deve iniziare con `<LETTERA>:/`: un percorso come
`/e/...` non è valido per SmartGit. Se il formato non corrisponde al sistema
rilevato, fermati e segnala il valore letto, senza riscrivere il file.

**Non toccare il file `.git` dentro il worktree.** `git worktree remove` lo valida, e se è in
formato Windows la rimozione fallisce ("does not point back to '.git/worktrees/<nome>'"). Il formato
che git scrive lì non è deterministico: lascialo com'è, ci pensa `/5_remove-worktree` prima della
rimozione. Non usare mai `git worktree prune` come scorciatoia: su questa macchina ha già cancellato
worktree e branch estranei.

## Verifica finale

Nel nuovo worktree verifica che:

- il branch attivo sia `<branch>`;
- `HEAD` corrisponda allo SHA del branch sorgente;
- `git status --short` non produca output.

Se un comando fallisce o un controllo non dà il risultato atteso, fermati e mostra il valore letto.
Non eseguire cleanup o operazioni distruttive automaticamente.

## Stima dell'effort

Dopo la verifica finale stima l'effort da impostare allo step 2: `Low`, `Medium` o `High`.

Lancia `trinity:scoper` sul nuovo worktree. Nel prompt passagli titolo, descrizione, criteri di
accettazione e commenti rilevanti delle issue, e il percorso assoluto del worktree. Chiedigli solo:

- file e componenti da toccare;
- aree critiche coinvolte (sicurezza, autenticazione, dati persistenti o migrazioni, concorrenza,
  operazioni distruttive, API pubbliche);
- test esistenti che coprono quel codice.

Non chiedergli un piano: lo fa lo step 2.

Il report è un input: decidi tu il livello valutando insieme report e issue su:

- difficoltà: quanti file e componenti, quanta logica nuova;
- impatto architetturale: interfacce, protocolli, schemi dati o comunicazione tra componenti;
- punti critici toccati;
- incertezza: descrizione vaga, criteri di accettazione assenti, decisioni aperte;
- verificabilità: test mancanti o comportamento difficile da riprodurre;
- stima e priorità già presenti su Linear, se ci sono.

Regole:

- un solo criterio forte (es. una migrazione di dati) basta per `High`;
- nel dubbio tra due livelli scegli il più alto;
- con più issue dai un solo valore, quello della issue più impegnativa.

Se lo scoper fallisce non fermarti: il worktree è già pronto. Stima dal solo testo della issue e
scrivi `(solo dalla issue)` nel motivo.

Alla fine stampa esclusivamente questa tabella, sostituendo i segnaposto con i valori effettivi:

```
┌────────────────────────┬──────────────────────────────────────────────────────────┐
│         Campo          │                          Valore                          │
├────────────────────────┼──────────────────────────────────────────────────────────┤
│ Issue Linear           │ <issue-id> — <titolo-issue> (una riga per issue)        │
├────────────────────────┼──────────────────────────────────────────────────────────┤
│ Branch                 │ <branch> (da origin/<source-branch>)                     │
├────────────────────────┼──────────────────────────────────────────────────────────┤
│ Effort                 │ <Low|Medium|High> — <motivo in poche parole>             │
├────────────────────────┼──────────────────────────────────────────────────────────┤
│ Prossimo passo         │ /trinity:workflow:2_work-issue <issue-id...> <model>    │
└────────────────────────┴──────────────────────────────────────────────────────────┘
```

Non mettere in tabella tipo, prefisso, SHA, commit, path del worktree, SmartGit e stato: se uno di
questi controlli fallisce, il command si ferma prima della tabella. Il prefisso è già nel nome del
branch.

Nell'output scrivila come tabella markdown a due colonne (`| Campo | Valore |`), non con i caratteri
di disegno del riquadro: fuori da un blocco di codice il renderer unisce le righe `│` in un
paragrafo e le manda a capo. Il riquadro sopra indica solo campi e ordine. Con più issue, la cella
«Issue Linear» diventa una riga della tabella per ogni issue.
