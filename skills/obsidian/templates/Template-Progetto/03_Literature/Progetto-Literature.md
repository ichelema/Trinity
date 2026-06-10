---
area:
  - 👦🏼personale
ambito:
  - 🧠apprendimento
type:
  - 📝nota
nota_type:
  - 📔literature
scope: project
project: Template-Progetto
tags:
  -
data_creazione: 2026-05-17T22:16
data_modifica: 2026-05-17T22:16
exclude_note_id: []
note_id: waAwcJArZs
---

# Progetto-Literature
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

## 🪶Note Literature
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
    && (
      file.path != null
      && (
        file.inFolder("🌿Evergreen")
        || file.inFolder("⚛️Atomic")
        || file.inFolder("🪶Literature")
        || file.inFolder("🗃️Reference")
        || file.path.contains("Template-Progetto/01_Evergreen")
        || file.path.contains("Template-Progetto/02_Atomic")
        || file.path.contains("Template-Progetto/03_Literature")
        || file.path.contains("Template-Progetto/04_Reference")
      )
    )
    && this.file.tags.length > 0
    && tags.containsAll(this.tags)
    && file.path != this.file.path
    && !this.file.hasLink(file)
    && if(this.exclude_note_id && note_id, !list(this.exclude_note_id).contains(note_id), true)

  folderGroup: |
    if(file.inFolder("🌿Evergreen") || file.path.contains("Template-Progetto/01_Evergreen"), "01 Evergreen",
    if(file.inFolder("⚛️Atomic") || file.path.contains("Template-Progetto/02_Atomic"), "02 Atomic",
    if(file.inFolder("🪶Literature") || file.path.contains("Template-Progetto/03_Literature"), "03 Literature",
    if(file.inFolder("🗃️Reference") || file.path.contains("Template-Progetto/04_Reference"), "04 Reference",
    "99 Other"))))
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
      - property: file.name
        direction: ASC
      - property: data_modifica
        direction: DESC
    columnSize:
      file.folder: 379
      file.name: 149
      note.data_creazione: 133
      note.data_modifica: 131
```

