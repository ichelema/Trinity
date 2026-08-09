---
description: Audit della memoria (file-based + Hindsight) contro le daily note Obsidian, con report ad approvazione manuale
argument-hint: "[apply]"
---

# Dream

Audita le memorie persistenti (file-based di Claude Code + Hindsight) usando le
daily note di Obsidian come FONTE DI VERITÀ: individua memorie obsolete, da
aggiornare, fatti importanti mai salvati e violazioni della policy di MEMORY.md.
NESSUNA azione viene eseguita senza checkbox flaggato dall'utente nel report:
il checkbox È la conferma esplicita.

Le daily indicano COSA verificare, ma ogni fatto verificabile va confermato
sullo stato REALE del sistema (config, file, comandi). Gerarchia delle fonti:
stato reale > daily note > trascrizioni sessioni > memorie.

L'audit copre TUTTI i progetti: ogni directory memoria in
`~/.claude/projects/*/memory/` e ogni bank Hindsight sul server. Tutte le
operazioni Hindsight usano la REST API (indipendente dal cwd), MAI i tool MCP
`hindsight/*`: quelli parlano solo col bank risolto dal cwd e colpirebbero il
bank sbagliato.

## Percorsi

- Memoria file-based (tutti i progetti): `~/.claude/projects/*/memory/`
- Trascrizioni sessioni (fonte ausiliaria, READ-ONLY): `~/.claude/projects/<project>/*.jsonl`
- API REST Hindsight: `http://127.0.0.1:8888/v1/default`
- Daily note (READ-ONLY, mai modificarle): `e:/obsidian/sinapsi/🌅Daily/YYYY-MM/YYYY-MM-DD.md`
- Report: `${CLAUDE_PLUGIN_ROOT}/logs/dream/report-YYYY-MM-DD.md`
- Stato: `${CLAUDE_PLUGIN_ROOT}/logs/dream/state.json`

## Modalità

Ricava la modalità da `$ARGUMENTS`: vuoto → AUDIT; `apply` → APPLY; qualsiasi
altro valore → spiega l'uso (audit / apply) e fermati.

## Esecuzione multi-agente

- Il command gira in modalità multi-agente: Fable (il modello della sessione)
  fa da ORCHESTRATORE e non delega la supervisione; i task di lavoro vanno a
  subagent lanciati col tool Agent con `model: "opus"` (Opus 5).
- In AUDIT delega a subagent Opus, in parallelo quando indipendenti: lettura
  di daily e trascrizioni, audit file-based per progetto, audit di ciascun
  bank Hindsight, verifiche sul campo. Ogni subagent restituisce dati grezzi
  (fatti, discrepanze, proposte), non il report.
- In APPLY puoi delegare a subagent Opus gruppi omogenei di azioni; la
  marcatura degli esiti nel report e l'aggiornamento dello stato restano
  all'orchestratore.
- CONTROLLO FINALE (Fable, mai delegato): prima di scrivere il report o il
  riepilogo di apply, verifica il lavoro dei subagent — campiona le azioni
  proposte ricontrollando Fonte e Verifica, controlla ID univoci e contatori
  coerenti, e che nessuna azione violi le Regole. Ciò che non passa si
  corregge o si scarta.

## Flusso AUDIT

1. **Finestra**: leggi `state.json`. Finestra = da `last_audit` a adesso.
   Se il file non esiste (primo giro): ultimi 14 giorni.
