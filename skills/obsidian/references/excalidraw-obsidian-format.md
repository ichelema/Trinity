# Excalidraw Obsidian Format

Reference operativa per Claude Code: creare, salvare e incorporare file Excalidraw nel Vault Obsidian partendo dal canvas live MCP.

Questo documento distingue in modo esplicito:

- canvas live MCP / Excalidraw server;
- file `.excalidraw` grezzo in compatibility mode;
- file Obsidian-native `.excalidraw.md`;
- nota Markdown `.md` che incorpora il disegno inline.

> `export_scene` **pubblica il disegno in Obsidian**: un hook lancia uno script Ruby che
> converte al formato nativo, **salva il `.excalidraw.md` nel vault** e rimuove il grezzo.
> Non serve sapere *come* converte né spostare/aprire/modificare file a mano.

---

## Regole operative essenziali

- **`export_scene` = pubblica nel vault**: l'hook converte e salva il `.excalidraw.md` direttamente nel vault (PostToolUse su `export_scene`), poi rimuove il grezzo. Tu non sposti nulla.
- **Formato target nel vault**: usare sempre `.excalidraw.md` Obsidian-native.
- **Embed Excalidraw**: usare sempre `![[<DRAWING_NAME>.excalidraw.md]]` con estensione completa.
- **Aprire nel vault** (opzionale): tool MCP `obsidian-semantic-notes-vault`, chiamata `view open_in_obsidian` (path relativo).
- **Creazione file nel vault**: note `.md` e disegni vanno creati automaticamente senza chiedere conferma, salvo indicazione esplicita dell'utente.
- **Nessun controllo pesante non richiesto**: non usare screenshot per verificare il proprio lavoro; usare `describe_scene` o fidarsi della response del tool quando sufficiente.
- **Nessuna lettura massiva del file esportato**: non leggere con `Read` il `.excalidraw` generato da `export_scene`, perché può superare i token limit.

---

## Convenzioni e placeholder

Usare questi placeholder in modo coerente. Non introdurre varianti locali non documentate.

| Placeholder | Significato | Uso |
|---|---|---|
| `{PROJECT_DIR}` | Directory progetto locale (Windows path) | `export_scene` / `import_scene` / `dump-scene` |
| `{OBSIDIAN_VAULT}` | Directory root del vault (Windows path) | dove l'hook pubblica; `Write`/`Edit` della nota |
| `<DRAWING_NAME>` | Nome base del disegno senza estensione | produce `.excalidraw` → `.excalidraw.md` |
| `<NOTE_NAME>` | Nome base della nota senza estensione | produce `.md` |
| `<RELATIVE_FOLDER>` | Cartella nel vault, relativa alla root | sottocartella di destinazione/embed |

### Regole path

- `export_scene` deve scrivere dentro `{PROJECT_DIR}` (il server MCP blocca path esterni); è l'hook che pubblica poi nel vault.
- I tool Claude Code `Write` / `Edit` (per la nota `.md`) usano path file-system del vault: `{OBSIDIAN_VAULT}`.
- Nei JSON/tool arguments, i backslash Windows vanno escapati come `\\`.

---

## Formato file `.excalidraw.md` Obsidian-native

Nel vault il disegno è un file `.excalidraw.md`: un Markdown con frontmatter `excalidraw-plugin: parsed`. **Lo genera automaticamente lo script di conversione** (vedi "Workflow"): non va creato né modificato a mano. Usarlo sempre come destinazione finale, mai `.excalidraw` puro.

### Frontmatter (opzioni utili)

| Chiave | Effetto |
|---|---|
| `excalidraw-plugin: parsed` | Marca il file come disegno Excalidraw. Obbligatorio. |
| `excalidraw-export-transparent: true` | Background trasparente in export. |
| `excalidraw-export-dark: true` | Forza tema scuro in export. |
| `excalidraw-export-pngscale: 2` | Scala export PNG. Valori tipici: `0.5`–`5`. |
| `excalidraw-default-mode: view` | Apre il disegno in view mode. |

---

## Embedding Excalidraw nelle note

Incorporare il disegno con il wikilink (sempre con estensione `.excalidraw.md` completa):

```markdown
![[<DRAWING_NAME>.excalidraw.md]]          # disegno intero
![[<DRAWING_NAME>.excalidraw.md|600x400]]  # ridimensionato (larghezza×altezza)
```

⚠️ Non usare `![[<DRAWING_NAME>.excalidraw]]` (senza `.md`): resta in compatibility mode e non si renderizza inline correttamente nelle note.

---

## Pattern comuni

### DataviewJS — embed disegno inline

```javascript
dv.paragraph(`![[<DRAWING_NAME>.excalidraw.md|400]]`);
```

