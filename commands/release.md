---
description: Versiona il plugin Trinity (bump version, commit, tag) e fa il push solo dopo conferma
argument-hint: "[major|minor|patch] oppure X.Y.Z (opzionale)"
---

# Release

Crea una nuova release del plugin Trinity: aggiorna `version` in
`.claude-plugin/plugin.json`, committa, crea il tag e — SOLO dopo conferma
esplicita — fa il push. MAI pushare in automatico.

La parte meccanica (bump + commit + tag locale) è delegata alla task mise
`release`; questo comando aggiunge il giudizio sulla versione e il gate di
conferma sul push.

## Flusso operativo

1. **Stato pulito**: esegui `git status`. Se ci sono modifiche non committate
   NON correlate alla release, fermati e segnalalo: non includere file estranei
   nel commit di bump.
2. **Versione attuale**: leggi `version` da `.claude-plugin/plugin.json` e
   l'ultimo tag con `git describe --tags --abbrev=0` (il repo parte da 0 tag:
   il primo tag nasce da questa release in poi — non si retro-tagga lo storico).
3. **Nuova versione** (semver `MAJOR.MINOR.PATCH`):
   - Se l'utente ha passato `X.Y.Z`, usala.
   - Se ha passato `major|minor|patch`, calcola il bump dalla versione attuale.
   - Altrimenti proponi un bump guardando i commit dall'ultimo tag/bump
     (`git log <ref>..HEAD --oneline`) e CHIEDI conferma prima di procedere.
4. **Esegui la parte meccanica** (bump + commit `chore(plugin): bump X.Y.Z` +
   tag `vX.Y.Z`, tutto locale):

   ```bash
   mise run release <NUOVA_VERSIONE>
   ```

5. **Push (gate di conferma)**: mostra cosa verrebbe pushato (commit + tag) e
   CHIEDI conferma esplicita. Solo dopo l'OK:

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
  "Per Git non fare push automatici").
- Il numero di versione deve combaciare tra `plugin.json` e il tag (`vX.Y.Z`).
- Mantieni la convenzione di commit esistente: `chore(plugin): bump X.Y.Z`.
- Se `git status` non è pulito su file non correlati, fermati prima del commit.
- Non inventare un changelog: se serve, ricavalo dai commit reali tra le due
  versioni.
- Dopo un bump il manifest cambia: ricorda che il plugin viene riletto solo al
  riavvio di Claude Code.
