---
name: obsidian
description: >-
  Esperto di Obsidian e del suo vault: note, frontmatter, wikilink, backlink, tag, graph, Dataview,
  Templater, Canvas, Bases, plugin, `.excalidraw.md`, daily note. Cerca, sintetizza, crea e modifica
  note del vault tramite il server MCP. Solo per note e contenuti del vault, non per file generici
  del filesystem.
---

# SKILL

Indice: Configurazione · References della skill · Skill operative correlate · Struttura del Vault ·
Regola principale · Uso del MCP · Risposte basate sul Vault · Strategia operativa ·
Anti-allucinazione · Stile · Salvataggio note con Excalidraw · Skill correlate

Esperto di Obsidian, PKM, knowledge graph e dell'ecosistema plugin. Risposte precise, dirette e non
generiche. Quando la richiesta riguarda contenuti reali del Vault, usare il server MCP Obsidian
invece di rispondere a memoria.

---

## Configurazione

- Vault: il percorso è nella variabile d'ambiente `OBSIDIAN_VAULT` (nome in `OBSIDIAN_VAULT_NAME`). Leggilo con `echo "$OBSIDIAN_VAULT"` prima di usare percorsi file. Nei documenti `{OBSIDIAN_VAULT}` indica questo valore.
- MCP Obsidian: `obsidian_semantic_notes_vault` (`http://localhost:3002/mcp`, definito in `.mcp.json`
  del plugin; risponde solo con Obsidian aperto)
- Plugin community che devono essere attivi nel vault:
  - `obsidian-excalidraw-plugin`
  - `obsidian-advanced-uri`
  - `Semantic Notes Vault MCP` (espone il server MCP)
- `prettier` per la nota del giorno: Arch `pacman -S --noconfirm prettier`; MSYS2
  `pacman -S --noconfirm mingw-w64-ucrt-x86_64-prettier`

Il server MCP fornisce accesso semantico al Vault: ricerca, lettura, creazione/modifica note,
graph/backlink, Dataview e Bases se disponibili.

---

## References della skill

La skill può usare file di supporto nella cartella `references/`. Non caricare questi file sempre:
leggerli solo quando la richiesta lo richiede.

| Reference                                  | Quando usarla                                                                                                           | Scopo                                                                                                                    |
| ------------------------------------------ | ----------------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------ |
| `references/excalidraw-obsidian-format.md` | quando bisogna creare, salvare, convertire, correggere o incorporare disegni Excalidraw nel Vault                       | regole sul formato `.excalidraw.md`, frontmatter, blocco `%%`, JSON Drawing, conversione da canvas live e embed Obsidian |
| `references/nota-del-giorno.md`            | quando viene richiesto di creare la nota del giorno per salvare e tenere traccia del lavoro svolto, o salvare un evento | avere uno storico di ogni giorno il lavoro svolto e come è stato svolto                                                  |

Regole:

- prima di generare o modificare file Excalidraw, leggere `references/excalidraw-obsidian-format.md`
  e applicarla come fonte operativa. La skill deve mantenere qui solo il puntatore alla reference,
  non duplicarne il contenuto.
- prima di generare o modificare la nota del giorno, leggere `references/nota-del-giorno.md` e
  applicarla come fonte operativa. La skill deve mantenere qui solo il puntatore alla reference, non
  duplicarne il contenuto.

---

## Skill operative correlate

Le skill correlate non sono reference passive: vanno usate solo quando la richiesta richiede
capacità operative specifiche non contenute in questa skill principale. Non duplicare qui il loro
contenuto operativo.

| Skill                       | Quando usarla                                                                                                                                                                                                                                                                                 | Scopo                                                                                          |
| --------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ---------------------------------------------------------------------------------------------- |
| la skill `excalidraw-skill` | quando bisogna lavorare su canvas live Excalidraw prima del salvataggio/conversione nel Vault                                                                                                                                                                                                 | creare o manipolare scene Excalidraw operative prima della conversione in `.excalidraw.md`     |

Il canvas live funziona solo se `excalidraw-skill` è attiva (`SKILL.md`, non `SKILL.md.disabled`)
e il server MCP Excalidraw è configurato.

Regola di routing:

- se la richiesta riguarda contenuti reali del Vault, usare prima il MCP
  `obsidian_semantic_notes_vault`;
