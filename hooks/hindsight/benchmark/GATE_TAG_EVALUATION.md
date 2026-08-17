# Valutazione del tag semantico generato dal gate di retain (ICH-85)

Data del test: 17 agosto 2026.

## Domanda

Conviene far restituire al gate pre-retain (`gpt-5.6-luna`, una sola chiamata
che già decide `action`/`reason`/`preview`/`context`) un tag aggiuntivo
`topic:*` scelto da un vocabolario chiuso, da unire ai tag fissi
`claude-code` + `repo:<nome>`?

Contesto: da ICH-85 `build_tags()` non genera più `branch:<nome>`; i tag fissi
restano `claude-code` + `repo:<nome>`. Un esperimento del 31 maggio 2026 aveva
già mostrato che tag semantici liberi frammentano la consolidation (71
partizioni su 72 documenti) senza migliorare il recall. Questa valutazione
riprova con un vocabolario chiuso a bassa cardinalità (8 valori) e con
un'alternativa che tiene il tag fuori dal recinto principale della
consolidation tramite `observation_scopes`.

## Vocabolario provato

`retain_gate_tag_vocabulary` in `hindsight.config.json`, 8 valori:
`topic:environment`, `topic:config`, `topic:workflow`, `topic:debugging`,
`topic:architecture`, `topic:data`, `topic:integration`, `topic:evaluation`.
Nessun bucket `other`. Le descrizioni per il prompt sono in
`GATE_TAG_DESCRIPTIONS` (`lib/hindsight_retain_gate.py`).

## Metodo

- Campione: i 150 documenti più recenti del bank core `trinity-project`
  (399 documenti totali al momento del test), esportati con `original_text`,
  `context`, `event_date` e `metadata` originali.
- Tag: una chiamata reale del gate per documento (`evaluate_retain` con
  `retain_gate_tag_enabled: true`, stessa libreria di produzione, schema JSON
  strict con `enum` del vocabolario). 150 su 150 taggati, 0 errori, 0 valori
  fuori vocabolario. Latenza p50 3.5 s, p95 7.9 s.
- Tre bank replica costruiti dagli STESSI documenti (stesso `document_id`,
  contenuto, context, timestamp, metadata), diversi solo per tag e scope:
  - **A** baseline: `[claude-code, repo:<repo>]`, scope di default.
  - **B** gate tag: `A + [topic:x]`, scope di default (un recinto per topic).
  - **D** gate tag con doppio recinto: `A + [topic:x]` e
    `observation_scopes = [A, A + [topic:x]]` (una observation generale più
    una per topic).
- Il server ha estratto i fatti e consolidato ogni bank (consolidation
  automatica più `POST /consolidate` finale, attesa fino a code vuote).
- Metriche di frammentazione dal DB (`memory_units`): partizioni (insiemi di
  tag distinti sui fatti `world`/`experience`), observation, `proof_count`.
- Metriche di recall: `gold_questions.json` (18 query ostiche) con i parametri
  di produzione (`budget mid`, `tags ["claude-code"]`, `tags_match any`,
  tipi observation/world/experience), MRR / R@1 / R@3 sui top-3, più la quota
  di query con due risultati quasi identici nel top-K (`difflib` ≥ 0.9).

Lo script riproducibile è `hindsight_gate_tag_bench.py` (`--limit 150`,
fasi riavviabili). Gli artefatti grezzi sono locali e ignorati da Git sotto
`artifacts/` (`gate_tag_docs.jsonl`, `gate_tag_assignments.jsonl`,
`gate_tag_metrics.json`, `gate_tag_report.md`).

## Distribuzione dei topic assegnati dal gate

| Topic | Documenti |
| --- | --- |
| `topic:config` | 32 |
| `topic:architecture` | 30 |
| `topic:debugging` | 26 |
| `topic:environment` | 21 |
| `topic:integration` | 20 |
| `topic:workflow` | 12 |
| `topic:evaluation` | 7 |
| `topic:data` | 2 |

