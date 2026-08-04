# Trinity — comportamento core

Le regole specifiche del singolo progetto (CLAUDE.md locale) hanno precedenza.

## Principi generali

Privilegia la cautela rispetto alla velocità; per task banali usa il buon senso.

- Prima di implementare, esplicita le assunzioni rilevanti.
- Se esistono più interpretazioni, presentale: non sceglierne una in silenzio.
- Se esiste un approccio più semplice, segnalalo e preferiscilo.
- Se qualcosa non è chiaro e impedisce una soluzione corretta, fermati, identifica il dubbio e chiedi.
- Verifica ogni assunzione, dichiara apertamente la confusione, porta in evidenza i tradeoff.

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

- Lascia intatti codice, commenti e formattazione adiacenti.
- Rifattorizza solo ciò che è rotto.
- Rispetta lo stile esistente, anche se lo faresti diversamente.
- Dead code preesistente o non correlato: segnalalo e rimuovilo solo su richiesta esplicita.
- Rimuovi import, variabili o funzioni che le tue modifiche hanno reso inutilizzati.
- Ogni riga modificata deve essere riconducibile direttamente alla richiesta dell'utente.

## Esecuzione guidata dagli obiettivi

**Definire i criteri di successo. Ripetere il ciclo fino alla verifica.**

Trasformare le attività in obiettivi verificabili:

- “Aggiungere la convalida” → “Scrivere test per input non validi, quindi farli superare”
- “Correggere il bug” → “Scrivere un test che lo riproduca, quindi farlo superare”
- “Rifattorizzare X” → “Assicurarsi che i test passino sia prima che dopo”

Per le attività in più fasi, definire un breve piano:

```
1. [Fase] → verificare: [controllo]
2. [Fase] → verificare: [controllo]
3. [Fase] → verificare: [controllo]
```

Criteri di successo ben definiti consentono di ripetere il ciclo in modo indipendente. Criteri vaghi (“farlo funzionare”) richiedono continui chiarimenti.

## Ambiente di lavoro

<!-- OS:windows -->

- OS: Windows 11 Enterprise.
- Shell: bash MSYS2 UCRT64 (`/usr/bin/bash`), `MSYSTEM=UCRT64`.
- Vault principale Obsidian: `${OBSIDIAN_VAULT}` (nome vault: `${OBSIDIAN_VAULT_NAME}`). Versione MSYS del path: ricavala con `cygpath -u "${OBSIDIAN_VAULT}"`.

<!-- /OS:windows -->

<!-- OS:linux -->

- OS: Linux.
- Shell: bash.
- Vault principale Obsidian (se presente su questa macchina): `${OBSIDIAN_VAULT}` (nome vault: `${OBSIDIAN_VAULT_NAME}`).

<!-- /OS:linux -->

## Regole operative

- Usa sintassi Unix compatibile bash/zsh (forward slash, `/dev/null`, pipe Unix): mai PowerShell o CMD.

<!-- OS:windows -->

- Se manca un programma di sistema, verifica prima con `command -v <bin>`, poi installalo con `pacman -S --noconfirm <pacchetto>`.

<!-- /OS:windows -->

<!-- OS:linux -->

- Se manca un programma di sistema, verifica prima con `command -v <bin>`, poi installalo col package manager della distro (es. `sudo apt-get install -y <pacchetto>`).

<!-- /OS:linux -->

- Mostra sempre l'output completo `stdout`/`stderr`. Se un comando fallisce, mostra l'errore completo all'utente prima di tentare un fix, e loggalo per il debug.
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

Quando esplori codice in un linguaggio con LSP attivo (oggi Python, TypeScript, Ruby, Lua), preferisci il tool `LSP` agli strumenti testuali:

- Trovare dove un simbolo è definito o usato → `LSP goToDefinition` / `findReferences`, non `grep` del nome.
- Tipi, firme, documentazione → `LSP hover`; struttura di un file → `LSP documentSymbol`.
- `grep`/`Grep` resta giusto per ricerca testuale (TODO, stringhe, config); `glob`/`Glob` per trovare file per nome.
- Se per il linguaggio non c'è un server LSP, usa `grep`/`glob`.

Per il workflow completo (analisi d'impatto prima di un refactor, diagnostica dopo gli edit) vedi la skill `lsp-enable`.

## Regole path

<!-- OS:windows -->

- I path MSYS2 (`/c/...`, `/e/...`) funzionano solo in bash.
- Ruby e Python girano nativamente su Windows e non riconoscono path MSYS.
- Negli script Python usa sempre path Windows: `C:/Appl/...`, `E:/doublecmd/...` oppure backslash.
- Negli script Python non usare mai path MSYS come `/c/...` o `/e/...`.

<!-- /OS:windows -->

<!-- OS:linux -->

- Usa sempre path POSIX assoluti: niente lettere di unità, niente `cygpath`, nessuna conversione necessaria.

<!-- /OS:linux -->

## Nushell per data processing

Per output tabulare, aggregazione o filtraggio su dati strutturati preferisci
Nushell (`$HOME/.local/bin/nu -c "..."`) a pipe testuali — vedi la skill `nushell`.

<!-- OS:windows -->

È un binario Windows nativo: passagli path Windows (`C:/...`), mai MSYS (`/c/...`).

<!-- /OS:windows -->

<!-- OS:linux -->

Se `nu` non è in `~/.local/bin`, usa quello nel PATH; i path sono POSIX normali.

<!-- /OS:linux -->

## Struttura directory dei progetti

Salvo indicazioni diverse del progetto, relative alla root del progetto corrente:
`<root>/data` per i dati, `<root>/logs` per i log, `<root>/script` per gli script,
`<root>/test` per i test e per i file di prova temporanei (`test_*.py`, `test_*.rb`,
script di prova non di progetto).
