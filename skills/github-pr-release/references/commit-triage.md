# Triage delle modifiche pendenti in commit atomici

Usa questo workflow quando il working tree contiene modifiche non committate e
vanno trasformate in una storia leggibile prima di rilasciare.

Un commit che mescola interventi scollegati non si può revertare, non si può
rivedere e non si può raccontare nel changelog: il triage serve a rendere ogni
riga della history riconducibile a una singola decisione.

## 1. Esamina tutto il pendente

```bash
git status --short
git diff
git diff --staged
```

Per i file non tracciati ispeziona il contenuto: `git diff` non li mostra, e
sono spesso la parte più significativa del lavoro.

## 2. Raggruppa in commit atomici

Un singolo intervento logico per commit. Per ogni gruppo prepara un messaggio
**conventional commit** (`feat`, `fix`, `chore`, `docs`, `refactor`, `test`,
`style`) coerente con lo storico del repository — guardalo con
`git log --oneline -20` invece di assumere una convenzione.

## 3. Mostra il piano e fermati

Presenta una tabella e attendi l'OK:

| # | Messaggio | File |
| --- | --- | --- |
| 1 | `fix(auth): gestisce il token scaduto` | `src/auth.ts` |
| 2 | `test(auth): copre il refresh fallito` | `test/auth.spec.ts` |

L'utente può cambiare i raggruppamenti, riscrivere i messaggi o escludere file.
Non creare nessun commit prima di una risposta esplicita: dopo, disfare
richiede `git reset` e la fiducia su cosa fosse staged è già persa.

## 4. Crea i commit uno alla volta

Stage selettivo dei soli file del gruppo, poi commit **senza pathspec**:

```bash
git add src/auth.ts
git commit -m "fix(auth): gestisce il token scaduto"
```

Le eliminazioni si stageano con `git add <path-eliminato>`, oppure
`git rm --cached <path>` per la sola de-indicizzazione.

**Non usare `git commit -- <paths>`.** Con file untracked presenti può
ri-tracciare file che avevi escluso di proposito, e il commit non corrisponde
più a quello che l'utente ha approvato. La forma `git add` + `git commit`
committa l'index così com'è, che è esattamente ciò che hai mostrato.

Se il working tree è già pulito, salta questo workflow.