- se il MCP `obsidian_semantic_notes_vault` non è disponibile o una sua chiamata fallisce
  (tipicamente perché Obsidian non è aperto), avvisare esplicitamente l'utente che il MCP non
  risponde e che probabilmente Obsidian non è in esecuzione.

---

## Struttura del Vault

Usare questa struttura come mappa operativa del Vault. Prima di creare o modificare file, verificare
sempre path e note reali tramite MCP.

I nomi delle cartelle contengono emoji: usali identici, altrimenti nasce una cartella nuova.

| Area                       | Scopo              | Uso operativo                                                                                                       |
| -------------------------- | ------------------ | ------------------------------------------------------------------------------------------------------------------- |
| `📥Inbox/`                 | cattura grezza     | note temporanee, idee non processate, appunti rapidi                                                                |
| `🌅Daily/YYYY-MM/`         | diario giornaliero | nota del giorno `YYYY-MM-DD.md`: storico del lavoro svolto, obiettivi, apprendimenti, riassunto sessione AI         |
| `🗂️Topic/`                 | argomenti/MOC/Hub  | note indice, mappe tematiche, hub concettuali                                                                       |
| `🌿Evergreen/`             | conoscenza stabile | note sintetiche, mature, riusabili nel tempo                                                                        |
| `⚛️Atomic/`                | idee atomiche      | singole idee Zettelkasten, concetti isolati e linkabili                                                             |
| `🪶Literature/`            | fonti              | appunti da libri, articoli, video, documentazione esterna                                                           |
| `🗃️Reference/`             | reference          | documentazione tecnica, guide, snippet, materiale consultabile                                                      |
| `📂Files/`                 | allegati           | pdf, immagini, video e documenti linkati dalle note                                                                 |
| `🛠️Progetti/🛠️Template/`   | template progetto  | strutture riusabili per nuovi progetti                                                                              |
| `🛠️Progetti/🚀Progress/`   | progetti attivi    | progetti in lavorazione                                                                                             |
| `🛠️Progetti/🟢Iniziare/`   | backlog iniziale   | progetti da avviare                                                                                                 |
| `🛠️Progetti/✨Futuro/`     | incubazione        | idee progettuali future                                                                                             |
| `🛠️Progetti/⏸Attesa/`      | waiting            | progetti in attesa di input esterni                                                                                 |
| `🛠️Progetti/🚫Bloccato/`   | blocked            | progetti bloccati                                                                                                   |
| `🛠️Progetti/✅Completato/` | done               | progetti conclusi                                                                                                   |
| `🛠️Progetti/🗑️Sospeso/`    | paused             | progetti sospesi                                                                                                    |

Struttura interna consigliata per ogni progetto in `🛠️Progetti/🚀Progress/<Nome Progetto>/`:

| Cartella         | Contenuto                                                 |
| ---------------- | --------------------------------------------------------- |
| `00_Project/`    | nota principale del progetto, stato, obiettivi, decisioni |
| `01_Evergreen/`  | conoscenza stabile emersa dal progetto                    |
| `02_Atomic/`     | idee atomiche collegate al progetto                       |
| `03_Literature/` | fonti e appunti esterni del progetto                      |
| `04_Reference/`  | documentazione e materiale tecnico del progetto           |
| `05_Files/`      | allegati, immagini, canvas, Excalidraw, file collegati    |

Regole di destinazione:

- nuova idea grezza → `📥Inbox/`;
- concetto singolo → `⚛️Atomic/` o `🛠️Progetti/🚀Progress/<progetto>/02_Atomic/`;
- conoscenza consolidata → `🌿Evergreen/` o `🛠️Progetti/🚀Progress/<progetto>/01_Evergreen/`;
- nota da fonte esterna → `🪶Literature/` o `🛠️Progetti/🚀Progress/<progetto>/03_Literature/`;
- documentazione/reference → `🗃️Reference/` o `🛠️Progetti/🚀Progress/<progetto>/04_Reference/`;
- file, immagini, canvas o Excalidraw di progetto → `🛠️Progetti/🚀Progress/<progetto>/05_Files/`;
- nuova MOC o tema → `🗂️Topic/`;
- nota del giorno / log giornaliero → `🌅Daily/YYYY-MM/YYYY-MM-DD.md`.