---

## Workflow: canvas MCP → vault Obsidian

> ⚡ **`export_scene` pubblica nel vault.** L'hook `PostToolUse`
> `hooks/excalidraw/excalidraw-to-obsidian.rb` intercetta `export_scene`, converte al formato
> nativo, **salva il `.excalidraw.md` nel vault** e **rimuove il `.excalidraw` grezzo**. Niente
> Advanced URI, niente `%%` a mano, niente `mv`/`mkdir` manuali. Due soli passi:

### 1. Esporta (= pubblica)

Esportare dentro `{PROJECT_DIR}` (il server MCP blocca path esterni). Il **nome** e l'eventuale
**sottocartella** scelti qui determinano dove il disegno finisce nel vault:

```json
{ "filePath": "{PROJECT_DIR}\\<DRAWING_NAME>.excalidraw" }
```

| Dove esporti | Dove finisce nel vault |
|---|---|
| `{PROJECT_DIR}/<nome>.excalidraw` | `{OBSIDIAN_VAULT}/Excalidraw/<nome>.excalidraw.md` (default) |
| `{PROJECT_DIR}/<cartella>/<nome>.excalidraw` | `{OBSIDIAN_VAULT}/<cartella>/<nome>.excalidraw.md` |

Dopo l'export il `.excalidraw.md` è già nel vault, pronto; il grezzo è stato rimosso. Se un file
omonimo esisteva, ne viene fatto un backup `.bak`.

### 2. Crea la nota `.md` che incorpora il disegno

Con `Write`, senza chiedere conferma:

```markdown
# <NOTE_NAME>

![[<DRAWING_NAME>.excalidraw.md]]
```

Se nota e disegno sono in cartelle diverse, usare il path vault-relative:
`![[<RELATIVE_FOLDER>/<DRAWING_NAME>.excalidraw.md]]`.

### (Opzionale) Aprire il disegno in Obsidian

```text
view(action: "open_in_obsidian", path: "<RELATIVE_FOLDER>/<DRAWING_NAME>.excalidraw.md")
```

### Fallback (hook non attivo o vault non configurato)

Se l'hook non gira o `OBSIDIAN_VAULT` non è impostato, il `.excalidraw.md` resta accanto al grezzo
in `{PROJECT_DIR}` (e va spostato a mano). Per forzare la conversione:

```bash
ruby "${TRINITY_PLUGIN_DIR}/hooks/excalidraw/excalidraw-to-obsidian.rb" "{PROJECT_DIR}/<DRAWING_NAME>.excalidraw"
```

---

## Regola: niente screenshot non richiesti

- **NON** chiamare `get_canvas_screenshot` per verificare il proprio lavoro. Costa circa `28.000` token contro circa `1.000` di `describe_scene`.
- Per ogni verifica strutturale — posizioni, colori, dimensioni, label, connessioni — usare `describe_scene`.
- Per modifiche puntuali, ad esempio un singolo `update_element` o `batch_create_elements`, fidarsi della response del tool: conferma già le proprietà aggiornate. Non fare verifiche aggiuntive.
- Fare screenshot solo se l'utente lo richiede esplicitamente con richieste come `mostrami`, `fammi vedere`, `screenshot`, `check visivo`.
- Fare screenshot anche quando serve controllare dettagli puramente visivi che `describe_scene` non può catturare: rendering font, anomalie di stile, artefatti visivi.
- Se l'utente ha già fatto un check visivo iniziale, non ripetere screenshot durante piccole modifiche successive.

---

## Regola: file-edit per modifiche multiple

Quando devi fare più di 3 modifiche sul canvas, non usare chiamate MCP una per una.

Esempi di modifiche che contano:

- delete;
- update;
- riposizionamenti;
- cambi colore;
- modifica di `points` su `line` / `arrow`;
- modifiche batch a dimensioni, coordinate o stile.

### Workflow file-edit

1. Scarica la scena in locale con `dump-scene` — **NON** `export_scene`, che pubblicherebbe nel
   vault e rimuoverebbe il grezzo:

   ```bash
   ruby "${TRINITY_PLUGIN_DIR}/hooks/excalidraw/dump-scene.rb" "{PROJECT_DIR}/<DRAWING_NAME>.excalidraw"
   ```

   Produce un `.excalidraw` nel dialetto MCP (importabile da `import_scene`), senza toccare il vault.

2. Crea un backup `.bak` prima di modificare:

   ```bash
   cp "{PROJECT_DIR}/<DRAWING_NAME>.excalidraw" "{PROJECT_DIR}/<DRAWING_NAME>.excalidraw.bak"
   ```

