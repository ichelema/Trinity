# CHANGELOG.md — struttura, curatela e scelta della versione

Il changelog è una lista **curata** dei cambiamenti rilevanti per utenti e
integratori del progetto. Non è una copia di `git log`: il lettore vuole
sapere cosa cambia per lui, non come è stato implementato.

## Struttura

```markdown
# Changelog

## [Unreleased]

## [1.2.0] - 2026-07-18

### Added
- ...

### Changed
- ...

### Deprecated
- ...

### Removed
- ...

### Fixed
- ...

### Security
- ...
```

## Regole di curatela

* Tenere `[Unreleased]` sempre in cima; a ogni release diventa la nuova
  sezione versionata e se ne ricrea uno vuoto.
* Date `YYYY-MM-DD`; versioni dalla più recente alla meno recente.
* Usare solo le categorie non vuote.
* Raggruppare più commit che producono lo stesso cambiamento in una voce sola.
* Descrivere l'**effetto per l'utente**, non i dettagli di implementazione.
* Rendere espliciti breaking change, migrazioni, deprecazioni e rimozioni.
* Omettere chore, refactor, test e modifiche interne senza effetto osservabile.

## Conversione da commit a voce di changelog

**Commit tecnico con effetto osservabile → riformulare per l'utente:**

```text
chore(eol): normalizza i fine-riga a LF
```

```markdown
### Changed
- Normalizzati i fine-riga a LF per rendere coerenti sviluppo e CI.
```

Se è solo una modifica interna senza conseguenze pratiche, ometterla.

**Documentazione nuova → Added:**

```text
docs: aggiunge la documentazione dei plugin e di Neovim utile per LLM
```

```markdown
### Added
- Aggiunta la documentazione sui plugin e sull'integrazione con Neovim.
```

**Fix con più dettagli tecnici → una voce sull'effetto:**

```text
fix(illuminate): evidenzia le occorrenze in azzurrino e riduce il delay
```

```markdown
### Fixed
- Migliorata l'evidenziazione delle occorrenze e ridotto il ritardo di aggiornamento.
```

**Refactor puro → omettere:**

```text
refactor(trouble): rimuove focus=false ridondante da <leader>kd
```

Omettere dal changelog, salvo che modifichi il comportamento osservabile.

## Scegliere la versione (Semantic Versioning)

Decidere guardando le voci accumulate in `[Unreleased]`:

| Contenuto di Unreleased | Bump |
|---|---|
| Breaking change, rimozioni, migrazioni obbligatorie | `MAJOR` (2.0.0) |
| Nuove funzionalità compatibili (`Added`, `Deprecated`) | `MINOR` (1.3.0) |
| Solo `Fixed`/`Changed`/`Security` compatibili | `PATCH` (1.2.1) |

In caso di dubbio tra MINOR e PATCH, chiedersi: "un utente deve cambiare
qualcosa o può fare qualcosa di nuovo?" Se sì → MINOR. Prima della 1.0.0 le
regole sono più lasche, ma restare coerenti dentro il progetto.