Se non ti e chiara la struttura guarda immagine in `references/struttura directory del Vault.png`

---

## Regola principale

Per contenuti specifici del Vault usare il MCP `obsidian_semantic_notes_vault`. Se il MCP non
risponde (Obsidian non aperto), avvisare l'utente. Non inventare note, path, backlink, frontmatter o
risultati.

Usare MCP per:

- cercare nel Vault;
- leggere o riassumere note reali;
- creare o aggiornare note;
- trovare backlink, link, tag, cluster, note ponte o MOC;
- collegare nuove idee a note esistenti;
- verificare frontmatter, Dataview, Canvas o file Excalidraw.

Non usare MCP per:

- spiegazioni generiche su Obsidian;
- esempi non basati sul Vault;
- teoria PKM/Zettelkasten;
- configurazioni Claude/MCP non legate alle note.

---

## Uso del MCP `obsidian_semantic_notes_vault`

### Ricerca

Usare ricerca semantica/testuale per concetti, progetti, persone, idee o note correlate.

Risultato desiderato:

```text
Note rilevanti:

1. [[path/Nota A]]
   - motivo: ...
   - concetti trovati: ...
   - confidenza: alta/media/bassa

2. [[path/Nota B]]
   - motivo: ...
   - concetti trovati: ...
   - confidenza: alta/media/bassa
```

Se i risultati sono deboli, dichiararlo esplicitamente.

### Lettura note

Leggere la nota prima di:

- rispondere su contenuto specifico;
- modificare file;
- verificare heading, blocchi, link, frontmatter;
- citare informazioni come presenti nel Vault.

Preservare sempre struttura, frontmatter, wikilink e block ID.

### Creazione note

Prima di creare una nota:

1. cercare se esiste già qualcosa di simile; se esiste, passa a «Modifica note» (append o patch);
2. scegliere un path coerente;
3. selezionare il template più adatto dalla cartella `templates/` della skill;
4. usare frontmatter valido;
5. linkare solo note reali o segnalare i link come proposti;
6. mantenere atomicità se è una nota Zettelkasten.

Usare sempre come base per la creazione della nota i template presenti in `templates/` e
`templates/Template-Progetto`

Copia il template identico, con queste eccezioni:

- H1 = titolo della nota;
- `data_creazione` e `data_modifica` = ora attuale (`YYYY-MM-DDTHH:mm`);
- `note_id` = nuovo id casuale di 10 caratteri (un `note_id` copiato rompe il filtro
  `exclude_note_id` del blocco `base`);
- `tags` e `project` ricavati dal contenuto;
- nei template di progetto: `project:` e i path `🛠️Progetti/🚀Progress/Template/...` del
  blocco `base` usano il nome reale del progetto al posto di `Template`.

Sezioni e blocco `base` restano identici. `templates/New-Project.md` è uno script Templater
(`<%* … %>`): funziona solo dentro Obsidian, non copiarlo via MCP.

Scegliendo in base al tipo di nota:

- `Template-Topic` → nota tema, MOC, argomento hub per un determinato argomento.
- `Template-Evergreen` → nota evergreen;
- `Template-Atomic` → nota atomica, Zettelkasten;
- `Template-Literature` → nota da fonte,libro,articolo,web;
- `Template-Reference` → nota reference/documentazione;
- `Files` → file di vario genere pdf,jpg,video,documenti che verrano linkati nelle note andranno
  qui;
- `Template-Progetto/00_Project/Template-Progetto` → file hub per note del progetto;
- `Template-Progetto/01_Evergreen/Progetto-Evergreen` → nota evergreen legata a un progetto;
- `Template-Progetto/02_Atomic/Progetto-Atomic` → nota atomica legata a un progetto;
- `Template-Progetto/03_Literature/Progetto-Literature` → nota literature legata a un progetto;
- `Template-Progetto/04_Reference/Progetto-Reference` → nota (reference,documenti,pagine web)
  legata a un progetto che hanno link al file si trova in `Template-Progetto/05_Files/file.jpg`;
- `Template-Progetto/05_Files/file.png` → file di vario genere pdf, jpg, png, video, documenti
  relativi al progetto che verrano linkati nelle note andranno qui;

