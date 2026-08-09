# Creare e modificare le Note del Giorno in Obsidian

Reference operativa per Claude Code: creare e aggiornare le Note del Giorno (daily
note) nel Vault Obsidian, partendo dal Template `templates/Template-Daily.md`.

La daily serve come **storico del lavoro svolto** in giornata: cosa è stato fatto,
come, e con quali dettagli tecnici, in forma interrogabile da un LLM in futuro.

- Cartella: `🌅Daily/YYYY-MM/` (sottocartella mensile, es. `🌅Daily/2026-07/`)
- Nome file: `YYYY-MM-DD.md` (es. `🌅Daily/2026-06/2026-06-25.md`)
- Template base: `templates/Template-Daily.md`

> Prima di concludere che la daily di oggi non esiste, cerca nel vault
> `file:YYYY-MM-DD`: il path passa per la sottocartella mensile.

---

## Workflow: estrazione informazioni dalla sessione → vault Obsidian

1. **Raccogli** dalla sessione corrente: obiettivi, cosa è stato fatto, risultati,
   issue Linear chiuse, dettagli tecnici (commit, file, comandi, numeri esatti).
   Non inventare nulla: usa solo ciò che è realmente avvenuto nella sessione.
2. **Carica il template** `templates/Template-Daily.md` come scheletro.
3. **Mappa un task = una sessione**: ogni task significativo della giornata diventa
   un blocco `###` dentro `## 🤖 Riassunto sessione Agente AI`.
4. **Compila** le sezioni (vedi struttura sotto).
5. **Mostra la bozza all'utente** prima di scrivere, se richiesto.
6. **Crea/aggiorna** la nota via MCP (`vault create` / `edit`), poi aprila con
   `view open_in_obsidian`.
7. **Formatta** la nota con Prettier prima della verifica finale:

   ```bash
   prettier --write "🌅Daily/<YYYY-MM>/<YYYY-MM-DD>.md" --print-width 130 --prose-wrap always
   ```

8. **Verifica** che i link interni `[[#...]]` risolvano e che i contenuti siano
   coerenti con la sessione.

---

## Struttura della nota

Segui il Template `Template-Daily.md`. Convenzioni reali (dedotte dalle daily del
Vault), che il template lascia implicite:

### Frontmatter

Copia il frontmatter del template, **senza virgolette** sui valori di data:

```yaml
---
type:
  - 📝nota
nota_type:
  - 🌄daily
data_creazione: 2026-06-25T02:50:00
data_modifica: 2026-06-25T03:27:58
---
```

### Titolo H1

Formato `# DD-MM-YYYY - Daily Note` (giorno-mese-anno, **invertito** rispetto al
nome file).

### `## 🎯 Obiettivi`

I task principali della giornata come checkbox **linkati con alias** all'header della
loro sessione nel riassunto. Forma obbligatoria: `[[#<header esatto>|<alias>]]`, dove:

- l'**ancora** (prima di `|`) è **identica** all'header `###` della sessione — è ciò
  che fa risolvere il link;
- l'**alias** (dopo `|`) è il testo mostrato, nel formato `<Stato> - <descrizione>`, con
  `<Stato>` che riflette l'esito del task (es. `Fixed`, `Commited`, `Aggiunto`, `Risolto`).

```markdown
- [x] [[#Fix hook SessionEnd di Hindsight|Fixed - hook SessionEnd di Hindsight]]
- [x] [[#Commit di pulizia del repository Trinity|Commited - di pulizia del repository Trinity]]
- [x] [[#Comando nota del giorno per il plugin Trinity|Aggiunto - Comando nota del giorno per il plugin Trinity]]
```

### `## ✅ Issue chiuse`

Le issue Linear portate a **Done** durante la giornata, in un blocco che il
plugin Linear di Obsidian rende come card:

````markdown
## ✅ Issue chiuse

```linear
ids:
  - ICH-16
  - ICH-22
```
````

Per una sola issue si usa la forma singolare:

````markdown
```linear
id: ICH-16
```
````

Il blocco contiene **solo l'ID**, mai titolo o stato copiati a mano: la card
mostra sempre il valore corrente della issue, mentre un titolo incollato
invecchia dal giorno dopo. Un agente che legge il markdown grezzo vede l'ID e
può interrogare Linear per il resto — il rendering avviene solo dentro Obsidian.

Regole di compilazione:

- Elenca solo le issue **effettivamente chiuse** quel giorno, non quelle su cui
  hai lavorato: quelle stanno in 🎯 Obiettivi e nel riassunto.
- Verifica lo stato reale su Linear prima di inserirle (`get_issue`), invece di
  dedurlo dal fatto che la PR è stata mergiata.
- Se non hai chiuso nulla, lascia il blocco vuoto come nel template.
- Gli ID vanno **nudi**, senza magic words (`Fixes`, `Closes`): nella daily non
  servono, e altrove farebbero richiudere a Linear issue già chiuse.

