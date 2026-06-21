---
name: excalidraw-skill
description: Programmatic canvas toolkit for creating, editing, and refining Excalidraw diagrams via MCP tools with real-time canvas sync. Use when an agent needs to (1) draw or lay out diagrams on a live canvas, (2) iteratively refine diagrams using `describe_scene` (default — textual structured analysis, ~1k tokens) to inspect its own work, falling back to `get_canvas_screenshot` only when explicitly requested, (3) export/import .excalidraw files or PNG/SVG images, (4) save/restore canvas snapshots, (5) convert Mermaid to Excalidraw, or (6) perform element-level CRUD, alignment, distribution, grouping, duplication, and locking. Requires a running canvas server (EXPRESS_SERVER_URL, default http://127.0.0.1:3000).
---

# Excalidraw Skill

## Step -1: Verifica che il server canvas sia in esecuzione

Prima di qualsiasi operazione sul canvas, controlla se il server è attivo:

```bash
curl -s --connect-timeout 1 http://localhost:3000 > /dev/null 2>&1 && echo "running" || echo "stopped"
```

Se il risultato è `stopped`, avvialo con:

```bash
mise -C "${TRINITY_PLUGIN_DIR}" run start-excalidraw
```

Attendi il bind (max 20 secondi):

```bash
curl -s --retry 10 --retry-connrefused --retry-delay 1 --connect-timeout 2 \
  http://127.0.0.1:3000/api/elements -o /dev/null -w "HTTP %{http_code}\n"
```

Atteso: `HTTP 200`.

> ⚠️ **NON usare `npm run canvas`.** Quel comando esegue prima `build:server` (`npx tsc`), e su questa macchina il **node di MSYS2** (`/ucrt64/bin/node`, attualmente 24.14.1) fa **crashare `tsc`** con `std::bad_weak_ptr` (exit 127) → la build fallisce e per via del `&&` il server non viene mai lanciato. Il problema è **solo** lo step di build: `node dist/server.js` gira benissimo, e `dist/` è già compilato.

**Rebuild dei sorgenti `.ts`** (solo se hai modificato `src/`, raramente) — usa il **node di mise** (Windows nativo), che compila `tsc` senza crashare; mai `npx tsc` con il node MSYS2:

```bash
"C:/msys64/home/$USERNAME/.local/share/mise/installs/node/24.16.0/node.exe" \
  "$REPO/node_modules/typescript/bin/tsc" -p "$REPO/tsconfig.json"
```

---

## Step 0: Determine Connection Mode

Two modes are available. Try MCP first — it has more capabilities.

**MCP mode** (preferred): If `excalidraw/batch_create_elements` and other `excalidraw/*` tools appear in your tool list, use them directly. MCP tools handle label and arrow binding format automatically.

**REST API mode** (fallback): If MCP tools aren't available, use HTTP endpoints at `http://127.0.0.1:3000`. See the cheatsheet for REST payloads. Note the format differences in the table below — REST and MCP accept slightly different field names.

**Neither works?** Tell the user the canvas server isn't running and they need to start it (`PORT=3000 npm run canvas` from the mcp_excalidraw repo) and open `http://127.0.0.1:3000`.

### MCP vs REST API Quick Reference

| Operation        | MCP Tool                   | REST API Equivalent                                       |
| ---------------- | -------------------------- | --------------------------------------------------------- |
| Create elements  | `batch_create_elements`    | `POST /api/elements/batch`                                |
| Get all elements | `query_elements`           | `GET /api/elements`                                       |
| Get one element  | `get_element`              | `GET /api/elements/:id`                                   |
| Update element   | `update_element`           | `PUT /api/elements/:id`                                   |
| Delete element   | `delete_element`           | `DELETE /api/elements/:id`                                |
| Clear canvas     | `clear_canvas`             | `DELETE /api/elements/clear`                              |
| Describe scene   | `describe_scene`           | `GET /api/elements` (parse manually)                      |
| Export scene     | `export_scene`             | `GET /api/elements` (save to file)                        |
| Import scene     | `import_scene`             | `POST /api/elements/sync`                                 |
| Snapshot         | `snapshot_scene`           | `POST /api/snapshots`                                     |
| Restore snapshot | `restore_snapshot`         | `GET /api/snapshots/:name` then `POST /api/elements/sync` |
| Screenshot       | `get_canvas_screenshot`    | `POST /api/export/image` (needs browser)                  |
| Viewport         | `set_viewport`             | `POST /api/viewport` (needs browser)                      |
| Export image     | `export_to_image`          | `POST /api/export/image` (needs browser)                  |
| Export URL       | `export_to_excalidraw_url` | Only via MCP                                              |

### Format Differences Between Modes (Critical)

1. **Labels**: MCP accepts `"text": "My Label"` on shapes (auto-converts). REST requires `"label": {"text": "My Label"}`.
2. **Arrow binding**: MCP accepts `startElementId`/`endElementId`. REST requires `"start": {"id": "..."}` / `"end": {"id": "..."}`.
3. **fontFamily**: Must be a string (e.g. `"1"`) or omit entirely. Never pass a number.
4. **Updating labels via REST**: Re-include `"label"` in the PUT body to ensure it renders correctly after updates.

---

## Coordinate System

The canvas uses a 2D coordinate grid: **(0, 0) is the origin**, **x increases rightward**, **y increases downward**. Plan your layout before writing any JSON.

**General spacing guidelines:**

- Vertical spacing between tiers: 80–120px (enough that arrows don't crowd labels)
- Horizontal spacing between siblings: 40–60px minimum
- Shape width: `max(160, labelCharCount * 9)` to prevent text truncation
- Shape height: 60px single-line, 80px two-line labels
- Background/zone padding: 50px on all sides around contained elements

---

## Layout Anti-Patterns (Critical for Complex Diagrams)

These are the most common mistakes that produce unreadable diagrams. Avoid all of them.

### 1. Do NOT use `label.text` (or `text`) on large background zone rectangles

When you put a label on a background rectangle, Excalidraw creates a bound text element centered in the middle of that shape — right where your service boxes will be placed. The text overlaps everything inside the zone and cannot be repositioned.

**Wrong:**

```json
{
  "id": "vpc-zone",
  "type": "rectangle",
  "x": 50,
  "y": 50,
  "width": 800,
  "height": 400,
  "text": "VPC (10.0.0.0/16)"
}
```

**Right — use a free-standing text element anchored at the top of the zone:**

```json
{"id": "vpc-zone", "type": "rectangle", "x": 50, "y": 50, "width": 800, "height": 400, "backgroundColor": "#e3f2fd"},
{"id": "vpc-label", "type": "text", "x": 70, "y": 60, "width": 300, "height": 30, "text": "VPC (10.0.0.0/16)", "fontSize": 18, "fontWeight": "bold"}
```

The free-standing text element sits at the top corner of the zone and doesn't interfere with elements placed inside.

### 2. Avoid cross-zone arrows in complex diagrams

An arrow from an element in one layout zone to an element in a distant zone will draw a long diagonal line crossing through everything in between. In a multi-zone infra diagram this produces an unreadable tangle of spaghetti.

**Design rule:** Keep arrows within the same zone or tier. To show cross-zone relationships, use annotation text or separate the zones so their edges are adjacent (no elements between them), and route the arrow along the edge.

If you must connect across zones, use an elbowed arrow that travels along the perimeter — never through the middle of another zone.

### 3. Use arrow labels sparingly

Arrow labels are placed at the midpoint of the arrow. On short arrows, they overlap the shapes at both ends. On crowded diagrams, they collide with nearby elements.

- Only add an arrow label when the relationship name is genuinely essential (e.g., protocol, port number, data direction).
- If you're adding a label to every arrow, reconsider — it usually adds visual noise, not clarity.
- Keep arrow labels to ≤ 12 characters. Prefer omitting them entirely on dense diagrams.

---

## Scene Analysis Strategy — Use `describe_scene` by Default

**Regola fondamentale:** usa sempre `describe_scene` (~1k token, restituisce ID, tipo, posizione, dimensioni, colori, label, connessioni). Ricorri a `get_canvas_screenshot` (~28k token) **solo** se l'utente lo chiede esplicitamente o per dettagli puramente visivi (font rendering, anomalie di stile). Avvisa del costo prima di lanciarlo.

---

## Quality Checklist

After each `batch_create_elements`, call `describe_scene` and verify:

1. **Text truncation** — `describe_scene` riporta `width`/`height` di ogni shape e la lunghezza della label. Se `labelCharCount * 9 > width`, il testo sarà troncato → aumenta `width`/`height`.
2. **Overlap** — confronta bounding box (x, y, width, height) degli elementi: se due shape non-zone si sovrappongono, riposiziona. Le zone di sfondo devono contenere i figli con padding ≥ 50px.
3. **Arrow crossing** — controlla i punti di start/end delle frecce e i bounding box degli elementi intermedi: se la retta start→end passa dentro un rettangolo non collegato, instrada con waypoint curvi o elbowed (vedi Arrow Routing).
4. **Arrow-label overlap** — calcola il midpoint della freccia (media tra start ed end) e controlla che non cada dentro il bounding box di una shape. Se collide, accorcia la label o riposiziona.
5. **Spacing** — almeno 40px di gap tra gli elementi (verificabile dai bounding box). Layout troppo stretti sono illeggibili.
6. **Readability** — `fontSize` ≥ 16 per testo, ≥ 20 per titoli. `describe_scene` riporta il fontSize per gli elementi text.
7. **Zone label placement** — se hai usato `text`/`label.text` su un rettangolo di zone, `describe_scene` mostrerà un elemento `text` con `containerId` puntato alla zone: la label è centrata nella zone e si sovrappone ai contenuti. Fix: cancella il bound text e aggiungi un elemento text free-standing in alto.

If you find any issue: **stop, fix it, re-run `describe_scene`, then continue.** Say "I see [issue], fixing it" rather than glossing over problems. Only proceed once all checks pass.

---

## Workflow: Drawing a New Diagram

Use `create_from_mermaid` for standard flowchart/sequence/ER diagrams. Use `batch_create_elements` for precise layout control or custom architecture.

### MCP Mode

1. Call `read_diagram_guide` for design best practices (colors, fonts, anti-patterns).
2. Plan your coordinate grid on paper/in comments — map out tiers and x-positions before writing JSON.
3. Optional: `clear_canvas` to start fresh.
4. Use `batch_create_elements` — create shapes and arrows in one call. Custom `id` fields (e.g. `"id": "auth-svc"`) make later updates easy.
5. Set shape widths using `max(160, labelLength * 9)`. Use `text` field for labels.
6. Bind arrows with `startElementId` / `endElementId` — they auto-route to element edges.
7. `set_viewport` with `scrollToContent: true` to auto-fit.
8. Run `describe_scene` → execute the Quality Checklist on the structured output → fix issues before next iteration. Don't take a screenshot unless the user explicitly asks for one.

**MCP element + arrow example:**

```json
{
  "elements": [
    {
      "id": "lb",
      "type": "rectangle",
      "x": 300,
      "y": 50,
      "width": 180,
      "height": 60,
      "text": "Load Balancer"
    },
    {
      "id": "db",
      "type": "rectangle",
      "x": 300,
      "y": 250,
      "width": 180,
      "height": 60,
      "text": "PostgreSQL"
    },
    {
      "type": "arrow",
      "x": 0,
      "y": 0,
      "startElementId": "lb",
      "endElementId": "db"
    }
  ]
}
```

### REST API Mode

1. Plan your coordinate grid first.
2. Optional: `curl -X DELETE http://127.0.0.1:3000/api/elements/clear`
3. Create elements using `POST /api/elements/batch`. Use `"label": {"text": "..."}` for labels.
4. Bind arrows with `"start": {"id": "..."}` / `"end": {"id": "..."}`.
5. Verify with `GET /api/elements` (parse the JSON manually — equivalente a `describe_scene`) → run Quality Checklist on the structured output. Use `POST /api/export/image` only if the user explicitly asks for a visual screenshot.

**REST API element + arrow example:**

```bash
curl -X POST http://127.0.0.1:3000/api/elements/batch \
  -H "Content-Type: application/json" \
  -d '{
    "elements": [
      {"id": "svc-a", "type": "rectangle", "x": 100, "y": 100, "width": 160, "height": 60, "label": {"text": "Service A"}},
      {"id": "svc-b", "type": "rectangle", "x": 400, "y": 100, "width": 160, "height": 60, "label": {"text": "Service B"}},
      {"type": "arrow", "x": 0, "y": 0, "start": {"id": "svc-a"}, "end": {"id": "svc-b"}, "label": {"text": "calls"}}
    ]
  }'
```

---

## Arrow Routing — Avoid Overlaps

Straight arrows can cross through elements in complex diagrams. Use curved or elbowed arrows when needed:

**Curved arrows** (smooth arc over obstacles):

```json
{
  "type": "arrow",
  "x": 100,
  "y": 100,
  "points": [
    [0, 0],
    [50, -40],
    [200, 0]
  ],
  "roundness": { "type": 2 }
}
```

The intermediate waypoint `[50, -40]` lifts the arrow upward. `roundness: {type: 2}` makes it smooth.

**Elbowed arrows** (right-angle / L-shaped routing):

```json
{
  "type": "arrow",
  "x": 100,
  "y": 100,
  "points": [
    [0, 0],
    [0, -50],
    [200, -50],
    [200, 0]
  ],
  "elbowed": true
}
```

**When to use which:**

- Fan-out (one source → many targets): curved arrows with waypoints spread to avoid overlapping
- Cross-lane (connecting to side panels): elbowed arrows that go up, then across, then down
- Long horizontal connections: curved arrows with a slight vertical offset

**Rule:** If an arrow would pass through an unrelated shape, add a waypoint to route around it.

**Points format**: Both `[[x, y], ...]` tuples and `[{"x": ..., "y": ...}]` objects are accepted; both are normalized automatically.

---

## Workflow: Iterative Refinement

**Feedback loop:** `batch_create_elements` → `describe_scene` → fix issues with `update_element` → `describe_scene` → proceed.

---

## Workflow: Refine an Existing Diagram

1. `describe_scene` to understand current state — note element IDs and positions.
2. Identify elements by `id` or label text (not by x/y coordinates — they change).
3. `update_element` to resize/recolor/move; `delete_element` to remove.
4. Re-run `describe_scene` to confirm the result (positions, sizes, colors, connections). Use `get_canvas_screenshot` only if the user explicitly asks to see the image.
5. If updates fail: check the ID exists with `get_element`; check it's not locked with `unlock_elements`.

---

## Workflow: Mermaid Conversion

For converting existing Mermaid diagrams to Excalidraw:

**MCP mode:**

```
create_from_mermaid(mermaidDiagram: "graph TD\n  A --> B\n  B --> C")
```

After conversion, call `set_viewport` with `scrollToContent: true` and run `describe_scene` to verify the layout. If the auto-layout is poor (nodes crowded, edges crossing — visible from overlapping bounding boxes), identify problem elements with `describe_scene` and reposition with `update_element`.

---

## Workflow: File I/O

- Export to `.excalidraw`: `export_scene` with optional `filePath`
- Import from `.excalidraw`: `import_scene` with `mode: "replace"` or `"merge"`
- Export to image: `export_to_image` with `format: "png"` or `"svg"` (requires browser open)
- Share link: `export_to_excalidraw_url` — encrypts scene, returns shareable excalidraw.com URL
- CLI export: `node scripts/export-elements.cjs --out diagram.elements.json`
- CLI import: `node scripts/import-elements.cjs --in diagram.elements.json --mode batch|sync`

## Workflow: Snapshots

1. `snapshot_scene` with a name before risky changes.
2. Make changes, evaluate with `describe_scene` (default). Use a screenshot only if the user explicitly asks to see the canvas image.
3. `restore_snapshot` to roll back if needed.

## Workflow: Duplication

`duplicate_elements` with `elementIds` and optional `offsetX`/`offsetY` (default: 20, 20). Useful for repeated patterns or copying layouts.

## Error Recovery

- **Elements not appearing?** Check `describe_scene` — they may have been created off-screen. Use `set_viewport` with `scrollToContent: true`.
- **Arrow not connecting?** Verify element IDs with `get_element`. Make sure `startElementId`/`endElementId` (MCP) or `start.id`/`end.id` (REST) match existing element IDs.
- **Canvas in a bad state?** `snapshot_scene` first, then `clear_canvas` and rebuild. Or `restore_snapshot` to go back.
- **Element won't update?** It may be locked — call `unlock_elements` first.
- **Layout looking wrong after import?** Use `describe_scene` to inspect actual positions, then batch-update positions.
- **Duplicate text elements?** Auto-sync may re-inject cached bound texts after `clear_canvas`. Clean up by deleting `type: "text"` elements with a `containerId`. Best prevention: never put labels on background zone rectangles — use free-standing text elements.

---

## References

- `references/cheatsheet.md`: Complete MCP tool list (26 tools) + REST API endpoints + payload shapes.
