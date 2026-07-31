---
description: Crea/aggiorna la nota del giorno col lavoro della sessione corrente
---

# Nota del giorno

Crea (o aggiorna, se esiste già) la **nota del giorno** di oggi nel Vault Obsidian,
registrando il lavoro svolto in **questa sessione**.

Usa la skill `obsidian` e segui la sua reference operativa
`references/nota-del-giorno.md` come **unica fonte** per struttura, frontmatter,
path (`🌅Daily/YYYY-MM/YYYY-MM-DD.md`, sottocartella mensile), template e regole.
Non reinventare il formato.

## Procedura

1. Ricostruisci dalla sessione corrente, **senza inventare nulla**, solo ciò che è
   realmente accaduto: obiettivi, cosa è stato fatto, risultati e i dettagli tecnici
   esatti (commit hash, file toccati, comandi, numeri/porte).
2. Mappa **un task significativo = un blocco `###`** dentro
   `## 🤖 Riassunto sessione Agente AI`, con l'header identico al testo linkato in
   `## 🎯 Obiettivi` (carattere per carattere, altrimenti il link non risolve).
3. Se la daily di oggi **esiste già**, fai **append/patch** della nuova sessione
   (non sovrascrivere) e aggiorna `data_modifica`.
4. **Mostrami la bozza prima di scrivere.** Dopo il mio ok: crea/aggiorna via MCP,
   formatta con Prettier come da reference, e apri la nota in Obsidian.

## Vincoli (dalla reference)

Niente tag, nessun header che contenga `:`, numeri esatti nei dettagli tecnici,
un task = una sessione `###`.