2. **Daily note**: elenca le daily nella finestra con Glob su
   `e:/obsidian/sinapsi/*Daily/*/*.md` filtrando per data nel nome file
   (fallback: `ls` via Bash col path quotato se l'emoji dà problemi). Di ogni
   daily leggi solo le sezioni utili all'audit:
   - `## 🤖 Riassunto sessione Agente AI` — in particolare i `#### Dettagli tecnici`
     (commit, file, comandi, numeri esatti) e i `#### Risultato ottenuto`
   - `## 📚 Cose apprese oggi`
   - `## 🎯 Obiettivi`
3. **Trascrizioni sessioni (fonte ausiliaria)**: i file
   `~/.claude/projects/<project>/*.jsonl` modificati nella finestra. NON
   leggerle mai integralmente (sono JSONL grandi): usale solo con Grep mirato
   per parole chiave, quando una daily è ambigua o manca contesto — per
   confermare un fatto, recuperare comandi/valori esatti, o coprire lavoro
   svolto ma non registrato nelle daily.
4. **Memoria file-based**: trova tutte le directory memoria con Glob su
   `~/.claude/projects/*/memory/MEMORY.md`. Per ciascuna leggi `MEMORY.md`
   (compresa la policy nel commento HTML in testa, dove presente: "il
   file-based tiene SOLO lo stretto necessario, il resto in Hindsight") e
   tutti i file tematici della directory. Verifica anche la coerenza
   dell'indice: voci che puntano a file inesistenti, file senza voce, hook
   contraddittori col contenuto, indice oltre le 200 righe → proponi il fix
   nella categoria **Violazioni policy**.
5. **Hindsight (audit completo, via REST)**: `GET /banks` per l'elenco dei
   bank; per ogni bank `GET /banks/<bank>/memories/list` e
   `GET /banks/<bank>/documents` paginando fino a esaurimento (percent-encode
   il nome del bank negli URL). ESCLUDI i bank il cui nome contiene
   `obsidian`: sono in sola lettura, li sincronizza il plugin di Obsidian —
   non vanno né auditati né modificati. Se il server non risponde: prosegui in audit
   parziale solo file-based e marca il degrado nell'intestazione del report
   ("Server Hindsight: NON RAGGIUNGIBILE — audit parziale").
6. **Confronto semantico** (le daily vincono sempre sulle memorie):
   - memoria contraddetta dai fatti delle daily → **Obsolete** o **Da aggiornare**
   - fatto importante nelle daily assente dalla memoria → **Nuove da salvare**;
     prima di proporlo verifica con un recall mirato via REST
     (`POST /banks/<bank>/memories/recall`) che non esista già (evita falsi
     "mancante"). Cosa cercare, in ordine di priorità: correzioni esplicite
     dell'utente, decisioni architetturali/implementative, modifiche a
     strumenti/comandi/workflow, pattern di debugging ricorrenti con soluzione
     verificata, preferenze stabili. NON proporre: stato temporaneo di
     debugging, conclusioni speculative, errori occasionali, info deducibili
     dal codice
   - prima di proporre `file-create` o un nuovo retain, cerca il file tematico
     o il documento esistente più pertinente da aggiornare: creare è l'ultima
     scelta
   - file-based che viola la policy di MEMORY.md (chiediti: "serve a OGNI
     sessione?" — se no, va in Hindsight) → **Violazioni policy**
   - duplicati o sovrapposizioni tra memorie → proponi merge nella categoria
     più adatta
7. **Verifica sul campo**: per ogni fatto verificabile — config, path,
   versioni, tool, impostazioni — conferma lo stato ATTUALE prima di proporre
   l'azione: leggi il file di configurazione, controlla il path, lancia il
   comando read-only. Esempio: una memoria parla del sistema di reranking →
   leggi `hindsight.config.json` e verifica il reranker davvero configurato.
   Per capire DOVE verificare (quale file, config o comando) aiutati con un
   recall mirato (REST) e con le memorie stesse.
   - la verifica conferma la daily → procedi con l'azione
   - la verifica contraddice la daily → vince lo stato reale; segnala la
     discrepanza nel report
   - fatto non verificabile sul campo (eventi, decisioni, preferenze) →
     valuta sulla sola daily e marcalo come tale nel report
8. **Report**: scrivi `logs/dream/report-YYYY-MM-DD.md` nel formato sotto.
   Se esiste già (secondo audit lo stesso giorno), prima copialo in `.bak`.
9. **Stato**: aggiorna SOLO `last_report` in `state.json`. NON toccare
   `last_audit`: avanza solo ad apply completato, così un report mai applicato
   non fa perdere la finestra.
10. **Chiusura**: riassumi in prosa nel messaggio finale cosa hai trovato
   (contatori per categoria, le azioni più rilevanti) e invita a flaggare i
   checkbox nel report e lanciare `/trinity:dream apply`.

## Formato del report

```markdown
# Dream report — YYYY-MM-DD

- Generato: <ISO>
- Finestra: <window_start ISO> → <window_end ISO>
- Daily analizzate: <n> — <elenco date>
- Memoria file-based: <n> progetti, <n> file · Hindsight: <n> bank, <n> documenti, <n> fatti · Server Hindsight: OK
- Azioni proposte: <n> (obsolete: n, aggiornamenti: n, nuove: n, policy: n, mental model: n)

Flagga `[x]` le azioni che approvi, poi lancia `/trinity:dream apply`.
Le azioni non flaggate saranno considerate respinte.

Legenda tipi: hs-invalidate = il fatto resta archiviato ma non verrà più
richiamato · hs-update = corregge il testo di un fatto · hs-correct-doc =
riscrive un documento errato · hs-retain = salva un fatto nuovo ·
file-update/-delete/-create = modifica/cancella/crea un file memoria (sempre
con backup .bak) · policy-migrate = sposta un file memoria in Hindsight ·
mm-refresh = rigenera i mental model

## Obsolete

- [ ] **A1** · hs-invalidate · bank `<bank>` · fatto `<memory_id>`
  - Cosa fa: <una frase semplice: di cosa parla la memoria e perché non vale più>
  - Attuale: "<claim della memoria>"
  - Motivo: daily YYYY-MM-DD §"<sezione ###>" — "<citazione breve>"
  - Verifica: `hindsight.config.json` — reranker effettivo: voyage/rerank-2.5 ✓

## Da aggiornare

- [ ] **A2** · file-update · `~/.claude/projects/<slug>/memory/<file>.md`
  - Cosa fa: <una frase semplice: quale memoria viene corretta e come>
  - Attuale: "<claim attuale>"
  - Proposta (testo esatto che verrà scritto):
    ```
    <nuovo contenuto>
    ```
  - Fonte: daily YYYY-MM-DD §"<sezione>" — "<citazione>"
  - Verifica: <file/comando controllato e cosa risulta>

## Nuove da salvare

- [ ] **A3** · hs-retain · bank `<bank>`
  - Cosa fa: <una frase semplice: quale fatto nuovo viene salvato e a che serve>
  - Proposta (testo esatto): "<contenuto del retain>"
  - Tags: claude-code (+ repo:<nome> solo se già presente nel bank)
  - Fonte: daily YYYY-MM-DD §"<sezione>"
  - Verifica: solo daily (fatto non verificabile sul campo)

## Violazioni policy MEMORY.md

- [ ] **A4** · policy-migrate · `~/.claude/projects/<slug>/memory/<file>.md` → bank `<bank>`
  - Cosa fa: <una frase semplice: quale memoria viene spostata e perché>
  - Motivo: dettaglio tecnico non usato a ogni sessione → per policy va in Hindsight
  - Proposta: hs-retain del contenuto (testo esatto sotto) + delete del file + rimozione riga indice
    ```
    <testo del retain>
    ```

## Mental model

- [x] **A5** · mm-refresh · rigenera i mental model
  - Pre-flaggata: necessaria se approvi qualunque azione hs-*. Togli la spunta
    solo se non approvi nessuna azione Hindsight.
```

Regole del formato:

- ID stabili `A1..An`, sequenziali, mai rinumerati.
- Un solo checkbox per azione, sulla stessa riga dell'ID (parsing in apply:
  `- [x] **A<n>**`).
- Ogni azione deve essere comprensibile DA SOLA, senza aprire altri file: la
  riga `Cosa fa` spiega in una frase di cosa parla la memoria, cosa cambierà
  e perché — linguaggio semplice, niente sigle o ID non spiegati. Chi legge
  deve poter decidere il flag leggendo solo il blocco.
- Per update/create riporta sempre il contenuto proposto ESATTO: l'utente
  approva ciò che verrà scritto, non un'intenzione vaga.
- Ogni azione cita la Fonte (daily + sezione) che la giustifica; per fatti
  emersi solo dalle trascrizioni, cita il file `.jsonl` e la parola chiave
  usata per trovarli.
- Le azioni `hs-*` indicano sempre il bank di destinazione; le azioni `file-*`
  il path completo del file (forma `~/...`).
- Ogni azione riporta la riga `Verifica:` — come il fatto è stato confermato
  sullo stato reale (file letto, comando lanciato, valore trovato), oppure
  `solo daily (fatto non verificabile sul campo)`. Se la verifica contraddice
  la daily, l'azione lo dichiara e propone lo stato reale.
- Nelle proposte di testo converti i riferimenti temporali relativi ("ieri",
  "la settimana scorsa") in date assolute.
- `mm-refresh` è l'UNICA azione pre-flaggata (con nota); tutte le altre nascono `[ ]`.
- Zero azioni → report con sola intestazione + "Memoria allineata, nessuna
  azione proposta."

## Flusso APPLY

1. Leggi `state.json` → `last_report`. Se stato o report mancano:
   "nessun report: lancia prima `/trinity:dream`" e fermati.
2. Leggi il report. Azioni eseguibili = righe `- [x] **A<n>**` SENZA marcatore
   `→ FATTO`. Le `- [ ]` sono respinte e si saltano; le `→ ERRORE` flaggate si
   ritentano.
3. Esegui le azioni UNA alla volta secondo la tassonomia sotto. Dopo ciascuna,
   Edit del report per appendere l'esito in coda alla riga dell'ID:
   `→ FATTO <ISO>` oppure `→ ERRORE: <motivo breve>`. Il report è l'unico
   registro degli esiti.
4. Se almeno un'azione Hindsight è riuscita e `mm-refresh` è flaggata, a fine
   giro, una sola volta:

   ```bash
   bash "${CLAUDE_PLUGIN_ROOT}/hooks/hindsight/ops/hindsight-mental-models.sh" refresh --all
   ```

5. **Stato**: `last_audit` = il `window_end` letto dall'intestazione del report
   (NON "adesso": la prossima finestra parte da dove finiva quella auditata).
   Avanza anche con zero azioni flaggate (lanciare apply = review conclusa, il
   non flaggato è respinto). NON avanzare se ci sono azioni in `→ ERRORE`:
   correggile e rilancia apply.
6. **Riepilogo** in prosa: eseguite / respinte (non flaggate) / errori, con
   invito a rilanciare apply per i soli errori.

## Tassonomia azioni

| Tipo | Esecuzione in apply |
|---|---|
| `file-update` | `cp <file> <file>.bak` → Edit del corpo → aggiorna `metadata.modified` (ISO) → se cambia il senso, aggiorna la riga indice in MEMORY.md |
| `file-delete` | `cp` in `.bak` → `rm` → rimuovi la riga indice da MEMORY.md |
| `file-create` | Write con frontmatter conforme (name kebab, description, metadata.type, modified) + riga indice in MEMORY.md. RARO: solo se passa il test policy "serve a OGNI sessione?" |
| `hs-invalidate` | `curl -X PATCH <API>/banks/<bank>/memories/<id>` con `{"state": "invalidated", "reason": "dream YYYY-MM-DD"}` |
| `hs-update` | stesso PATCH con `{"text": "<testo corretto>"}` (ritocco puntuale di un singolo fatto) |
| `hs-correct-doc` | `curl -X DELETE <API>/banks/<bank>/documents/<id>` → retain REST (riga sotto) del testo corretto |
| `hs-retain` | `curl -X POST <API>/banks/<bank>/memories` con `{"items": [{"content": "<testo>", "context": "<dominio>", "tags": [...], "document_id": "dream:<YYYY-MM-DD>:<An>"}], "async": false}` — verifica `"success": true` (sync, fino a ~90s); il `document_id` deterministico fa upsert sui retry invece di duplicare. Tag SOLO universali (`claude-code`, `repo:<nome già nel bank>`; mai tag semantici) |
| `policy-migrate` | prima l'`hs-retain` e verifica che sia riuscito, POI il `file-delete` |
| `mm-refresh` | script refresh `--all`, una volta sola a fine apply |

`<API>` = `http://127.0.0.1:8888/v1/default`; header `Content-Type: application/json`;
nome bank sempre percent-encoded negli URL.

## Regole

- Le daily note sono READ-ONLY: mai Edit/Write nel vault durante dream.
- I bank Hindsight `obsidian` sono OFF-LIMITS: li sincronizza il plugin di
  Obsidian e sono in sola lettura — mai proporre né eseguire azioni su di essi
  (né retain, né update, né delete, né come destinazione di policy-migrate).
- Apply tocca SOLO: directory memoria, report, state file e bank Hindsight.
  Mai codice sorgente, config o test dei progetti.
- Mai eseguire un'azione non flaggata; mai flaggare al posto dell'utente
  (unica eccezione dichiarata: `mm-refresh`).
- `.bak` prima di ogni sovrascrittura o cancellazione di file (il `.gitignore`
  copre già `logs/` e `*.bak`).
- Non salvare o mostrare segreti, API key, token, password nel report.
