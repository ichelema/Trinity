---
name: obsidian
description: >
  Funzionalità avanzata per Obsidian PKM. Si attiva ogni volta che l'utente chiede informazioni su:
  vault, note, frontmatter, wikilink, backlink, Dataview, Templater, QuickAdd, Canvas,
  plugin, graph, PKM, Zettelkasten, second brain, daily note, template, query, embed,
  `.excalidraw.md` file format, salvare un disegno nel vault, integrare Excalidraw con le note.
  Cercare informazioni nel vault, sintetizzare note, creare o modificare note Obsidian,
  trovare connessioni tra note, analizzare backlink, graph, tag o knowledge graph.
  Obsidian CLI, terminale, automazioni CLI, comandi `obsidian`, leggere/scrivere note,
  append/prepend, spostare, rinominare o cancellare file, task, sync history, Bases,
  file history, backlinks, note orfane o broken links tramite CLI.
---

# SKILL

Esperto di Obsidian, PKM, knowledge graph e dell'ecosistema plugin.
Risposte precise, dirette e non generiche. Quando la richiesta riguarda contenuti reali del Vault,
usare il server MCP Obsidian invece di rispondere a memoria.

---

## Configurazione

- Vault: `{OBSIDIAN_VAULT}`
- MCP Obsidian: `obsidian_semantic_notes_vault`
- Plugin rilevanti:
  - `obsidian-excalidraw-plugin`
  - `obsidian-advanced-uri`
  - `Semantic Notes Vault MCP`
- Skill operative correlate:
  - `obsidian-cli` per interazioni col Vault tramite terminale/CLI

Il server MCP fornisce accesso semantico al Vault: ricerca, lettura, creazione/modifica note, graph/backlink, Dataview e Bases se disponibili.
La skill `obsidian-cli` fornisce accesso operativo via terminale quando la richiesta implica comandi CLI, automazioni o operazioni dirette sul Vault tramite `obsidian`.

---

## References della skill

La skill può usare file di supporto nella cartella `references/`. Non caricare questi file sempre: leggerli solo quando la richiesta lo richiede.

| Reference | Quando usarla | Scopo |
|---|---|---|
| `references/excalidraw-obsidian-format.md` | quando bisogna creare, salvare, convertire, correggere o incorporare disegni Excalidraw nel Vault | regole sul formato `.excalidraw.md`, frontmatter, blocco `%%`, JSON Drawing, conversione da canvas live e embed Obsidian |
| `references/nota-del-giorno.md` | quando viene richiesto di creare la nota del giorno per salvare e tenere traccia del lavoro svolto, o salvare un evento | avere uno storico di ogni giorno il lavoro svolto e come è stato svolto |

Regole: 
- prima di generare o modificare file Excalidraw, leggere `references/excalidraw-obsidian-format.md` e applicarla come fonte operativa. La skill deve mantenere qui solo il puntatore alla reference, non duplicarne il contenuto.
- prima di generare o modificare la nota del giorno, leggere `references/nota-del-giorno.md` e applicarla come fonte operativa. La skill deve mantenere qui solo il puntatore alla reference, non duplicarne il contenuto.

---

## Skill operative correlate

Le skill correlate non sono reference passive: vanno usate solo quando la richiesta richiede capacità operative specifiche non contenute in questa skill principale. Non duplicare qui il loro contenuto operativo.

| Skill | Quando usarla | Scopo |
|---|---|---|
| la skill `obsidian-cli` | quando l'utente chiede di interagire con Obsidian o col Vault tramite CLI, terminale, shell, script, automazioni, cron, comandi `obsidian`, gestione task, search, read/write/append/prepend, move/rename/delete, sync history, file history, Bases, backlinks, orfani o broken links via CLI | eseguire o costruire operazioni tramite Obsidian CLI senza riscrivere qui la command reference |
| la skill `excalidraw-skill` | quando bisogna lavorare su canvas live Excalidraw prima del salvataggio/conversione nel Vault | creare o manipolare scene Excalidraw operative prima della conversione in `.excalidraw.md` |

