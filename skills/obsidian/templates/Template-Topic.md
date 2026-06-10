---
area:
  - 👦🏼personale
ambito:
  - 🧠apprendimento
type:
  - 📝nota
nota_type:
  - 🗩topic
scope: main
project: null
tags:
  -
data_creazione: 2026-05-17T21:16
data_modifica: 2026-05-17T21:16
exclude_note_id: []
note_id: Dx1hcuSuY6
---

# Template-Topic
---

## 🎯 Obiettivo
*Dove voglio arrivare (il futuro, il risultato)*

---

## 📌 Contesto
*Da dove parto e perché (il presente, le condizioni)*
 
---

## ...

---

# 📝 Todo

- [ ] 

---

# 🧩 Connessioni principali

## 🌿Note Evergreen
- 

---

## ⚛️ Note Atomic
- 

---

## 🗃️ Note Reference
- 

---

# 🔗Base di conoscenza non collegate

```base
filters: formula.includeNote
formulas:
  includeNote: |
    file.ext == "md"
    && (file.inFolder("🌿Evergreen")
    || file.inFolder("🗃️Reference"))
    && this.file.tags.length > 0
    && tags.containsAll(this.tags)
    && file.path != this.file.path
    && !this.file.hasLink(file)
    && if(this.exclude_note_id && note_id, !list(this.exclude_note_id).contains(note_id), true)
  folderGroup: |
    if(file.inFolder("🌿Evergreen"),"01 Evergreen",
    if(file.inFolder("🗃️Reference"), "02 Reference",
    "99 Other"))
views:
  - type: table
    name: View
    groupBy:
      property: formula.folderGroup
      direction: ASC
    order:
      - file.folder
      - file.name
      - data_creazione
      - data_modifica
      - tags
    sort:
      - property: data_modifica
        direction: DESC
    columnSize:
      file.folder: 196
      file.name: 402
      note.data_creazione: 133
      note.data_modifica: 131
```

