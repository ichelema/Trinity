---
description: Promozione curata dei fatti dai bank di progetto al bank core Hindsight
---

# Promote

Rivedi i candidati alla promozione dai bank Hindsight di progetto al bank CORE
condiviso e promuovi SOLO quelli approvati dall'utente. La promozione è curata:
MAI promuovere senza approvazione esplicita.

Lo script meccanico è:

```bash
python "${CLAUDE_PLUGIN_ROOT}/hooks/hindsight/ops/hindsight-promote.py"
```

## Flusso operativo

1. **Report candidati**: leggi `${CLAUDE_PLUGIN_ROOT}/logs/promote-candidates.json`.
   - Se esiste ed è fresco (generato da meno di 7 giorni), usalo direttamente.
   - Altrimenti rigeneralo: `python .../hindsight-promote.py --triage`
     (richiede il server Hindsight su :8888 e `OPENAI_API_KEY`; usa il triage
     gpt-4.1-nano con cache dei verdetti, quindi è economico ripeterlo).
2. **Review umana**: mostra all'utente una tabella dei candidati con:
   - bank di provenienza e doc_id
   - motivazione del triage (`reason`)
   - anteprima del contenuto (`preview`)
   Chiedi quali promuovere. L'utente può anche promuovere documenti che il
   triage ha scartato: in quel caso usa `--scan` per l'elenco completo dei
   non revisionati.
3. **Move degli approvati** (uno per documento):

   ```bash
   python .../hindsight-promote.py --move <DOC_ID> --bank <BANK>
   ```

   Il move fa: retain dell'`original_text` sul core (con strip dei tag
   `repo:`/`branch:`) + `delete_document` dal bank progetto + aggiornamento
   dello state file. È un MOVE, non una copia: un fatto vive in un solo bank.
4. **Reject dei respinti** (così non ricompaiono al prossimo scan):

   ```bash
   python .../hindsight-promote.py --reject <DOC_ID> --bank <BANK>
   ```

5. **Riepilogo finale**: mostra `--status` (promossi/respinti totali).

## Regole

- Promuovi solo fatti TRASVERSALI: utili anche su un progetto completamente
  diverso (preferenze utente, vincoli d'ambiente, procedure di toolchain).
- I fatti specifici del progetto restano nel suo bank: NON è un difetto,
  è l'isolamento voluto.
- Non promuovere mai in automatico, nemmeno se il triage è molto confidente.
- Non salvare o mostrare segreti, API key, token, password.
