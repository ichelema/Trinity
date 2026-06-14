# Excalidraw Obsidian Format

Reference operativa per Claude Code: creare, salvare, convertire, correggere e incorporare file Excalidraw nel Vault Obsidian partendo dal canvas live MCP.

Questo documento distingue in modo esplicito:

- canvas live MCP / Excalidraw server;
- file `.excalidraw` grezzo in compatibility mode;
- file Obsidian-native `.excalidraw.md`;
- nota Markdown `.md` che incorpora il disegno inline.

---

## Regole operative essenziali

- **Conversione automatica**: `export_scene` genera già il `.excalidraw.md` nativo via hook (plugin Trinity ≥ 0.5.7). Non convertire a mano né con Advanced URI.
- **Formato target nel vault**: usare sempre `.excalidraw.md` Obsidian-native.
- **Embed Excalidraw**: usare sempre `![[<DRAWING_NAME>.excalidraw.md]]` con estensione completa.
- **Aprire nel vault**: usare il tool MCP `view open_in_obsidian` (path relativo), non Advanced URI con cartelle emoji.
- **Canvas Obsidian**: il canvas nativo Obsidian usa file `.canvas` in JSON ed è distinto da Excalidraw.
- **File `.excalidraw` puro**: considerarlo solo temporaneo o compatibility mode, mai formato finale per embed inline.
- **Creazione file nel vault**: note `.md`, disegni `.excalidraw` e file convertiti `.excalidraw.md` vanno creati automaticamente senza chiedere conferma, salvo indicazione esplicita dell'utente.
- **Nessun controllo pesante non richiesto**: non usare screenshot per verificare il proprio lavoro; usare `describe_scene` o fidarsi della response del tool quando sufficiente.
- **Nessuna lettura massiva del file esportato**: non leggere con `Read` il `.excalidraw` generato da `export_scene`, perché può superare i token limit.

---

## Convenzioni e placeholder

Usare questi placeholder in modo coerente. Non introdurre varianti locali non documentate.

| Placeholder | Significato | Formato atteso | Uso corretto |
|---|---|---|---|
| `{PROJECT_DIR}` | Directory progetto locale | Windows path | Tool MCP `export_scene` / `import_scene` |
| `{PROJECT_DIR_MSYS}` | Directory progetto locale | MSYS/Git Bash path | Comandi Bash: `mv`, `cp`, `sed`, backup |
| `{OBSIDIAN_VAULT}` | Directory root del vault Obsidian | Windows path | Tool Claude Code `Write` / `Edit` |
| `{OBSIDIAN_VAULT_MSYS}` | Directory root del vault Obsidian | MSYS/Git Bash path | Comandi Bash verso il vault |
| `{OBSIDIAN_VAULT_NAME}` | Nome logico del vault Obsidian | Stringa Advanced URI | URI `obsidian://adv-uri?...` |
| `<DRAWING_NAME>` | Nome base del disegno senza estensione | Nome file sicuro | Produce `.excalidraw` e `.excalidraw.md` |
| `<NOTE_NAME>` | Nome base della nota senza estensione | Nome file sicuro | Produce `.md` |
| `<VAULT_RELATIVE_EXCALIDRAW_PATH>` | Path del `.excalidraw` relativo al vault | Path relativo Obsidian | Prima dell'URL encoding |
| `<VAULT_RELATIVE_EXCALIDRAW_PATH_ENCODED>` | Path relativo al vault URL-encoded | Advanced URI path | Parametro `filepath=` |

### Regole path non negoziabili

