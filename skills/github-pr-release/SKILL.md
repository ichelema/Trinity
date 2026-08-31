---
name: github-pr-release
version: "2.0.0"
allowed-tools: Bash(git switch:*), Bash(git pull:*), Bash(git log:*), Bash(git add:*), Bash(git commit:*), Bash(git tag:*), Bash(git push:*), Bash(git status:*), Bash(git diff:*), Bash(gh repo view:*), Bash(gh release create:*), Bash(mise run:*), Bash(awk:*)
description: >
  Release e versionamento di un progetto: scelta della versione SemVer, curatela
  del CHANGELOG.md, triage delle modifiche pendenti in commit atomici, tag annotato
  e GitHub Release via gh CLI. Usala per "facciamo la release", "prepara la versione",
  "bump di versione", "aggiorna il changelog", "crea il tag", "pubblica la release",
  anche su richieste brevi e senza dettagli. Copre anche il rilascio del plugin Trinity.
  Non usarla per lavorare su una issue o per aprire e mergiare una PR di feature:
  quello è della skill linear.
---

# Release e versionamento

Porta un progetto da "ci sono modifiche" a "esiste una versione pubblicata":
commit atomici → changelog curato → bump → tag → GitHub Release.

## Confine con la skill `linear`

| Richiesta | Skill |
| --- | --- |
| Lavorare su una issue, aprire o mergiare la PR di una feature | `linear` |
| Rilasciare una versione, bump, changelog, tag | questa |

Le due si incontrano in un punto solo: il changelog cita le issue rilasciate.
Vedi "Non disallineare Linear" sotto.

## Flusso

1. **Working tree pulito.** Se ci sono modifiche pendenti, trasformale prima in
   commit atomici seguendo [references/commit-triage.md](references/commit-triage.md).
2. **Parti dal branch di default aggiornato.** Rilevalo, non assumerlo:

   ```bash
   BASE=$(gh repo view --json defaultBranchRef -q .defaultBranchRef.name)
   git switch "$BASE"
   git pull --ff-only origin "$BASE"
   ```

3. **Verifica.** `mise run check`, o il comando di test del progetto. Se non
   esiste alcun check, dillo all'utente invece di saltarlo in silenzio.
4. **Changelog.** Leggi [references/changelog.md](references/changelog.md) per
   struttura, curatela e scelta della versione. In sintesi: raccogli i commit
   dall'ultimo tag (`git log <ultimo-tag>..HEAD --oneline`), aggiorna le voci di
   `[Unreleased]`, trasformalo in `## [x.y.z] - YYYY-MM-DD`, ricrea un
   `[Unreleased]` vuoto in cima.
5. **Bump come commit a sé.** Aggiorna il file di versione del progetto e
   committa separatamente dai commit della feature: chi legge la history deve
   distinguere "cosa è cambiato" da "quando è stato rilasciato".

   ```bash
   git add <file-di-versione> CHANGELOG.md
   git commit -m "chore: bump 1.2.0"
   git tag -a v1.2.0 -m "Release v1.2.0"
   ```

6. **Push, con conferma.** Un solo push per tutti i commit e il tag. Mostra cosa
   verrebbe pubblicato e attendi un OK esplicito:

   ```bash
   git push --follow-tags origin "$BASE"
   ```

7. **GitHub Release**, usando **solo** la sezione della versione come note, mai
   l'intero CHANGELOG.md:

   ```bash
   VERSION=1.2.0
   awk -v ver="$VERSION" '$0 ~ "^## \\["ver"\\]" {flag=1; next} /^## \[/ {flag=0} flag' \
     CHANGELOG.md > "$TMPDIR/release-notes.md"

   gh release create "v$VERSION" \
     --title "v$VERSION" \
     --notes-file "$TMPDIR/release-notes.md"
   ```

## Conferme

Tutto ciò che resta nel repository locale (commit, tag, branch) procede senza
chiedere. Tutto ciò che esce — `git push`, `gh release create` — richiede una
conferma esplicita: è il confine oltre il quale un errore diventa pubblico e si
corregge solo con un'altra release.

## Non disallineare Linear

Una release **non passa da una issue**: è lavoro di repository, non di prodotto.
Non creare un'issue Linear per il bump, non aprire una PR di release, non usare
magic words. Non c'è niente da tenere allineato perché non c'è niente di
parallelo, e la tracciabilità esiste già in entrambe le direzioni — da Linear
vedi la PR come attachment, dal changelog vedi l'ID issue.

Il punto in cui si rompe è il testo: `Fixes ICH-14` dentro il changelog o nel
messaggio del commit di release fa ricollegare a Linear issue già chiuse,
attaccandole al rilascio invece che alla PR che le ha risolte. Nel changelog gli
ID vanno **nudi** (`ICH-14`). Dettagli in
[references/changelog.md](references/changelog.md).

Se il workspace Linear ha una release pipeline configurata, esiste anche
l'allineamento esplicito via `save_release`; senza pipeline (il caso di default)
non serve e non va simulato con issue finte.

## Progetti con release automatizzata

Alcuni progetti hanno già una task che fa bump, commit e tag insieme: usala
invece di rifare i passi a mano, così la versione resta coerente ovunque il
progetto la scriva.

```bash
mise run release <NUOVA_VERSIONE>
```

**Plugin Trinity** (`E:/AI/Claude/Trinity`): la versione sta in
`.claude-plugin/plugin.json`, la task `mise run release <X.Y.Z>` fa bump +
commit `chore(plugin): bump X.Y.Z` + tag `vX.Y.Z` in locale. La "API pubblica"
su cui giudicare il SemVer sono gli hook, i comandi, le skill, i tool MCP e lo
schema di `hindsight.config.json`. Il numero in `plugin.json` deve combaciare
col tag. Dopo il bump il manifest cambia, ma Claude Code lo rilegge solo al
riavvio.

Su Windows/MSYS2 il push via SSH dal Bash tool può fallire perché msys2 ignora
`HOME`/config: in quel caso usa i percorsi SSH assoluti e ripeti.

## Checklist pre-release

Verifica e mostra l'esito:

- [ ] working tree pulito
- [ ] test passati
- [ ] versione nel codice = versione nel changelog = tag
- [ ] changelog che descrive i cambiamenti importanti, senza rumore
