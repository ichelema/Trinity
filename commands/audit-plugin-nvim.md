---
description: Audit di un plugin Neovim — report categorizzato, fix guidati uno-a-uno, header doc e commit granulari
argument-hint: <nome-plugin>  (es. trouble)
---

# Audit plugin Neovim

Esegui un audit completo del plugin Neovim indicato.

Plugin da auditare: **`$ARGUMENTS`**
(se vuoto, chiedi all'utente quale plugin auditare prima di procedere)

## Path di riferimento

| Cosa | Path |
|---|---|
| Config del plugin (modificabile) | `/c/Users/$USERNAME/AppData/Local/nvim/lua/sphynx/plugins/<plugin>.lua` |
| Documentazione | `/c/Download/<nome-plugin>.txt` — oppure una cartella `/c/Download/<nome-plugin>-doc/` con più `.txt`. Verifica quale dei due esiste. |
| Sorgente originale (SOLO lettura) | `/c/Users/$USERNAME/AppData/Local/nvim-data/lazy/<plugin>` |
| Elenco moduli / commenti | `/c/Users/$USERNAME/AppData/Local/nvim/lua/sphynx/core/3-plugins.lua` |

> I path MSYS (`/c/...`) valgono nella shell bash. Negli script Python/Ruby usa path Windows (`C:/Users/...`).

## Regole fondamentali

- **NON modificare** mai il sorgente del plugin in `nvim-data/lazy/<plugin>`: viene sovrascritto al prossimo `:Lazy update` e sporca il git del plugin. Puoi **ispezionarlo** per capire come funziona. Le modifiche vanno **solo** nella config dell'utente (`sphynx/plugins/<plugin>.lua`).
- Proponi **monkey patch** (override nella config) **solo se strettamente necessario**, segnalando che sono fragili.
- Ogni rilievo dev'essere **ancorato al codice reale** (`file:riga`), mai inventato. I plugin maturi spesso fanno scelte deliberate: non spacciarle per bug.
- Dopo ogni modifica a un file `.lua`, fai un **parse-check**: `luac -p <file>` (luac è in `/ucrt64/bin`).
- **Attenzione agli EOL**: prima di editare, misura i CR con `tr -cd '\r' < file | wc -c` (NON `grep`). Il tool Edit normalizza a LF: su file con EOL misti causa churn. Verifica i CR del commit con `git show` prima del push.

## Fase 1 — Analisi e report

1. Leggi la config del plugin e la sua documentazione; verifica che sia scritto correttamente e che **rispetti la documentazione**.
2. Controlla anche **fuori dal file** del plugin: possibili **conflitti**, **keymap già assegnate** altrove (cerca nei vari `sphynx/plugins/*.lua` e nei file core), **ottimizzazioni** correlate al plugin.
3. Produci un **report sintetico** suddiviso per **categorie**: Bug funzionali, Performance, Ottimizzazioni, Robustezza, Minori, Conflitti/Keymap, Aderenza alla doc.
4. Indica la **gravità** di ogni anomalia con un pallino colorato:
   - 🔴 **critica** — rompe funzionalità / bug certo ad alto impatto
   - 🟠 **alta** — bug o problema concreto, impatto medio
   - 🟡 **media** — ottimizzazione utile / incoerenza
   - 🟢 **bassa** — minore / stilistico
5. Chiudi il report con una **tabella riassuntiva** (es. `# | Categoria | Gravità | File:riga | Sintesi`).

## Fase 2 — Correzione guidata, un'anomalia per volta

Dopo il report, **NON** applicare tutto in blocco. Per ogni anomalia, una alla volta:

1. Mostra il **contesto** con il **codice** che la riguarda (`file:riga`).
2. Mostra la **diff** di cosa faresti per sistemarla, spiegando il perché.
3. Applica **solo dopo conferma**, poi `luac -p` di verifica.
4. Prosegui con la successiva.

## Fase 3 — Header di documentazione

Dopo aver fixato tutte le anomalie e fatto le ottimizzazioni, compila in cima al file del plugin l'header con questo template (adattando i contenuti al plugin reale):

```text
--[[
===============================================================================================
Plugin: <nome-plugin>
===============================================================================================
Description: <descrizione su una o due righe, allineata sotto "Description: ">
Status: Active
Author: <autore>
Repository: <url>
Notes:
 - <nota rilevante sulla config reale>
 - <...>
Keymaps:
 - <key>                 → <cosa fa>
 - <:Comando>           → <cosa fa>
TODO:
 - [ ] <eventuale miglioramento futuro>
===============================================================================================
--]]
```

Mantieni lo **stile degli altri header** del progetto (es. `todo-comments.lua`, `telescope.lua`), incluso l'uso dell'apostrofo al posto degli accenti (`gia'`, `piu'`, `e'`).

## Fase 4 — Commento in 3-plugins.lua

Nel file `core/3-plugins.lua`, sulla **riga del plugin modificato**, verifica se è presente il commento descrittivo. Formato:

```text
    "<plugin>",                  -- OK - <descrizione>
```

Se manca, inseriscilo **mantenendo l'allineamento** delle altre righe (la colonna del `--` è la stessa per tutte).

## Fase 5 — Commit granulari e push

- Le modifiche sono nel repo **`sphynx79/neovim_config`** (config nvim), branch **`main`**.
- Fai un **commit per ogni intervento** (NON un unico commit massimo): es. un commit per ogni fix applicato, uno per l'header, uno per il commento in `3-plugins.lua`. Commit message in conventional commit italiano, come lo storico (`fix(<plugin>): ... `, `docs(<plugin>): + header`).
- Chiudi i messaggi con:
  `Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>`
- Alla fine, **push** su `origin main`.
- Prima del push, verifica il diff (`git show`) per escludere churn EOL non voluto.

## Promemoria

- L'utente preferito si chiama **Sphynx**.
- Mostra sempre il diff/codice prima di applicare modifiche non banali.
- Se l'utente tiene `3-plugins.lua` aperto in nvim, ricordagli `:e!` dopo le modifiche su disco.