- `export_scene` deve scrivere dentro `{PROJECT_DIR}` perché il server MCP blocca path esterni.
- I comandi Bash devono usare solo path MSYS: `{PROJECT_DIR_MSYS}` e `{OBSIDIAN_VAULT_MSYS}`.
- I tool Claude Code `Write` / `Edit` devono usare path file-system del vault: `{OBSIDIAN_VAULT}`.
- Advanced URI non deve usare path assoluti. Deve usare solo `{OBSIDIAN_VAULT_NAME}` e un path relativo al vault URL-encoded.
- Non hardcodare il nome del vault dentro le URI: usare sempre `{OBSIDIAN_VAULT_NAME}`.
- Nei JSON/tool arguments, i backslash Windows vanno escapati come `\\`. Nella documentazione umana possono essere mostrati come `\`.

Esempio di path relativo encoded:

```text
<VAULT_RELATIVE_EXCALIDRAW_PATH> = Canvas/architettura.excalidraw
<VAULT_RELATIVE_EXCALIDRAW_PATH_ENCODED> = %2FCanvas%2Farchitettura.excalidraw
```

Se il file è nella root del vault:

```text
<VAULT_RELATIVE_EXCALIDRAW_PATH> = architettura.excalidraw
<VAULT_RELATIVE_EXCALIDRAW_PATH_ENCODED> = %2Farchitettura.excalidraw
```

---

## Formato file `.excalidraw.md` Obsidian-native

Il plugin `obsidian-excalidraw-plugin` salva i disegni come Markdown strutturato. Nel vault usare sempre questo formato, mai `.excalidraw` puro come destinazione finale.

````markdown
---
excalidraw-plugin: parsed
tags: [excalidraw]
---

# Excalidraw Data
## Text Elements
<!-- testo degli elementi, indicizzato dalla ricerca Obsidian -->

%%
## Drawing
```json
{
  "type": "excalidraw",
  "version": 2,
  "source": "https://excalidraw.com",
  "elements": [],
  "appState": {
    "gridSize": null,
    "viewBackgroundColor": "#ffffff"
  },
  "files": {}
}
```

%%
````

### Frontmatter chiave

| Chiave | Effetto |
|---|---|
| `excalidraw-plugin: parsed` | Marca il file come disegno Excalidraw. Obbligatorio. |
| `excalidraw-export-transparent: true` | Background trasparente in export. |
| `excalidraw-export-dark: true` | Forza tema scuro in export. |
| `excalidraw-export-pngscale: 2` | Scala export PNG. Valori tipici: `0.5`–`5`. |
| `excalidraw-default-mode: view` | Apre il disegno in view mode. |

---

## Regole critiche per il JSON Excalidraw

### Etichette come nodi separati

Ogni label deve essere un elemento `text` separato con `containerId` che punta allo shape padre. Non mettere `label` o `text` direttamente sullo shape.

```json
{
  "id": "r1",
  "type": "rectangle",
  "x": 100,
  "y": 100,
  "width": 200,
  "height": 60
},
{
  "id": "t1",
  "type": "text",
  "containerId": "r1",
  "text": "La mia etichetta",
  "x": 110,
  "y": 120
}
```

### Frecce e binding

Usare `startBinding` / `endBinding` con `elementId`, `focus`, `gap`.

```json
{
  "type": "arrow",
  "startBinding": {
    "elementId": "r1",
    "focus": 0,
    "gap": 4
  },
  "endBinding": {
    "elementId": "r2",
    "focus": 0,
    "gap": 4
  }
}
```

### Sezione `%%`

Il blocco `## Drawing` deve stare dentro `%%` per essere nascosto nella preview Markdown.

Devono esistere entrambi:

1. `%%` tra `## Text Elements` e `## Drawing`;
2. `%%` dopo il blocco JSON finale.

La conversione automatica di Obsidian omette sempre il `%%` dopo `## Text Elements`. Dopo ogni conversione va aggiunto proattivamente con `Edit`, senza verifiche preliminari.

### JSON non compresso

Il JSON deve restare leggibile. Evitare versioni base64/compressed salvo esplicita necessità di compatibilità.

---

## Conversione formato MCP → Obsidian

Quando si parte dal canvas live MCP, il file esportato non è direttamente il formato finale per Obsidian.

| Campo | Formato MCP / REST canvas | Formato Obsidian vault |
|---|---|---|
| Label su shape | `"text": "Label"` o `"label": {"text": "..."}` | Elemento `text` separato con `containerId` |
| Binding frecce | `startElementId` / `endElementId` | `startBinding.elementId` / `endBinding.elementId` |
| JSON | Eventualmente compresso o compatibility mode | JSON leggibile dentro `.excalidraw.md` |
| File finale | `.excalidraw` | `.excalidraw.md` |

---

## Embedding Excalidraw nelle note

Usare sempre il formato `.excalidraw.md`.

```markdown
![[<DRAWING_NAME>.excalidraw.md]]
![[<DRAWING_NAME>.excalidraw.md|600x400]]
![[<DRAWING_NAME>.excalidraw.md#group=<GROUP_NAME>]]
![[<DRAWING_NAME>.excalidraw.md|svg]]
![[<DRAWING_NAME>.excalidraw.md|png]]
```

Non usare:

```markdown
![[<DRAWING_NAME>.excalidraw]]
```

Motivo: `.excalidraw` resta in compatibility mode e non si renderizza inline correttamente nelle note.

---

## Link note ↔ disegni

- **Nota → disegno**: wikilink standard `[[<DRAWING_NAME>.excalidraw.md]]`.
- **Elemento disegno → nota**: proprietà `link` dell'elemento = `"[[<NOTE_NAME>]]"`; appare nei backlinks della nota.
- **Blocco Markdown come card dentro Excalidraw**: usare il comando palette `Insert markdown file from vault` dentro Excalidraw.

