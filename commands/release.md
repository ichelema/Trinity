---
description: Versiona il plugin Trinity (bump version, commit, tag) e fa il push solo dopo conferma
argument-hint: "[major|minor|patch] oppure X.Y.Z (opzionale)"
---

# Release

Crea una nuova release del plugin Trinity: aggiorna `version` in
`.claude-plugin/plugin.json`, committa, crea il tag e — SOLO dopo conferma
esplicita — fa il push. MAI pushare in automatico.

Prima del bump, se ci sono modifiche pendenti, le organizza in **commit atomici**
(uno per intervento), ne propone i messaggi e li crea SOLO dopo tua validazione.
La parte meccanica (bump + commit + tag locale) è delegata alla task mise
`release`; questo comando aggiunge il triage dei commit, il giudizio sulla
versione e il gate di conferma sul push.

## Flusso operativo

1. **Triage delle modifiche pendenti → commit atomici**:
   - Esamina TUTTO il pendente: `git status --short`, `git diff`,
     `git diff --staged`; per i file non tracciati ispeziona il contenuto nuovo.
   - Raggruppa in **commit atomici**: un singolo intervento logico per commit
     (Sphynx vuole commit granulari). Per ogni gruppo prepara un messaggio
     **conventional commit** (`feat`/`fix`/`chore`/`docs`/`refactor`…), coerente
     con lo storico del repo.
   - **Mostra il piano e FERMATI per la validazione**: una tabella
     `# | messaggio | file`. L'utente può cambiare raggruppamenti, riscrivere i
     messaggi o escludere file. Non procedere senza OK esplicito.
   - Dopo l'OK, crea i commit **uno alla volta** con **staging selettivo**:
     - stage dei soli file del gruppo con `git add <paths>` (le eliminazioni si
       stageano con `git add <path-eliminato>`, oppure `git rm --cached <path>`
       per sola de-indicizzazione);
     - poi `git commit -m "<messaggio>"` **senza pathspec** (committa l'index
       così com'è).
     - ⚠️ NON usare `git commit -- <paths>`: con file untracked presenti rischia
       ri-tracciamenti involontari e rompe l'atomicità.
   - Se il working tree è già pulito, salta questa fase.
2. **Versione attuale**: leggi `version` da `.claude-plugin/plugin.json` e
   l'ultimo tag con `git describe --tags --abbrev=0`.
3. **Nuova versione** (semver `MAJOR.MINOR.PATCH`):
   - Se l'utente ha passato `X.Y.Z`, usala.
   - Se ha passato `major|minor|patch`, calcola il bump dalla versione attuale.
   - Altrimenti proponi un bump guardando i commit dall'ultimo tag/bump
     (`git log <ref>..HEAD --oneline`) e CHIEDI conferma prima di procedere.
4. **Bump (commit atomico a sé)** — bump + commit `chore(plugin): bump X.Y.Z` +
   tag annotato `vX.Y.Z`, tutto locale e separato dai commit della feature:

   ```bash
   mise run release <NUOVA_VERSIONE>
   ```

5. **Push finale (gate di conferma)**: un SOLO push per tutti i commit + il tag.
   Mostra cosa verrebbe pushato e CHIEDI conferma esplicita. Solo dopo l'OK:

   ```bash
   git push --follow-tags origin master
   ```

   Nota MSYS2: il push via SSH dal Bash tool può fallire perché msys2 ignora
   HOME/config — se succede, usa i percorsi SSH assoluti (vedi il workaround
   noto nella memoria nativa) e ripeti.

## Come scegliere la versione (SemVer)

Versione = `MAJOR.MINOR.PATCH`. Per Trinity la "API pubblica" sono gli hook, i
comandi, i tool MCP, lo schema di `hindsight.config.json` e i comportamenti su
cui l'utente fa affidamento. Riferimento completo: https://semver.org

- **PATCH** (`0.6.11` → `0.6.12`): bug fix retrocompatibili. Nessuno deve
  cambiare il modo in cui usa il plugin.
- **MINOR** (`0.6.x` → `0.7.0`): nuove funzionalità retrocompatibili (nuovo
  comando, nuovo hook, nuova opzione di config con default). Niente si rompe.
- **MAJOR** (`0.x` → `1.0.0`): cambiamenti che ROMPONO la compatibilità
  (comando rimosso/rinominato, chiave di config cambiata, comportamento di un
  hook che cambia in modo non retrocompatibile).

Nota 0.x: finché sei in `0.y.z` il progetto è considerato "in sviluppo
iniziale" e l'API non è stabile. Per convenzione i breaking change si segnano
bumpando il MINOR (`0.6.x` → `0.7.0`), tenendo `1.0.0` per la prima release
davvero stabile. Nel dubbio, in caso di breaking change in 0.x: bump MINOR.

In caso di dubbio tra due livelli, proponi quello più alto e CHIEDI conferma.

## Regole

- Mai fare push senza conferma esplicita dell'utente (vale anche la regola core
  "Per Git non fare push automatici"). Un solo push finale, dopo tutti i commit.
- Commit **granulari e atomici**: un intervento logico per commit, mai mischiare
  modifiche scollegate nello stesso commit.
- Crea i commit sempre con staging selettivo + `git commit` senza pathspec; non
  usare `git commit -- <paths>` (rompe l'atomicità con untracked presenti).
- Non committare mai senza aver prima mostrato e fatto validare il piano dei
  commit (file + messaggi).
- Il numero di versione deve combaciare tra `plugin.json` e il tag (`vX.Y.Z`).
- Mantieni la convenzione di commit esistente: `chore(plugin): bump X.Y.Z`.
- Non inventare un changelog: se serve, ricavalo dai commit reali tra le due
  versioni.
- Dopo un bump il manifest cambia: ricorda che il plugin viene riletto solo al
  riavvio di Claude Code.