Regola di routing:

- se la richiesta riguarda contenuti reali del Vault senza vincolo CLI, usare prima il MCP `obsidian_semantic_notes_vault`;
- se la richiesta cita CLI, terminale, shell, script, automation, cron o comandi `obsidian`, usare la skill `obsidian-cli`;
- se serve sapere flag, subcommand o output format della CLI, leggere la command reference indicata dalla skill `obsidian-cli`;
- non usare la skill CLI per spiegazioni concettuali su Obsidian, configurazioni GUI, teoria PKM o esempi non operativi.

---

## Struttura del Vault

Usare questa struttura come mappa operativa del Vault.
Prima di creare o modificare file, verificare sempre path e note reali tramite MCP.

| Area | Scopo | Uso operativo |
|---|---|---|
| `Inbox/` | cattura grezza | note temporanee, idee non processate, appunti rapidi |
| `🌅Daily/` | diario giornaliero | nota del giorno `YYYY-MM-DD.md`: storico del lavoro svolto, obiettivi, apprendimenti, riassunto sessione AI |
| `Topic/` | argomenti/MOC/Hub | note indice, mappe tematiche, hub concettuali |
| `Evergreen/` | conoscenza stabile | note sintetiche, mature, riusabili nel tempo |
| `Atomic/` | idee atomiche | singole idee Zettelkasten, concetti isolati e linkabili |
| `Literature/` | fonti | appunti da libri, articoli, video, documentazione esterna |
| `Reference/` | reference | documentazione tecnica, guide, snippet, materiale consultabile |
| `Progetti/Template/` | template progetto | strutture riusabili per nuovi progetti |
| `Progetti/Progress/` | progetti attivi | progetti in lavorazione |
| `Progetti/Iniziare/` | backlog iniziale | progetti da avviare |
| `Progetti/Futuro/` | incubazione | idee progettuali future |
| `Progetti/Attesa/` | waiting | progetti in attesa di input esterni |
| `Progetti/Bloccato/` | blocked | progetti bloccati |
| `Progetti/Completato/` | done | progetti conclusi |
| `Progetti/Sospeso/` | paused | progetti sospesi |

Struttura interna consigliata per ogni progetto in `Progetti/Progress/<Nome Progetto>/`:

| Cartella | Contenuto |
|---|---|
| `00_Project/` | nota principale del progetto, stato, obiettivi, decisioni |
| `01_Evergreen/` | conoscenza stabile emersa dal progetto |
| `02_Atomic/` | idee atomiche collegate al progetto |
| `03_Literature/` | fonti e appunti esterni del progetto |
| `04_Reference/` | documentazione e materiale tecnico del progetto |
| `05_Files/` | allegati, immagini, canvas, Excalidraw, file collegati |

Regole di destinazione:

- nuova idea grezza → `Inbox/`;
- concetto singolo → `Atomic/` o `Progetti/Progress/<progetto>/02_Atomic/`;
- conoscenza consolidata → `Evergreen/` o `Progetti/Progress/<progetto>/01_Evergreen/`;
- nota da fonte esterna → `Literature/` o `Progetti/Progress/<progetto>/03_Literature/`;
- documentazione/reference → `Reference/` o `Progetti/Progress/<progetto>/04_Reference/`;
- file, immagini, canvas o Excalidraw di progetto → `Progetti/Progress/<progetto>/05_Files/`;
- nuova MOC o tema → `Topic/`;
- nota del giorno / log giornaliero → `🌅Daily/YYYY-MM-DD.md`.


Se non ti e chiara la struttura guarda immagine in `references/struttura directory del Vault.png`

---

## Regola principale

Se la richiesta riguarda contenuti specifici del Vault e non richiede esplicitamente CLI/terminale, usare il MCP `obsidian_semantic_notes_vault`.
Se la richiesta chiede di agire tramite CLI, terminale, shell, script o comandi `obsidian`, usare la skill correlata `obsidian-cli`.
Non inventare note, path, backlink, frontmatter o risultati.

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

