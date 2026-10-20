---
name: github-pr-release
version: "2.1.0"
# prettier-ignore
allowed-tools: Bash(git switch:*), Bash(git pull:*), Bash(git log:*), Bash(git add:*), Bash(git commit:*), Bash(git tag:*), Bash(git push:*), Bash(git status:*), Bash(git diff:*), Bash(gh repo view:*), Bash(gh release create:*), Bash(mise run:*), Bash(awk:*)
description: >-
  Release e versionamento di un progetto: versione SemVer, CHANGELOG.md curato, commit atomici, tag
  annotato e GitHub Release con gh. Usala quando l'utente chiede una release, un bump di versione,
  il changelog o il tag, anche in poche parole, e per rilasciare il plugin Trinity. Per lavorare su
  una issue o su una PR di feature usa la skill linear.
---

# Release e versionamento

Porta un progetto da "ci sono modifiche" a "esiste una versione pubblicata": commit atomici →
changelog curato → bump → tag → GitHub Release.

## Flusso

1. **Working tree pulito.** Se ci sono modifiche pendenti, trasformale prima in commit atomici
   seguendo [references/commit-triage.md](references/commit-triage.md).
2. **Parti dal branch di default aggiornato.** Rilevalo, non assumerlo:

   ```bash
   BASE=$(gh repo view --json defaultBranchRef -q .defaultBranchRef.name)
   git switch "$BASE"
   git pull --ff-only origin "$BASE"
   ```

3. **Verifica.** `mise run check`, o il comando di test del progetto. Se non esiste alcun check,
   dillo all'utente invece di saltarlo in silenzio.
4. **Changelog.** Segui [references/changelog.md](references/changelog.md) per struttura, curatela e
   scelta della versione. La release non passa da Linear: nessuna issue né PR per il bump, e nel
   changelog gli ID delle issue restano nudi (`ICH-14`).
5. **Bump come commit a sé.** Se il progetto ha una task di release (`mise run release <X.Y.Z>`),
   usala: tiene la versione coerente ovunque il progetto la scrive. Per il plugin Trinity leggi
   [references/trinity.md](references/trinity.md). Altrimenti aggiorna il file di versione e
   committa separatamente dai commit della feature: chi legge la history deve distinguere "cosa è
   cambiato" da "quando è stato rilasciato".

   ```bash
   git add <file-di-versione> CHANGELOG.md
   git commit -m "chore: bump 1.2.0"
   git tag -a v1.2.0 -m "Release v1.2.0"
   ```

6. **Checklist, poi push con conferma.** Prima del push copia questa lista nella risposta e spunta
   ogni voce:

   - [ ] working tree pulito → se no, torna al passo 1
   - [ ] test passati → se no, torna al passo 3
   - [ ] versione nel codice = versione nel changelog = tag → se no, torna al passo 4 o 5 (prima di
         ricreare il tag cancella quello locale con `git tag -d vX.Y.Z`)
   - [ ] changelog con i cambiamenti importanti, senza rumore → se no, torna al passo 4

   Se una voce fallisce, correggi e ripeti tutta la checklist. Commit, tag e branch restano locali e
   procedono senza chiedere. Il push invece rende pubblico il rilascio, e un errore pubblicato si
   corregge solo con un'altra release: mostra cosa verrebbe pubblicato e aspetta un OK esplicito,
   anche se di solito pushi senza chiedere. Poi fai un solo push per tutti i commit e il tag:

   ```bash
   git push --follow-tags origin "$BASE"
   ```

7. **GitHub Release**, con conferma come il push. Come note usa **solo** la sezione della versione,
   non l'intero CHANGELOG.md:

   ```bash
   VERSION=1.2.0
   NOTES=$(mktemp)
   awk -v ver="$VERSION" '$0 ~ "^## \\["ver"\\]" {flag=1; next} /^## \[/ {flag=0} flag' \
     CHANGELOG.md > "$NOTES"

   gh release create "v$VERSION" \
     --title "v$VERSION" \
     --notes-file "$NOTES"
   ```
