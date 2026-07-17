---
description: Promozione curata dei fatti dai bank di progetto al bank core Hindsight
---

# Promote

Rivedi i candidati alla promozione dai bank Hindsight di progetto al bank CORE
condiviso e promuovi SOLO quelli approvati dall'utente. La promozione è curata:
MAI promuovere senza approvazione esplicita.

Lo script meccanico è (risolvi l'interprete come gli hook: `hs-python.sh`
esporta `$HS_PY` — su Windows il python del PATH, su Linux/mac quello di mise —
e imposta `PYTHONUTF8=1`; ogni blocco sotto assume `$HS_PY` già risolto così):

```bash
. "${CLAUDE_PLUGIN_ROOT}/hooks/hindsight/lib/hs-python.sh"
"$HS_PY" "${CLAUDE_PLUGIN_ROOT}/hooks/hindsight/ops/hindsight-promote.py"
```

## Flusso operativo

1. **Report candidati**: leggi `${CLAUDE_PLUGIN_ROOT}/logs/promote-candidates.json`.
   - Se esiste ed è fresco (generato da meno di 7 giorni), usalo direttamente.
   - Altrimenti rigeneralo: `"$HS_PY" .../hindsight-promote.py --triage`
     (richiede il server Hindsight su :8888 e `OPENAI_API_KEY`; usa il triage
     gpt-4.1-nano con cache dei verdetti, quindi è economico ripeterlo).
2. **Review umana**: mostra all'utente una tabella dei candidati con:
   - bank di provenienza e doc_id
   - motivazione del triage (`reason`)
   - contenuto COMPLETO del documento: il campo `preview` è troncato a 500
     caratteri e i documenti superano spesso i 1000, quindi approvare dal
     preview significa non vedere metà del testo. Leggi l'`original_text`
     intero (`GET /documents/<id>` sul bank di provenienza).
   Chiedi quali promuovere. L'utente può anche promuovere documenti che il
   triage ha scartato: in quel caso usa `--scan` per l'elenco completo dei
   non revisionati.
3. **Move degli approvati** (uno per documento):

   ```bash
   "$HS_PY" .../hindsight-promote.py --move <DOC_ID> --bank <BANK>
   ```

   Il move fa: retain dell'`original_text` sul core (con strip dei tag
   `repo:`/`branch:`) + `delete_document` dal bank progetto + aggiornamento
   dello state file. È un MOVE, non una copia: un fatto vive in un solo bank.

   Usa `--move` SOLO per i documenti interamente trasversali: sposta
   l'`original_text` per intero, senza guardarci dentro.
4. **Documenti MISTI** (fatti trasversali *e* fatti specifici del progetto nello
   stesso documento: normale, un documento contiene 3-6 fatti estratti). Il
   `--move` porterebbe sul core anche la parte specifica. Invece:
   - retain del solo fatto trasversale, **riscritto a mano**, direttamente sul
     core via REST — NON col tool MCP `mcp__hindsight__retain`: questo comando
     è a scope user e il retain MCP scrive sul bank risolto dal cwd, quindi
     lanciato fuori dal repo Trinity il fatto finirebbe in silenzio nel bank
     del progetto (l'opposto della promozione). La REST è indipendente dal
     cwd, stesso pattern del `--move`:

     ```bash
     CORE_URL="$("$HS_PY" -c "import sys; sys.path.insert(0, r'${CLAUDE_PLUGIN_ROOT}/hooks/hindsight/lib'); from hindsight_config import load_config, bank_url; cfg = load_config(); print(bank_url(cfg, (cfg.get('bank') or {}).get('core_bank', '')))")"
     curl -s -m 120 -X POST "$CORE_URL/memories" \
       -H "Content-Type: application/json" \
       -d '{"items":[{"content":"<fatto riscritto>","tags":["claude-code"],
            "metadata":{"promoted_from":"<BANK>"},
            "document_id":"promoted:<BANK>:<DOC_ID>#curato"}],"async":false}'
     ```

     Verifica `"success": true` nella risposta (sync: può durare fino a ~90s).
     Il `document_id` deterministico fa upsert su retry invece di duplicare;
     il suffisso `#curato` lo distingue dall'id di un eventuale `--move` dello
     stesso documento.
   - poi tratta il documento come respinto (punto 5): il sorgente resta nel
     bank del progetto, dove i fatti specifici devono stare.
5. **Reject dei respinti** (così non ricompaiono al prossimo scan):

   ```bash
   "$HS_PY" .../hindsight-promote.py --reject <DOC_ID> --bank <BANK>
   ```

6. **Riepilogo finale**: mostra `--status` (promossi/respinti totali).

## Regole

- Promuovi solo fatti TRASVERSALI: utili anche su un progetto completamente
  diverso (preferenze utente, vincoli d'ambiente, procedure di toolchain).
- I fatti specifici del progetto restano nel suo bank: NON è un difetto,
  è l'isolamento voluto.
- Non promuovere mai in automatico, nemmeno se il triage è molto confidente.
- Non salvare o mostrare segreti, API key, token, password.
