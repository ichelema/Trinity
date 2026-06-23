# Trinity — comportamento core

Queste regole valgono in OGNI progetto in cui il plugin trinity è attivo. Le regole specifiche del singolo progetto (CLAUDE.md locale) hanno precedenza in caso di conflitto.

## Principi generali

Queste linee guida riducono gli errori di coding comuni degli LLM. Privilegiano la cautela rispetto alla velocità; per task banali usa il buon senso.

- Rispondi sempre in italiano.
- Prima di implementare, esplicita le assunzioni rilevanti.
- Se esistono più interpretazioni, presentale: non sceglierne una in silenzio.
- Se esiste un approccio più semplice, segnalalo e preferiscilo.
- Se qualcosa non è chiaro e impedisce una soluzione corretta, fermati, identifica il dubbio e chiedi.
- Non dare nulla per scontato, non nascondere la confusione, porta in evidenza i tradeoff.

## Prima la semplicità

Scrivi il minimo codice che risolve il problema. Niente di speculativo.

- Nessuna funzionalità oltre a ciò che è stato richiesto.
- Nessuna astrazione per codice usato una sola volta.
- Nessuna flessibilità o configurabilità non richiesta.
- Nessuna gestione degli errori per scenari impossibili.
- Se scrivi 200 righe e potrebbero essere 50, riscrivile.
- Se un senior engineer direbbe che è troppo complicato, semplifica.

## Modifiche chirurgiche

Tocca solo ciò che devi. Ripulisci solo il tuo disordine.

- Non migliorare codice, commenti o formattazione adiacenti.
- Non fare refactoring di cose che non sono rotte.
- Rispetta lo stile esistente, anche se lo faresti diversamente.
- Se noti dead code non correlato, segnalalo: non cancellarlo.
- Rimuovi import, variabili o funzioni che le tue modifiche hanno reso inutilizzati.
- Non rimuovere dead code preesistente a meno che non venga chiesto.
- Ogni riga modificata deve essere riconducibile direttamente alla richiesta dell'utente.

## Esecuzione guidata dagli obiettivi

Definisci criteri di successo verificabili e itera fino alla verifica.

| Richiesta | Criterio operativo |
|---|---|
| Aggiungi la validazione | Scrivi test per input non validi, poi falli passare |
| Correggi il bug | Scrivi un test che lo riproduce, poi fallo passare |
| Fai il refactoring di X | Assicurati che i test passino prima e dopo |

Per task multi-step, enuncia un breve piano:

```text
1. [Step] → verifica: [check]
2. [Step] → verifica: [check]
3. [Step] → verifica: [check]
```

Criteri di successo solidi permettono di iterare in autonomia. Criteri deboli richiedono chiarimenti prima dell'implementazione.

## Ambiente di lavoro

- OS: Windows 11 Enterprise.
- Shell: bash MSYS2 UCRT64 (`/usr/bin/bash`), `MSYSTEM=UCRT64`.
- Vault principale Obsidian: `${OBSIDIAN_VAULT}` (nome vault: `${OBSIDIAN_VAULT_NAME}`). Versione MSYS del path: ricavala con `cygpath -u "${OBSIDIAN_VAULT}"`.

## Regole operative

- Usa sintassi Unix compatibile bash/zsh: forward slash, `/dev/null`, pipe Unix.
- Non usare PowerShell o CMD.
- Se manca un programma di sistema, verifica prima con `command -v <bin>`, poi installalo con `pacman -S --noconfirm <pacchetto>`.
- Mostra sempre l'output completo `stdout`/`stderr` dopo ogni comando.
- Se un comando fallisce, mostra l'errore completo prima di tentare un fix.
- Non silenziare mai gli errori.
- Mostra sempre feedback all'utente in caso di errore.
- Logga gli errori per debug.
- Non usare `--force` o operazioni distruttive senza conferma esplicita.
- Prima di sovrascrivere un file esistente, crea un backup con suffisso `.bak`.
- Non cancellare file senza conferma esplicita.

## Linguaggi e strumenti

- Usa Ruby come default per script.
- Per script Bash usa sempre shebang `#!/usr/bin/env bash`.
- Preferisci `curl` a `wget` per richieste HTTP.
- Per Git non fare push automatici: chiedi sempre conferma.
- Per Python, Node e Ruby usa sempre `mise` per installare pacchetti/runtime.

## Navigazione del codice

Quando esplori codice in un linguaggio con LSP attivo (oggi Python, TypeScript, Ruby), preferisci il tool `LSP` agli strumenti testuali:

- Trovare dove un simbolo è definito o usato → `LSP goToDefinition` / `findReferences`, non `grep` del nome.
- Tipi, firme, documentazione → `LSP hover`; struttura di un file → `LSP documentSymbol`.
- `grep`/`Grep` resta giusto per ricerca testuale (TODO, stringhe, config); `glob`/`Glob` per trovare file per nome.
- Se per il linguaggio non c'è un server LSP, usa `grep`/`glob`.

Per il workflow completo (analisi d'impatto prima di un refactor, diagnostica dopo gli edit) vedi la skill `lsp-enable`.

## Regole path

- I path MSYS2 (`/c/...`, `/e/...`) funzionano solo in bash.
- Ruby e Python girano nativamente su Windows e non riconoscono path MSYS.
- Negli script Python usa sempre path Windows: `C:/Appl/...`, `E:/doublecmd/...` oppure backslash.
- Negli script Python non usare mai path MSYS come `/c/...` o `/e/...`.

## Nushell per data processing

Usa Nushell quando l'output beneficia di formattazione tabulare, aggregazione o filtraggio:

```bash
$HOME/.local/bin/nu -c "..."
```

Nushell è un binario Windows nativo, non MSYS2: usa path Windows, non `/c/...` o `/e/...`.

- Corretto: `nu -c "open 'C:/Desktop/Claude/Main/data.json'"`
- Errato: `nu -c "open '/c/Desktop/Claude/Main/data.json'"`

### Casi d'uso Nushell

| Caso | Preferisci |
|---|---|
| Elencare file con filtri | `nu -c "ls | where size > 1mb | sort-by size"` invece di `ls -la | awk ...` |
| Leggere e filtrare JSON/CSV/YAML | `nu -c "open data.json | where status == 'active' | select name email"` invece di `cat data.json | jq ...` |
| Aggregazioni/report | `nu -c "ls | group-by type | transpose type files | insert count { |r| $r.files | length }"` |
| Conversione formati | `nu -c "open data.csv | to json"` |

### Quando non usare Nushell

Resta su bash per orchestrazione processi, pipe testuali semplici, scripting di sistema e comandi senza dati strutturati (`git`, `pacman`, `curl` senza parsing).

## Struttura directory dei progetti

Salvo indicazioni diverse del progetto, usa queste posizioni relative alla root del progetto corrente:

| Uso | Path |
|---|---|
| File di dati | `<root>/data` |
| Log | `<root>/logs` |
| Test | `<root>/test` |
| Script | `<root>/script` |
| File di test temporanei (`test_*.py`, `test_*.rb`, script di prova non di progetto) | `<root>/test` |

## Indicatore di qualità

Queste linee guida funzionano se producono meno modifiche non necessarie nei diff, meno riscritture dovute a complicazioni eccessive e domande di chiarimento prima dell'implementazione anziché dopo gli errori.
