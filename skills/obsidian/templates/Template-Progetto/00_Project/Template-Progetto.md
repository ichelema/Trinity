---
area:
  - 👦🏼personale
ambito:
  - 🧠apprendimento
type:
  - 📝nota
nota_type:
  - 🎯project
scope: project
project: Template
project_start: 2026-05-17
project_end:
tags:
  - 
data_creazione: 2026-05-17T22:08
data_modifica: 2026-05-17T22:10:11
exclude_note_id: []
note_id: ZxWLmJXd3k
---

# Template-Progetto
to
---

## 🎯 Obiettivo
*Dove voglio arrivare (il futuro, il risultato)*

---

## 📌 Contesto
*Da dove parto e perché (il presente, le condizioni)*

---

## 🗓️ Milestone
Traguardi intermedi misurabili che segnano avanzamento reale. Non sono task minuti
(quelli vanno in 📝 Todo rapido), sono checkpoint grossi: quando ne spunti uno, il progetto
è oggettivamente avanzato.

- [ ] 

---

## 📝 Todo rapido
*Micro-task atomici che puoi spuntare in una sessione di lavoro, la tua inbox operativa quotidiana del progetto.*
- [ ] 

---

# 🧩 Connessioni principali

## 🌿Note Evergreen
- 

---

## ⚛️ Note Atomic
- 

---

# 🔗Base di conoscenza non collegate

```base
filters: formula.includeNote
formulas:
  includeNote: |
    file.ext == "md"
    && (
      file.path.contains("🛠️Progetti/🚀Progress/Template/01_Evergreen")
      || file.path.contains("🛠️Progetti/🚀Progress/Template/02_Atomic")
    )
    && file.path != this.file.path
    && !this.file.hasLink(file)
    && if(this.exclude_note_id && note_id, !list(this.exclude_note_id).contains(note_id), true)

  folderGroup: |
    if(file.path.contains("🛠️Progetti/🚀Progress/Template/01_Evergreen"), "01 Evergreen",
    if(file.path.contains("🛠️Progetti/🚀Progress/Template/02_Atomic"), "02 Atomic",
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
      - property: formula.folderGroup
        direction: ASC
      - property: data_modifica
        direction: DESC
    columnSize:
      file.folder: 300
      file.name: 280
      note.data_creazione: 133
      note.data_modifica: 131
```