Tutti gli 8 valori vengono usati; nessuno domina. Il vocabolario è quindi
utilizzabile dal modello senza forzature.

## Risultati

| Metrica | A (baseline) | B (topic) | D (topic + doppio recinto) |
| --- | --- | --- | --- |
| Documenti | 150 | 150 | 150 |
| Fatti (world+experience) | 1078 | 1079 | 1072 |
| Observation | 471 | 653 (+39%) | 1098 (+133%) |
| Observation / fatto | 0.437 | 0.605 | 1.024 |
| Partizioni di tag sui fatti | 2 | 9 | 9 |
| Fatti per partizione (media) | 539 | 120 | 119 |
| `proof_count` medio | 2.48 | 1.69 (−32%) | 1.90 (−23%) |
| `proof_count` max | 29 | 14 | 27 |
| Observation con `proof_count` > 1 | 210 / 471 (45%) | 174 / 653 (27%) | 293 / 1098 (27%) |
| MRR | 0.306 | 0.296 | 0.222 (−27%) |
| R@1 | 0.222 | 0.222 | 0.167 |
| R@3 | 0.389 | 0.389 | 0.278 (−29%) |
| Query con duplicati nel top-K | 0 % | 0 % | 5.6 % |

Note di lettura:

- La seconda partizione di A (11 fatti) è un documento storico con
  `metadata.repo = improvement+ICH-72-review-Fable` (nome cartella di un
  worktree senza remote, fallback di `git_info`): non c'entra col tag del gate.
- I valori assoluti di MRR sono bassi per tutte e tre le varianti perché il gold
  set copre l'intero bank (399 documenti) mentre le repliche ne hanno 150. Il
  confronto resta valido: le tre repliche hanno esattamente gli stessi documenti.
- Con un solo recinto (A) il consolidator serializza su un unico lock di scope;
  con 8-9 recinti (B/D) parallelizza. In pratica A ha impiegato più tempo per
  fatto ma D, dovendo consolidare ogni fatto in due recinti, è stato il più
  lento in assoluto (circa 2 ore per 1072 fatti).

## Lettura

- **B** frammenta come previsto: +39% di observation, `proof_count` medio
  −32%, quota di observation confermate da più fonti dal 45% al 27%. Il recall
  non migliora (MRR −3%, R@1 e R@3 identici): il tag non entra nel ranking e il
  filtro di produzione (`claude-code`, `any`) non lo usa.
- **D** elimina la frammentazione del recinto generale ma raddoppia le
  observation: la stessa conoscenza esiste due volte (generale + per topic) e
  finisce nel recall due volte. MRR −27%, R@3 −29%, prime query con doppioni
  nel top-K. Costo di consolidation lato server raddoppiato.
- **A** è la variante con la sintesi più forte (`proof_count` massimo, più
  observation multi-fonte) e il recall migliore.

## Decisione

**Rifiutato**: il gate NON produce il tag aggiuntivo in produzione.
`retain_gate_tag_enabled` resta `false`. I tag automatici sono soltanto
`claude-code` + `repo:<nome>`.

Il codice del tag (schema/prompt estesi, `validate_gate_tag`,
`merge_gate_tags`, chiavi di config) resta nella libreria, spento e coperto
dai test, per poter ripetere la misura con un altro vocabolario o quando il
recall saprà usare il topic come filtro. Il worker non lo unisce ai tag e non
imposta `observation_scopes`.

## Cosa servirebbe per riconsiderarlo

1. Un classificatore lato recall che scelga il topic della domanda e filtri
   con `tags_match all` sul topic: senza, il tag non porta selettività.
2. Con D, un filtro di recall che scelga UN solo recinto (generale oppure topic)
   per non restituire due volte la stessa observation.
3. Rimisurare con questo stesso bench (`hindsight_gate_tag_bench.py`) su un
   campione più ampio, confrontando sempre con la baseline A.