---

## Pattern comuni

### DataviewJS — embed disegno inline

```javascript
dv.paragraph(`![[<DRAWING_NAME>.excalidraw.md|400]]`);
```

---

## Workflow: canvas MCP → vault Obsidian

> ⚡ **Conversione automatica via hook.** Dal plugin Trinity v0.5.7, l'hook `PreToolUse`
> `hooks/excalidraw/excalidraw-to-obsidian.rb` intercetta ogni chiamata a `export_scene` e
> genera automaticamente, accanto al `.excalidraw`, anche il `.excalidraw.md` già in formato
> nativo Obsidian. **NON** serve più Advanced URI (`convert-excalidraw`), **NON** serve aggiungere
> il `%%` a mano, **NON** serve modificare il JSON. Il file `.excalidraw.md` è pronto all'uso.

Trasformazioni che l'hook applica automaticamente:

- `shape.label.text` → elemento `text` separato con `containerId` + `boundElements`;
- `arrow.start`/`arrow.end` → `arrow.startBinding`/`arrow.endBinding`;
- `arrow.label.text` → `arrow.text`;
- genera la sezione `## Text Elements` con gli `^id` allineati al JSON;
- aggiunge i `%%` attorno al blocco `## Drawing`.

### 1. Esporta nella directory di progetto locale

Il server MCP blocca path esterni: esportare sempre dentro `{PROJECT_DIR}`. L'hook scrive il
`.excalidraw.md` nella stessa directory dell'export.

Forma concettuale:

```bash
export_scene(filePath: "{PROJECT_DIR}\<DRAWING_NAME>.excalidraw")
```

Forma JSON/tool argument con backslash escapati:

```json
{
  "filePath": "{PROJECT_DIR}\\<DRAWING_NAME>.excalidraw"
}
```

Risultato in `{PROJECT_DIR}` dopo l'export (l'hook ha già convertito):

```text
<DRAWING_NAME>.excalidraw       (formato MCP grezzo, temporaneo)
<DRAWING_NAME>.excalidraw.md    (formato nativo Obsidian, pronto)
```

### 2. Sposta il `.excalidraw.md` nel vault

Spostare nel vault **solo** il `.excalidraw.md` (il `.excalidraw` grezzo è temporaneo, si può scartare).

```bash
mv "{PROJECT_DIR_MSYS}/<DRAWING_NAME>.excalidraw.md" "{OBSIDIAN_VAULT_MSYS}/<RELATIVE_FOLDER>/<DRAWING_NAME>.excalidraw.md"
```

Se la sottocartella non esiste, crearla prima con `mkdir -p`.

### 3. Apri il file in Obsidian con il MCP Obsidian (NON Advanced URI)

Usare il tool MCP Obsidian, che opera direttamente sul vault attivo:

```text
view(action: "open_in_obsidian", path: "<RELATIVE_FOLDER>/<DRAWING_NAME>.excalidraw.md")
```

> ⚠️ **NON usare Advanced URI per aprire file in cartelle con emoji nel nome** (es. `📂Files`).
> L'encoding dell'emoji (`%F0%9F%93%82`) fallisce silenziosamente e il file non si apre. Il
> tool MCP `view open_in_obsidian` usa path relativi al vault e non ha questo problema.

### 4. Crea la nota `.md` che incorpora il disegno

Usare il tool `Write`, senza chiedere conferma.

```text
{OBSIDIAN_VAULT}\<RELATIVE_FOLDER>\<NOTE_NAME>.md
```

Contenuto minimo:

```markdown
# <NOTE_NAME>

![[<DRAWING_NAME>.excalidraw.md]]
```

Se nota e disegno sono in cartelle diverse, usare un wikilink valido rispetto al vault:

```markdown
# <NOTE_NAME>

![[<RELATIVE_FOLDER>/<DRAWING_NAME>.excalidraw.md]]
```

### Fallback manuale (solo se l'hook non è attivo)

Se per qualche motivo l'hook non gira (plugin non ricaricato, versione < 0.5.7), il file
`.excalidraw.md` non viene generato. In quel caso, convertire manualmente lanciando lo script:

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

1. Esporta la scena in JSON `.excalidraw` dentro `{PROJECT_DIR}`:

   ```bash
   export_scene(filePath: "{PROJECT_DIR}\<DRAWING_NAME>.excalidraw")
   ```

   Nei tool arguments JSON:

   ```json
   {
     "filePath": "{PROJECT_DIR}\\<DRAWING_NAME>.excalidraw"
   }
   ```

