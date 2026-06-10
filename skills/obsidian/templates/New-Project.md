<%*
let titolo = await tp.system.prompt("Nome della nota");
await tp.file.rename(titolo);

// Tag wizard: inserisci tag separati da virgola (es: progetto/x, idea, #obsidian)
let rawTags = await tp.system.prompt("Tag (separati da virgola)", "");
let tags = (rawTags ?? "")
  .split(",")
  .map(t => t.trim())
  .filter(Boolean)
  .map(t => t.replace(/^#/, "")); // rimuove eventuale #

let tagsYaml = tags.length
  ? tags.map(t => `  - ${t}`).join("\n")
  : "  -"; // mantiene la struttura YAML anche se vuoto
-%>
---
area:
  - 👦🏼personale
ambito:
  - 🧠apprendimento
type:
  - 🛠progetto
progetto_stato:
  - 🚀progress
tags:
<% tagsYaml %>
data_creazione: <% tp.date.now("YYYY-MM-DDTHH:mm") %>
data_modifica: <% tp.date.now("YYYY-MM-DDTHH:mm") %>
---

## <% titolo %>
<% tp.file.cursor(1) %>

---
## 🎯 Obiettivo

---
## 🔗 Collegamenti
---
