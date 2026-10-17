---
name: deep-research
description: >-
  Ricerca approfondita su più fonti con report finale citato. Usala per revisioni della
  letteratura, confronti tra tecnologie e analisi di mercato o di dati. Non usarla per ricerche
  semplici da una sola query.
---

# Deep Research

Flusso in 5 fasi. Usa TodoWrite per tracciarle. Salva tutto in `research-<slug>/`
nella directory corrente.

## 1. Chiarire

Controlla se la domanda ha: più letture possibili, ambito mancante (tempo, dominio,
caso d'uso), obiettivo poco chiaro, tema troppo ampio.

- Domanda chiara: vai avanti.
- Ambiguità minori: dichiara l'assunzione e vai avanti.
- Ambiguità forte: usa AskUserQuestion. Massimo 3 domande, a scelta multipla, ognuna
  con il motivo.

## 2. Piano (`brief.md`)

- Domanda principale, in prima persona.
- 3-5 sotto-domande, ognuna con risposta indipendente.
- Parole chiave: primarie, secondarie, da escludere.
- Peso delle fonti: accademiche, notizie, tecniche, dati (somma circa 1).
- Ambito: tempo, geografia, profondità (panoramica, dettaglio, esaustivo).
- Criteri di successo misurabili.
- Formato dell'output: confronto, cronologia, analisi o riassunto.

## 3. Ricerca in parallelo

Scegli i ruoli che servono. Ogni ruolo ha un file in `references/`.

| Ruolo      | File                      | Usalo per                                    |
| ---------- | ------------------------- | -------------------------------------------- |
| Accademico | `references/academic.md`  | Paper, basi teoriche, evidenza peer-reviewed |
| Tecnico    | `references/technical.md` | Repository, documentazione, architettura     |
| Dati       | `references/data.md`      | Statistiche, metriche, tendenze              |
| Web        | `references/web.md`       | Notizie, report di settore, opinioni         |

Lancia i subagenti in un solo messaggio (tipo `general-purpose`). Il prompt di ognuno
contiene: il percorso del file del ruolo, il contenuto di `brief.md`, i confini del
compito e il nome del file di output (`<ruolo>-research.md`).

Iterazioni: 1 per temi mirati, 2 per esplorazione più approfondimento, 3 solo per temi
complessi. Se un subagente fallisce, riprova una volta con input più preciso. Se
fallisce ancora, continua e annota la lacuna.

## 4. Verifica

Leggi i file di output. Scegli le 5-10 affermazioni che reggono le conclusioni o che si
contraddicono. Controlla ognuna con `references/fact-check.md`.

Se un'affermazione portante risulta FALSE o UNVERIFIABLE, torna al passo 3 con una query
mirata, una sola volta. Se resta aperta, annotala tra le lacune e togli la conclusione che
si appoggia su di lei.

## 5. Sintesi e report

- Raggruppa i risultati per tema. Unisci i duplicati e conserva le fonti.
- Mostra le contraddizioni con una possibile spiegazione.
- Qualità delle fonti: peer-reviewed > documentazione tecnica > web > non verificato.
- Elenca i ruoli assenti e le lacune.
- Scrivi `report.md` con `references/report.md`.

## Regole

- Ogni affermazione ha una citazione. Senza fonte, scrivi "non verificato".
- Non scegliere solo le fonti che concordano.
- Indica la confidenza: high, medium o low.