### `## 🤖 Riassunto sessione Agente AI`

Cuore della nota. Struttura:

- Un **paragrafo introduttivo** che riassume la giornata in 1-3 frasi.
- **Un blocco `###` per ogni task**, dove il testo dell'header è **identico** all'ancora
  linkata in 🎯 Obiettivi (la parte prima di `|`): è ciò che fa funzionare il link
  `[[#header|alias]]`.
- **Separa un blocco `###` dal successivo con un `---`** su riga propria (thematic
  break), una riga vuota prima e una dopo.
- Ogni blocco `###` contiene i quattro sotto-heading `####` del template:
  - `#### Obiettivo` — cosa volevamo ottenere e perché
  - `#### Cosa è stato fatto` — i passaggi in modo umano, incl. difficoltà
  - `#### Risultato ottenuto` — pieno/parziale e cosa abbiamo, sintetico
  - `#### Dettagli tecnici` — commit, file, comandi, numeri esatti (per audit)

Esempio di due sessioni separate dal `---`:

```markdown
### Primo task
#### Obiettivo
...
#### Dettagli tecnici
...

---

### Secondo task
#### Obiettivo
...
```

### Altre sezioni

`⚡ Inbox rapida`, `🪶 Appunti`, `📚 Cose apprese oggi`,
`Concetti da trasformare in note` si compilano se ci sono contenuti reali;
altrimenti si lasciano vuote come nel template. I `[[link]]` a note non ancora
esistenti vanno segnalati come proposti.

---

## Regole operative essenziali

- **Niente tag nella nota**. Le daily non devono mai contenere tag (`#tag`).
- **Header senza `:`**. Un `:` nel testo di un `###` rompe l'anchor del link
  `[[#header]]`. Riformula sempre (es. "su drive E" invece di "su E:").
- **Coerenza task ↔ sessione**: il testo in 🎯 Obiettivi e l'header `###` devono
  coincidere carattere per carattere, altrimenti il link non risolve.
- **Numeri esatti** nei dettagli tecnici: commit hash, conteggi, dimensioni file,
  porte. Non arrotondare, non inventare.
- **Un task = una sessione `###`**: non accorpare task diversi in un unico blocco.
- Se la daily del giorno **esiste già**, leggila e fai **append/patch** della nuova
  sessione, non sovrascrivere; aggiorna `data_modifica`.
- Più di 3 modifiche su una nota esistente → usa il tool `edit` (file-edit), non
  chiamate MCP una per una.

---

## Formattazione con Prettier

Dopo aver scritto o aggiornato la nota, formattala sempre con:

```bash
prettier --write "<nota_del_giorno>.md" --print-width 130 --prose-wrap always
```

- `--print-width 130` — larghezza massima di riga.
- `--prose-wrap always` — manda a capo la prosa in modo coerente.

> Attenzione: il wrapping di Prettier può fondere l'ultimo bullet di una lista con
> il separatore `---` che segue (diventa `- ***`). Dopo la formattazione, verifica
> che i separatori tra sezioni siano rimasti `---` puliti su riga propria.

---

## Strategia di verifica

Dopo aver creato/aggiornato la nota, controlla che:

- ogni task in 🎯 Obiettivi abbia un header `###` corrispondente (link risolto) e usi
  la forma aliasata `[[#header|alias]]` con l'ancora identica all'header;
- le issue in ✅ Issue chiuse risultino davvero in stato Done su Linear, e il blocco
  contenga solo ID, senza titoli copiati né magic words;
- ogni sessione `###` abbia i quattro `####` (Obiettivo, Cosa è stato fatto,
  Risultato, Dettagli tecnici);
- tra un blocco `###` e il successivo ci sia un `---` su riga propria;
- i dettagli tecnici (commit, path, numeri) combacino con quanto realmente fatto
  nella sessione;
- frontmatter e titolo rispettino i formati sopra;
- non ci siano tag e nessun header contenga `:`.

---

## Regole negative

Non fare queste operazioni:

- Non chiedere conferma per creare note `.md`, salvo indicazione esplicita dell'utente.
- Non spostare a mano nel vault file se non espressamente richiesto.
- Non fare chiamate MCP una per una quando ci sono più di 3 modifiche: usare file-edit.
- Non inserire Tag nella nota.

---

## Aprire un file nel vault

Metodo consigliato — tool MCP Obsidian (path relativo al vault, gestisce le cartelle con emoji):

```text
view(action: "open_in_obsidian", path: "<RELATIVE_FOLDER>/<DAILY_NOTE_NAME>.md")
```

> Evitare Advanced URI per i path con emoji (es. `🌅Daily`): l'encoding dell'emoji fallisce
> silenziosamente. Il tool MCP `view open_in_obsidian` usa path relativi e non ha il problema.