3. Modifica direttamente il JSON con `Edit` / `Write`.

   Regole:

   - preferire un solo `Edit` con `replace_all` quando possibile;
   - preservare `id`, `groupIds`, `boundElements`, `startBinding`, `endBinding`, `containerId`, `seed`, `versionNonce` quando non sono oggetto della modifica;
   - non cambiare schema del file se l'obiettivo è solo una modifica geometrica o stilistica;
   - non comprimere il JSON.

4. Reimporta sul canvas live con replace:

   ```json
   {
     "filePath": "{PROJECT_DIR}\\<DRAWING_NAME>.excalidraw",
     "mode": "replace"
   }
   ```

Quando il disegno è pronto, pubblicalo con `export_scene` (vedi "Workflow").

### Quando NON usare file-edit

Restare su MCP diretto quando:

- è una prima creazione: `batch_create_elements` è già batch;
- ci sono solo 1-2 modifiche puntuali;
- l'utente vuole feedback live a ogni step;
- la modifica è più sicura tramite un singolo tool MCP specifico.

### Caso d'uso tipico

Usare file-edit per modificare i `points` interni di una `line`, ad esempio sorriso, baffi curvi o tratti organici. In questi casi `update_element` può non toccare i punti interni e costringerebbe a delete + recreate.

---

## Strategia di verifica

Usare la verifica più economica e affidabile per il tipo di modifica.

| Caso | Verifica corretta | Da evitare |
|---|---|---|
| Creazione batch elementi | Response di `batch_create_elements` | Screenshot automatico |
| Singolo update | Response di `update_element` | Screenshot automatico |
| Verifica strutturale | `describe_scene` | `get_canvas_screenshot` |
| Più di 3 modifiche | File-edit (`dump-scene` + `import_scene` replace) | Chiamate MCP una per una |
| Rendering visivo o font | Screenshot solo se necessario o richiesto | Lettura massiva JSON |
| Pubblicazione in Obsidian | `export_scene` (l'hook fa tutto) | `mv`/`Edit` del `%%` / `Read` del `.excalidraw` |

---

## Regole negative

Non fare queste operazioni:

- Non leggere il file `.excalidraw` generato da `export_scene` con `Read`.
- Non usare `get_canvas_screenshot` per verifiche strutturali o di routine.
- Non embeddare `![[<DRAWING_NAME>.excalidraw]]` nelle note.
- Non usare `.canvas` Obsidian come se fosse Excalidraw.
- Non chiedere conferma per creare note `.md` o disegni nel vault, salvo indicazione esplicita dell'utente.
- Non spostare a mano nel vault né aggiungere il `%%` o modificare il JSON dopo l'export: `export_scene` pubblica e converte da solo.
- Non usare `export_scene` per il file-edit (pubblicherebbe nel vault): usare `dump-scene`.
- Non fare chiamate MCP una per una quando ci sono più di 3 modifiche: usare file-edit.

---

## Aprire un file nel vault

Metodo consigliato — tool MCP Obsidian (path relativo al vault, gestisce le cartelle con emoji):

```text
view(action: "open_in_obsidian", path: "<RELATIVE_FOLDER>/<DRAWING_NAME>.excalidraw.md")
```

> ⚠️ Evitare Advanced URI per i path con emoji (es. `📂Files`): l'encoding dell'emoji fallisce
> silenziosamente. Il tool MCP `view open_in_obsidian` usa path relativi e non ha il problema.

---

## Troubleshooting

| Sintomo | Causa probabile | Fix |
|---|---|---|
| File si apre come Markdown invece del disegno | Manca `excalidraw-plugin: parsed` | Aggiungi frontmatter o usa `Open as Excalidraw`. |
| Disegno senza testi/frecce o reso male | Conversione non avvenuta (hook non scattato) | Vedi "Fallback": rilancia lo script di conversione. |
| `.excalidraw.md` non finisce nel vault | `OBSIDIAN_VAULT` non impostato | Il `.md` resta in `{PROJECT_DIR}`: imposta `OBSIDIAN_VAULT` o spostalo a mano. |
| Embed mostra immagine rotta | Path errato o file spostato | Controlla il wikilink e usa il path vault-relative corretto. |
| File corrotto o compresso | Compressione/corruzione JSON | Command palette: `Decompress current Excalidraw file`. |
| Troppi token durante verifica | Uso improprio di screenshot o `Read` | Usare `describe_scene` o response dei tool. |
| Modifiche al canvas perse dopo file-edit | Estratto con `export_scene` (ha pubblicato e rimosso il grezzo) | Usare `dump-scene` per estrarre, non `export_scene`. |

---

## Skill correlate

- Canvas live: la skill `excalidraw-skill`
- MCP Excalidraw: `yctimlin/mcp_excalidraw`