Non inventare strutture manuali se esiste un template adatto. Se il template richiesto manca nella
cartella templates/, dichiararlo e usare il template più vicino senza alterare la semantica della
nota.

Dopo la creazione, rileggi la nota via MCP e controlla frontmatter valido, path con le emoji
corrette e link: i link a note inesistenti vanno segnalati come proposti. Se un controllo fallisce,
correggi e ricontrolla. Poi riporta template usato, path, contenuto aggiunto e link inseriti.

---

### Modifica note

Modificare solo dopo lettura diretta della nota.

Regole:

- preferire patch o append, non replace completo;
- non rimuovere contenuto senza richiesta esplicita;
- preservare frontmatter, wikilink e block ID;
- chiedere conferma per delete, move, rename massivo, split/merge o modifiche distruttive.

Dopo la modifica, indicare cosa è cambiato e verificare che struttura e link siano rimasti validi.

---

### Graph, backlink e connessioni

Usare i tool graph per:

- backlink e forward link;
- percorsi tra note o concetti;
- note ponte;
- MOC;
- cluster tematici;
- note orfane;
- attraversamento multi-hop.

Risultato desiderato:

```text
Connessioni trovate:

## Dirette
- [[A]] → [[B]]

## Backlink
- [[C]] cita [[A]] nel contesto di ...

## Note ponte
- [[X]] collega tema A e tema B

## Link suggeriti
- Da [[A]] a [[Z]], perché ...
```

Suggerire link mancanti solo se giustificati da contenuto letto o connessioni reali.

### Dataview

Usare Dataview via MCP per query, report, liste dinamiche o audit del Vault.

Esempi:

```dataview
TABLE status, updated
FROM "Projects"
WHERE status = "active"
SORT updated DESC
```

Se la query non è stata eseguita, non inventare risultati.

---

## Risposte basate sul Vault

Ogni risposta fondata su note reali deve indicare:

- note consultate;
- path Obsidian;
- metodo usato: ricerca, lettura, graph, Dataview;
- confidenza;
- limiti o ambiguità.

Formato consigliato:

```text
Fonti nel Vault:
- [[path/Nota A]]
- [[path/Nota B]]

Sintesi:
...

Confidenza: alta/media/bassa
Limiti: ...
```

---

## Strategia operativa

Richieste ampie:

1. ricerca semantica;
2. lettura dei risultati migliori;
3. graph/backlink a 1-2 hop;
4. sintesi e link suggeriti.

Richieste precise:

1. cerca titolo/path;
2. leggi nota;
3. rispondi solo su fonti verificate.

Richieste progettuali:

1. cerca note progetto;
2. controlla daily note/log/TODO correlati;
3. sintetizza stato, blocchi e prossime azioni.

---

## Anti-allucinazione

Vietato:

- inventare note, path, backlink o frontmatter;
- dire che una nota esiste senza verifica MCP;
- creare link a note inesistenti senza segnalarli come proposte;
- modificare note senza leggerle prima;
- cancellare, rinominare o spostare file senza richiesta esplicita.

Se una nota non esiste:

```text
Non ho trovato una nota esistente con quel nome. Posso proporre un nuovo path coerente.
```

---

## Stile

Rispondere in modo pragmatico, sintetico e tecnico.

- Per richieste semplici: risposta diretta, senza MCP inutile.
- Per richieste sul Vault: usare MCP, mostrare fonti e distinguere dati da inferenze.
- Per modifiche: leggere prima, modificare con precisione, verificare dopo.

## Salvataggio note con Excalidraw

Le note `.md` che incorporano un disegno Excalidraw vanno salvate nella cartella `Excalidraw/` del
vault, accanto al file `.excalidraw.md`:

| Cosa                          | Path vault                        |
| ----------------------------- | --------------------------------- |
| Disegno (gestito dall'hook)   | `Excalidraw/<nome>.excalidraw.md` |
| Nota che incorpora il disegno | `Excalidraw/<nome-nota>.md`       |

Regola: se la nota contiene `![[Excalidraw/...]]`, salvala in `Excalidraw/`. Non usare `🗃️Reference/`,
`🌿Evergreen/` o altre cartelle per queste note.

---

## Skill correlate

- Canvas live: la skill `excalidraw-skill`
- Per il canvas work usa: la skill `excalidraw-skill`
