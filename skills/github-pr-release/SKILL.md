---
name: github-pr-release
version: "1.0.0"
description: >
  Lightweight Git/GitHub workflow for personal projects: feature branches, atomic
  commits, pull requests merged with a merge commit, curated CHANGELOG.md, SemVer
  releases with annotated tags and GitHub Releases via the gh CLI. Use whenever the
  user wants to start a feature/fix/hotfix branch, open, update, check or merge a PR,
  bring a branch back into main, prepare or publish a release, bump a version, update
  a changelog, or create a tag — any "release", "rilascio", "apri la PR", "merge in
  main", "prepara la versione" request on a project. Trigger even for short requests
  like "facciamo la release" or "chiudi la PR" without further detail. Do NOT use for
  releasing the Trinity plugin itself — that has its own /trinity:release command.
---

# GitHub PR e Release

Flusso leggero per gestire un progetto personale con Git, GitHub CLI (`gh`) e `mise`:
`main` stabile, branch brevi, commit atomici, PR quando utile, release taggate.

## Come usare questa skill

1. Identifica cosa chiede l'utente: **feature/fix** (branch → commit → PR),
   **merge** di una PR, oppure **release**. Segui la sezione corrispondente.
2. Prima di iniziare controlla lo stato del repository (`git status`, branch corrente):
   sessioni parallele o file staged altrui finiscono nei commit per sbaglio.
3. Chiedi sempre conferma all'utente prima delle operazioni che escono dal repo
   locale: `git push`, `gh pr create`, `gh pr merge`, `gh release create`.
   Tutto il resto (branch, commit, check) procede senza conferma.

## Regole del flusso

* `main` è sempre stabile e rilasciabile.
* Branch brevi: `feature/*`, `fix/*`, `hotfix/*`. Niente branch `develop`
  permanente salvo una reale necessità del progetto.
* I commit sono atomici e descrivono passi tecnici coerenti: un cambiamento
  logico per commit, così history, revert e review restano leggibili.
* La PR rappresenta una modifica funzionale; può contenere più commit.
* Il merge usa un **merge commit**: conserva tutti i commit e li raggruppa
  visibilmente sotto la loro PR nella history.

## Feature e PR

Partire sempre da `main` aggiornato:

```bash
git switch main
git pull --ff-only origin main
git switch -c feature/<nome-feature>
```

Creare commit atomici, uno per passo logico:

```bash
git add lib/result.rb
git commit -m "Add Result#try"

git add test/result_test.rb
git commit -m "Cover Result#try failure paths"

git add README.md
git commit -m "Document Result#try migration"
```

Prima di pubblicare, verificare diff, history e test:

```bash
git log --oneline --graph main..HEAD
git diff --stat main...HEAD
git diff main...HEAD
mise run check
```

Se il progetto non ha un task `mise`, usare il comando di test del progetto
(per esempio `bundle exec rake`). Se non esiste alcun check, segnalarlo
all'utente invece di saltare la verifica in silenzio.

Pubblicare il branch e creare la PR (con conferma dell'utente):

```bash
git push -u origin feature/<nome-feature>

gh pr create \
  --base main \
  --head feature/<nome-feature> \
  --title "Add Result#try" \
  --body "## Summary
- Add Result#try
- Add tests and documentation

## Verification
- mise run check"
```

Una PR si aggiorna con normali commit e `git push`. Prima del merge:

```bash
gh pr checks <numero-pr>
gh pr view <numero-pr>
```

## Merge della PR

Usare il merge commit per conservare tutti i commit e mostrare che
appartengono alla stessa PR:

```bash
gh pr merge <numero-pr> --merge
```

Non usare `--squash`: distrugge la storia dei commit atomici. Non usare
`--rebase`: conserva i commit ma non crea il nodo di merge che raggruppa la PR.

Dopo il merge, riallineare il locale e pulire:

```bash
git switch main
git pull --ff-only origin main
git branch -d feature/<nome-feature>
git fetch --prune
```

## Release

Prima di preparare il changelog leggi [references/changelog.md](references/changelog.md):
contiene struttura, regole di curatela e la guida per scegliere la versione SemVer.

Partire da `main` aggiornato e verificato:

```bash
git switch main
git pull --ff-only origin main
mise run check
```

Preparare il changelog:

1. leggere commit e PR dall'ultima release (`git log <ultimo-tag>..HEAD --oneline`);
2. aggiornare le voci in `[Unreleased]`, eliminando il rumore tecnico;
3. trasformare `[Unreleased]` in `## [x.y.z] - YYYY-MM-DD`;
4. aggiungere in cima un nuovo `## [Unreleased]` vuoto.

Scegliere la versione con Semantic Versioning: `MAJOR` per breaking change,
`MINOR` per funzionalità compatibili, `PATCH` per bug fix compatibili
(dettagli nel reference). Aggiornare il file di versione del progetto
(per esempio `lib/<package>/version.rb`) e creare il commit di release:

```bash
git add lib/<package>/version.rb CHANGELOG.md
git commit -m "Release v1.2.0"
```

Creare il tag annotato e pubblicare (con conferma dell'utente):

```bash
git tag -a v1.2.0 -m "Release v1.2.0"
git push origin main --follow-tags
```

Pubblicare la GitHub Release usando **solo la sezione della versione** come
note — mai l'intero CHANGELOG.md:

```bash
VERSION=1.2.0
awk -v ver="$VERSION" '$0 ~ "^## \\["ver"\\]" {flag=1; next} /^## \[/ {flag=0} flag' \
  CHANGELOG.md > "$TMPDIR/release-notes.md"

gh release create "v$VERSION" \
  --title "v$VERSION" \
  --notes-file "$TMPDIR/release-notes.md"
```

### Checklist pre-release

Verificare, mostrando l'esito all'utente:

- [ ] `main` pulito (`git status` senza modifiche pendenti);
- [ ] test passati (`mise run check` o equivalente);
- [ ] versione nel codice = versione nel changelog = tag;
- [ ] changelog che descrive tutti i cambiamenti importanti, senza rumore.

## Automazione con mise

Usare `mise` come punto di ingresso per i task ricorrenti. Un `Rakefile` solo
per task che richiedono logica Ruby; `Procfile`/`overmind` solo per processi
persistenti.

```toml
[tasks.check]
run = "bundle exec rake"

[tasks.pr]
run = "git diff --stat main...HEAD && git log --oneline --graph main..HEAD && mise run check"

[tasks.release]
run = "mise run check && git status --short"
```

Se il progetto non ha ancora questi task, proporli all'utente invece di
crearli d'ufficio.
