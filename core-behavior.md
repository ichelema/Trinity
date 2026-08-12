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
- Scrivi codice minimale e segui un approcio pragmatico.

## Modifiche chirurgiche

Tocca solo ciò che devi

- Lascia intatti codice, commenti e formattazione adiacenti.
- Rifattorizza solo ciò che è rotto.
- Rispetta lo stile esistente.
- Dead code preesistente o non correlato: segnalalo e rimuovilo solo su richiesta esplicita.
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

## Regole operative

- Usa sintassi Unix compatibile bash/zsh (forward slash, `/dev/null`, pipe Unix): mai PowerShell o CMD.

- Se manca un programma di sistema, verifica prima con `command -v <bin>`, poi
  installalo con `pacman -S --noconfirm <pacchetto>`.

- Quando esplori codice preferisci il tool `LSP` agli strumenti testuali.

- Non usare `--force` o operazioni distruttive senza conferma esplicita.

- Prima di sovrascrivere un file esistente, crea un backup con suffisso `.bak`.

## Assistenza proattiva

Sii proattivo, non limitarti a rispondere alle richieste.

Usa ciò che sai su di me, i miei obiettivi, progetti, vincoli e decisioni precedenti per:

- Individuare informazioni mancanti che potrebbero aiutarti ad assistermi meglio.

- Farmi domande mirate solo quando possono migliorare concretamente il risultato.

- Proporre attività che puoi svolgere subito per farmi avanzare verso i miei obiettivi.

- Segnalare opportunità di semplificazione, automazione o eliminazione di lavoro ripetitivo.

## Linguaggi e strumenti

- Usa Ruby come default per script.
- Per script Bash usa sempre shebang `#!/usr/bin/env bash`.
- Preferisci `curl` a `wget` per richieste HTTP.
- Per Python, Node e Ruby usa sempre `mise` per installare pacchetti/runtime.


## Output

- Minimizza l'output shell: sopprimi stdout/stderr quando non serve,
  preferisci flag quiet (`-q`, `--quiet`), filtra i comandi verbosi con
  `tail`/`head`/`grep`, e non riportare mai output voluminosi di
  build/test/install se non servono alla diagnosi.

- Per diagnosticare un fallimento, cattura l'output verboso su file nello
  scratchpad e ispeziona solo le porzioni rilevanti.

- Se un comando fallisce, mostra comunque l'errore completo all'utente prima
  di tentare un fix, e loggalo per il debug.

- Per output tabulare, aggregazione o filtraggio su dati strutturati preferisci
  Nushell (`$HOME/.local/bin/nu -c "..."`) a pipe testuali — vedi la skill `nushell`.

<!-- RETAIN:manual -->
## Retain a fine task

Al termine di un task significativo, valuta se il lavoro ha prodotto conoscenza
durevole che meriti di essere persistita. Salva solo se l'informazione è verificata,
non ovvia e probabilmente utile nelle sessioni future (decisioni con la loro
motivazione, cause radice e workaround, vincoli specifici dell'ambiente, approcci
scartati rilevanti).

NON salvare: stato temporaneo, output banale, dati ricavabili dal repository,
tentativi intermedi, duplicati.

Se sì: avvisa con UNA frase breve, poi chiama subito `mcp__hindsight__retain` così:

- `content`: forma breve e autosufficiente che spieghi il PERCHÉ, coi dettagli
  tecnici (comandi, path, valori) preservati alla lettera.
- `context`: una riga descrittiva del dominio (es. "gestione bank e config
  Hindsight nel progetto Trinity") — MAI una categoria secca né il nome del bank.
- `tags`: SOLO universali — `claude-code`, più `repo:<nome>` se specifico del
  progetto e `branch:<nome>` solo se davvero legato al branch. NIENTE tag
  semantici (bug, convention, preferenze…): frammentano la consolidation.

Se no: non fare nulla.

Se incerto: chiedimelo con un breve riassunto di ciò che salveresti.
<!-- /RETAIN:manual -->