2. Crea un backup `.bak` prima di modificare:

   ```bash
   cp "{PROJECT_DIR_MSYS}/<DRAWING_NAME>.excalidraw" "{PROJECT_DIR_MSYS}/<DRAWING_NAME>.excalidraw.bak"
   ```

3. Modifica direttamente il JSON con `Edit` / `Write`.

   Regole:

   - preferire un solo `Edit` con `replace_all` quando possibile;
   - preservare `id`, `groupIds`, `boundElements`, `startBinding`, `endBinding`, `containerId`, `seed`, `versionNonce` quando non sono oggetto della modifica;
   - non cambiare schema del file se l'obiettivo è solo una modifica geometrica o stilistica;
   - non comprimere il JSON.

4. Reimporta sul canvas live con replace:

   ```bash
   import_scene(filePath: "{PROJECT_DIR}\<DRAWING_NAME>.excalidraw", mode: "replace")
   ```

   Nei tool arguments JSON:

   ```json
   {
     "filePath": "{PROJECT_DIR}\\<DRAWING_NAME>.excalidraw",
     "mode": "replace"
   }
   ```

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
| Più di 3 modifiche | File-edit + `import_scene(mode: "replace")` | Chiamate MCP una per una |
| Rendering visivo o font | Screenshot solo se necessario o richiesto | Lettura massiva JSON |
| Conversione Obsidian | `Edit` diretto del `%%` | `Read` del `.excalidraw` esportato |

---

## Regole negative

Non fare queste operazioni:

- Non leggere il file `.excalidraw` generato da `export_scene` con `Read`.
- Non usare `get_canvas_screenshot` per verifiche strutturali o di routine.
- Non embeddare `![[<DRAWING_NAME>.excalidraw]]` nelle note.
- Non usare `.canvas` Obsidian come se fosse Excalidraw.
- Non usare path assoluti dentro Advanced URI.
- Non usare `{OBSIDIAN_VAULT_MSYS}` dentro `obsidian://adv-uri`.
- Non hardcodare `{OBSIDIAN_VAULT_NAME}` con un nome vault specifico.
- Non chiedere conferma per creare note `.md` o disegni nel vault, salvo indicazione esplicita dell'utente.
- Non fare controlli aggiuntivi dopo hook di formattazione se il workflow ha già applicato l'`Edit` richiesto.
- Non fare chiamate MCP una per una quando ci sono più di 3 modifiche: usare file-edit.

---

## Aprire un file nel vault

Metodo consigliato — tool MCP Obsidian (path relativo al vault, gestisce le cartelle con emoji):

```text
view(action: "open_in_obsidian", path: "<RELATIVE_FOLDER>/<DRAWING_NAME>.excalidraw.md")
```

> ⚠️ **Advanced URI sconsigliato per path con emoji.** `obsidian://adv-uri?...&filepath=...` fallisce
> silenziosamente quando il path contiene cartelle con emoji nel nome (es. `📂Files` →
> `%F0%9F%93%82Files`). Preferire sempre il tool MCP `view open_in_obsidian`.

La conversione `convert-excalidraw` via Advanced URI **non serve più**: l'hook genera già il
`.excalidraw.md` nativo all'export (vedi "Workflow: canvas MCP → vault Obsidian").

---

## Troubleshooting

| Sintomo | Causa probabile | Fix |
|---|---|---|
| File si apre come Markdown invece del disegno | Manca `excalidraw-plugin: parsed` | Aggiungi frontmatter o usa `Open as Excalidraw`. |
| Etichette dei box non visibili nel disegno | `.excalidraw` MCP con `label` non convertito | L'hook converte all'export; se manca, lanciare `ruby ${TRINITY_PLUGIN_DIR}/hooks/excalidraw/excalidraw-to-obsidian.rb <file>.excalidraw`. |
| Testi Markdown finiscono dentro il disegno | `^id` di `## Text Elements` non allineati al JSON | Rigenerare con l'hook/script di conversione (allinea gli ID automaticamente). |
| Embed mostra immagine rotta | Path errato o file spostato | Controlla il wikilink e usa il path vault-relative corretto. |
| File corrotto o compresso | Compressione/corruzione JSON | Command palette: `Decompress current Excalidraw file`. |
| Troppi token durante verifica | Uso improprio di screenshot o `Read` | Usare `describe_scene` o response dei tool. |
| Tante modifiche lente o fragili | Chiamate MCP una per una | Usare file-edit: export, backup, edit JSON, import replace. |
| Advanced URI non apre il file (cartella con emoji) | Encoding emoji nel path fallisce | Usare il tool MCP `view open_in_obsidian` con path relativo. |

---

## Skill correlate

- Canvas live: la skill `excalidraw-skill`
- MCP Excalidraw: `yctimlin/mcp_excalidraw`