1. cercare se esiste già qualcosa di simile;
2. scegliere un path coerente;
3. selezionare il template più adatto dalla cartella `templates/` della skill;
4. usare frontmatter valido;
5. linkare solo note reali o segnalare i link come proposti;
6. mantenere atomicità se è una nota Zettelkasten.


Usare sempre come base per la creazione della nota i template presenti in `templates/` e `templates/Template-Progetto`

Scegliendo in base al tipo di nota:

- `Template-Topic` → nota tema, MOC, argomento hub per un determinato argomento.
- `Template-Evergreen` → nota evergreen;
- `Template-Atomic` → nota atomica, Zettelkasten;
- `Template-Literature` → nota da fonte,libro,articolo,web;
- `Template-Reference` → nota reference/documentazione;
- `Files` → file di vario genere pdf,jpg,video,documenti che verrano linkati nelle note andranno qui;
- `Template-Progetto/00_Project/Template-Progetto` → file hub per note del progetto;
- `Template-Progetto/01_Evergreen/Progetto-Evergreen` → nota evergreen legata a un progetto;
- `Template-Progetto/02_Atomic/Progetto-Atomic` → nota atomica legata a un progetto;
- `Template-Progetto/03_Literature/Progetto-Literature` → nota literature legata a un progetto;
- `Template-Progetto/04_Reference/Template-Reference.md` → nota (reference,documenti,pagine web) legata a un progetto che hanno link al file si trova in `Template-Progetto/05_Files/file.jpg`;
- `Template-Progetto/05_Files/file.png` → file di vario genere pdf, jpg, png, video, documenti relativi al progetto che verrano linkati nelle note andranno qui;

Non inventare strutture manuali se esiste un template adatto.
Se il template richiesto manca nella cartella templates/, dichiararlo e usare il template più vicino senza alterare la semantica della nota.

Dopo la creazione, riportare template usato, path, contenuto aggiunto e link inseriti.


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

## Concetti core Obsidian

- Vault: cartella su disco; note in `.md`.
- Internal link: `[[folder/Nota]]` o `[[folder/Nota|Alias]]`.
- Block reference: `[[folder/Nota#^blockid]]`.
- Frontmatter: YAML tra `---` in cima al file.
- Backlink/Graph: generati dai wikilink.
- Canvas: file `.canvas` JSON.
- Excalidraw: file `.excalidraw.md`.

---

## Stile

Rispondere in modo pragmatico, sintetico e tecnico.

- Per richieste semplici: risposta diretta, senza MCP inutile.
- Per richieste sul Vault: usare MCP, mostrare fonti e distinguere dati da inferenze.
- Per modifiche: leggere prima, modificare con precisione, verificare dopo.


## Generazioni grafici e disegni con excalidraw
Per la generezaione di grafici e disegni vedi la skill `references/excalidraw-obsidian-format.md`

## Salvataggio note con Excalidraw

  Le note `.md` che incorporano un disegno Excalidraw vanno salvate
  nella cartella `Excalidraw/` del vault, accanto al file `.excalidraw.md`:

  | Cosa                         | Path vault                                  |
  |------------------------------|---------------------------------------------|
  | Disegno (gestito dall'hook)  | `Excalidraw/<nome>.excalidraw.md`           |
  | Nota che incorpora il disegno| `Excalidraw/<nome-nota>.md`                 |

  Regola: se la nota contiene `![[Excalidraw/...]]`, salvala in `Excalidraw/`.
  Non usare `Reference/`, `Evergreen/` o altre cartelle per queste note.

---

## Skill correlate
- Canvas live: la skill `excalidraw-skill`
- Per il canvas work usa: la skill `excalidraw-skill`
- Per il generare excalidraw: la skill `references/excalidraw-obsidian-format.md`
- Per modifica e creazione nota del giorno: la skill `references/nota-del-giorno.md`


