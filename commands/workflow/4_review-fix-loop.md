---
description:
  Due review indipendenti in parallelo (trinity:reviewer su Fable e su GPT) su worktree isolati, loop
  di fix minimi e report finale
argument-hint: <issue-id...> <model>
disable-model-invocation: true
---

Esegui due review indipendenti e parallele della PR delle issue indicate su worktree isolati, poi
applica i fix che meritano di essere fatti in un loop, finché non emergono più finding. In uscita,
report sintetico.

Le due review usano lo stesso agente `trinity:reviewer` su due modelli diversi: Fable (default
dell'agente) e GPT 5.6 sol xhigh (`claude-gpt-5-6-sol-xhigh` via proxy LiteLLM).

L'ultimo argomento è il modello: identifica il worktree di implementazione creato da
`/1_create-worktree` (e quindi il branch della PR). Non sceglie il modello di esecuzione.

## Validazione degli argomenti

Dividi `$ARGUMENTS` in token separati da spazi:

- l'ultimo token è il modello di implementazione;
- i token precedenti sono gli issue ID (almeno uno).

Se i token sono meno di 2, fermati e mostra:

`/trinity:workflow:4_review-fix-loop <issue-id...> <model>`

## Localizzazione del worktree e della PR

Non ricostruire il prefisso: ricava il worktree dallo stato reale di Git.

```bash
git worktree list --porcelain
```

Cerca l'entry il cui branch termina esattamente con `/<base-name>`, dove `<base-name>` segue la
regola dello step 1: una sola issue → `<issue-id>-<model>` (es. `improvments/ICH-84-fable`); più
issue → prefisso team una sola volta, poi i numeri delle successive, infine il modello (es.
`improvments/ICH-97-98-fable`). Da quella entry ricava `<wt-path>` e `<branch>`.

Se non esiste, fermati: il worktree di implementazione va creato prima con `/1_create-worktree`.

Verifica che esista una PR aperta per `<branch>`:

```bash
gh pr view "<branch>" --json url,state,title -q '.url'
```

Se non esiste, fermati e chiedi all'utente di aprirla o di passarti l'URL: la review parte dalla PR,
non da un branch orfano.

## Round di review parallela

Per ogni round:

1. Crea due worktree di review isolati e detached (senza branch: il reviewer non committa), uno per
   reviewer, con path assoluti in formato Windows (`E:/...`) su Windows/MSYS2:
   ```bash
   git fetch origin
   repo_root="$(git rev-parse --path-format=absolute --git-common-dir)"; repo_root="${repo_root%/.git}"
   command -v cygpath >/dev/null && repo_root="$(cygpath -m "$repo_root")"   # solo Windows/MSYS2
   sha="$(git rev-parse --verify "origin/<branch>^{commit}")"
   git worktree add --detach "$repo_root/.claude/worktrees/review+<base-name>-gpt" "$sha"
   git worktree add --detach "$repo_root/.claude/worktrees/review+<base-name>-fable" "$sha"
   ```
   Se una delle directory esiste già (round precedente non ripulito), fermati. Non toccare il file
   `.git` dentro i worktree.
2. Esegui `/trinity:workflow:3_independent-review` sui due worktree in parallelo, uno per reviewer,
   con argomenti `<issue-id...> <model> <review-wt-path>`. Il command ha
   `disable-model-invocation: true`: né tu né un subagente potete invocarlo come slash command, e un
   `/...` nel prompt di un subagente non viene espanso.
   Ogni reviewer scrive i file di appoggio solo in `<review-wt-path>/.review-tmp/`, mai altrove.
   - review `fable`: tool Agent con `subagent_type: trinity:reviewer`; nel prompt digli
     di leggere `${CLAUDE_PLUGIN_ROOT}/commands/workflow/3_independent-review.md` e di seguirlo con
     quegli argomenti al posto di `$ARGUMENTS`;
   - review `gpt`: il tool Agent non può scegliere GPT, quindi lanciala da Bash con una
     sessione headless sul proxy LiteLLM già avviato, con lo stesso agente:
     ```bash
     ANTHROPIC_BASE_URL="http://127.0.0.1:4000" \
     ANTHROPIC_AUTH_TOKEN="$(cat ~/.litellm/master-key.txt)" \
     ANTHROPIC_DEFAULT_FABLE_MODEL="claude-gpt-5-6-sol-xhigh" \
     ANTHROPIC_DEFAULT_SONNET_MODEL="claude-gpt-5-6-sol-high" \
     GH_CONFIG_DIR="$(cygpath -w ~/.config/gh)" \
     ~/.local/bin/claude.exe -p --agent trinity:reviewer --model claude-gpt-5-6-sol-xhigh \
       "/trinity:workflow:3_independent-review <issue-id...> <model> <review-wt-path>" \
       2> >(grep -v '^\[claude-code:unrecognized_model\]' >&2)
     ```
     `ANTHROPIC_DEFAULT_FABLE_MODEL` serve perché `3_independent-review` ha `model: fable` nel
     frontmatter: senza mappatura la sessione chiede al proxy `claude-fable-5-1` e fallisce con
     400. `ANTHROPIC_DEFAULT_SONNET_MODEL` serve al classificatore della modalità auto: con
     `--agent` il classificatore chiede `claude-sonnet-5` e poi `claude-opus-5`, che il proxy non
     ha, e blocca ogni comando Bash; la mappatura gli dà subito un modello GPT che risponde, e la
     review resta su `claude-gpt-5-6-sol-xhigh`. `GH_CONFIG_DIR` serve perché `gh` nella sessione
     headless trovi il login; il filtro su stderr toglie solo l'avviso innocuo `unrecognized_model`
     (Claude Code non conosce il nome `claude-gpt-5-6-sol-xhigh`). Se `<model>` coincide con uno
     dei due modelli di review (`fable` o `gpt`), segnalalo: quella review gira sullo stesso
     modello che ha scritto il codice ed è meno indipendente.
3. Raccogli i due report.
4. Rimuovi i due worktree leggendo e seguendo
   `${CLAUDE_PLUGIN_ROOT}/commands/workflow/5_remove-worktree.md` (per lo stesso motivo non puoi
   invocarlo come slash command), con `$worktree_name` = `<review-wt-path>`.

Le review sono read-only: nessun reviewer modifica file.

## Triage dei finding

Fondi i due report e per ogni finding decidi se è reale e merita un fix:

- è verificabile nel codice, non un'ipotesi;
- è un difetto o una violazione di requisito, non una preferenza stilistica;
- è dentro lo scope delle issue.

L'accordo dei due reviewer è un segnale forte ma non una prova: verifica comunque ogni finding nel
codice. La discordanza non è un motivo per scartare: controlla il finding singolarmente. Scarta i
falsi positivi e le preferenze stilistiche, senza riproporli nel round successivo.

## Fix minimi e chirurgici

Sul worktree di implementazione `<wt-path>`, applica solo i finding reali:

- prima del primo fix entra con un comando a sé, `cd "<wt-path>"`; dopo il push, o se ti fermi
  prima, esci con `cd "<repo-root>"`: lo step 5 non può cancellare la cwd della sessione;
- comandi sempre con `git -C "<wt-path>"`, `mise -C "<wt-path>"` e path assoluti;
- la minima modifica che risolve il difetto;
- nessun refactoring, nessuna riscrittura, nessun cambio di architettura;
- ogni riga modificata è riconducibile a un finding verificato;
- commit in inglese, uno per fix logico;
- push per aggiornare la PR.

Se un finding non si risolve con un fix minimo, non improvvisare una soluzione più ampia: segnalalo
nel report come criticità e chiedi.

## Loop

Ripeti round → triage → fix finché un round completo non produce alcun finding da fixare, con un
massimo di 3 round. Dal secondo round in poi fixa solo `BLOCKER`, `HIGH` e `MEDIUM`: i `LOW` vanno
nel report come residui, non in un nuovo giro.

Fermati e segnala se:

- hai completato il terzo round e restano finding da fixare: elencali nel report con il motivo;
- due round consecutivi ripropongono lo stesso finding già scartato come falso positivo (i due
  reviewer non convergono: disaccordo di fondo);
- un fix ne introduce un altro a valanga (il fix non era minimo).

## Report finale

Report sintetico, solo informazioni rilevanti:

- cosa è stato fixato (finding → fix, con file e righe);
- trade-off introdotti dai fix (se presenti);
- criticità residue o finding non risolti e perché;
- verdetto finale: PR pronta per il merge o no.

Se qualcosa non è chiaro, è contraddittorio o hai dubbi, chiedi prima di procedere. Altrimenti
mettiti al lavoro.
