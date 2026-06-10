---
area:
  - 👦🏼personale
ambito:
  - 🧠apprendimento
type:
  - 📝nota
nota_type:
  - ⚛atomic
scope: main
project: null
tags:
  -
data_creazione: 2026-05-17T22:04
data_modifica: 2026-05-17T22:04
exclude_note_id: []
note_id: upUKWcMl76
---

# Template-Atomic
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
    && (file.inFolder("🌿Evergreen")
    || file.inFolder("⚛️Atomic")
    || file.inFolder("🪶Literature")
    || file.inFolder("🗃️Reference"))
	&& this.file.tags.length > 0
    && tags.containsAll(this.tags)
    && file.path != this.file.path
    && !this.file.hasLink(file)
    && if(this.exclude_note_id && note_id, !list(this.exclude_note_id).contains(note_id), true)


  folderGroup: |
    if(file.inFolder("🌿Evergreen"),"01 Evergreen",
    if(file.inFolder("⚛️Atomic"),"02 Atomic",
    if(file.inFolder("🪶Literature"),"03 Literature",
    if(file.inFolder("🗃️Reference"), "04 Reference",
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
      - property: data_modifica
        direction: DESC
    columnSize:
      file.folder: 196
      file.name: 402
      note.data_creazione: 133
      note.data_modifica: 131
```

