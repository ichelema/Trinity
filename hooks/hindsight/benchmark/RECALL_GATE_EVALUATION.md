# Valutazione del gate prima del recall Hindsight

Data del test: 10 agosto 2026.

## Domanda

Conviene aggiungere una valutazione prima del recall automatico, così da non
consultare Hindsight quando il prompt è autosufficiente?

## Metodo

- Campione: gli ultimi 100 prompt umani disponibili, tutti oltre 20 caratteri.
- Fonte: 83 transcript principali Claude Code; transcript di subagent, tool,
  comandi, messaggi interni e possibili segreti sono esclusi.
- Copertura: 82 prompt Trinity, 13 ReportFlussi, 4 Switchyard e 1 dal worktree.
- Contesto disponibile: 89 prompt su 100 avevano almeno uno scambio precedente.
- Baseline: recall fresco con la stessa configurazione dell'hook di produzione,
  incluso il percorso multi-bank e il rerank globale.
- Giudizio: `gpt-5.6-luna` ha valutato separatamente se la memoria poteva aiutare
  e se almeno un risultato restituito era concretamente utile.
- Candidati: euristica locale, `gpt-4.1-nano`, `gpt-4.1-mini`,
  `gpt-5.6-luna`; ogni LLM è provato col solo prompt e con i due scambi
  precedenti. È provata anche una combinazione euristica + LLM.

Lo script riproducibile è `hindsight_recall_gate_bench.py`. Gli artefatti grezzi
sono locali e ignorati da Git sotto `bench_results/`.

## Baseline

| Misura | Risultato |
|---|---:|
| Recall con almeno un risultato | 83% |
| Recall con almeno una memoria utile | 47% |
| Recall inutili | 53% |
| Latenza fresca p50 | 1.909 ms |
| Latenza fresca p95 | 7.194 ms |
| Errori/timeout del recall | 5% |

Il problema esiste: più di metà dei richiami non aggiunge memoria utile.
Tuttavia un risultato non vuoto non significa che il risultato sia utile:
83% dei richiami ha restituito qualcosa, ma solo il 47% ha restituito qualcosa
di concretamente utile.

## Benchmark dei gate

`Utili mantenuti` è la misura più importante: indica quanti richiami utili della
baseline il gate non perderebbe. `Falsi negativi` è il numero dei richiami utili
saltati su 100 prompt.

| Test | Recall evitati | Recall inutili tra quelli eseguiti | Recall utili tra quelli eseguiti | Utili mantenuti | Falsi negativi | Gate p50 |
|---|---:|---:|---:|---:|---:|---:|
| Sempre recall (attuale) | 0% | 53,0% | 47,0% | 100,0% | 0 | 0 ms |
| Euristica locale | 85% | 73,3% | 26,7% | 8,5% | 43 | <1 ms |
| `gpt-4.1-nano`, prompt | 86% | 35,7% | 64,3% | 19,1% | 38 | 816 ms |
| `gpt-4.1-nano`, + contesto | 84% | 43,8% | 56,2% | 19,1% | 38 | 804 ms |
| `gpt-4.1-mini`, prompt | 73% | 51,9% | 48,1% | 27,7% | 34 | 956 ms |
| `gpt-4.1-mini`, + contesto | 45% | 50,9% | 49,1% | 57,4% | 20 | 987 ms |
| `gpt-5.6-luna`, prompt | 34% | 50,0% | 50,0% | 70,2% | 14 | 2.008 ms |
| `gpt-5.6-luna`, + contesto | 25% | 52,0% | 48,0% | 76,6% | 11 | 1.700 ms |

Le varianti ibride non migliorano abbastanza il risultato. Il candidato migliore
resta Luna più contesto: conserva il 76,6% dei recall utili, ma aggiunge circa
1,7 secondi di gate mediano e perde comunque 11 richiami utili su 47.

## Effetto del contesto

Passare i due scambi precedenti aiuta i modelli più capaci:

- `gpt-4.1-mini`: recall utili mantenuti dal 27,7% al 57,4%;
- `gpt-5.6-luna`: dal 70,2% al 76,6%;
- `gpt-4.1-nano`: resta al 19,1%, senza beneficio misurabile.

Il contesto è quindi utile per capire riferimenti e continuazioni, ma non rende
il gate abbastanza sicuro. Inoltre aumenta la latenza e il costo.

## Tempo totale stimato

Sul campione, includendo gate e recall quando autorizzato:

| Strategia | Tempo medio per prompt |
|---|---:|
| Sempre recall | 2.536 ms |
| `gpt-4.1-nano`, prompt | 1.288 ms |
| `gpt-4.1-mini`, + contesto | 2.430 ms |
| `gpt-5.6-luna`, + contesto | 3.859 ms |

Il nano risparmia tempo soltanto perché salta quasi tutti i richiami, compreso
l'80,9% di quelli utili. Il mini con contesto risparmia appena 106 ms medi ma
perde il 42,6% dei richiami utili. Luna è più lento del recall diretto.

## Valutazione finale

**Non implementare ora un gate LLM binario nell'hook.**

Motivi:

1. Il falso negativo è troppo alto: il candidato migliore perde 11 richiami
   utili su 47.
2. I modelli veloci sono troppo aggressivi e perdono 20-38 richiami utili.
3. Il modello più prudente costa più tempo del recall che dovrebbe evitare.
4. Le euristiche locali ampie sono ancora peggiori: le parole del prompt non
   bastano per capire se la memoria contiene qualcosa di utile.
5. Un gate eseguito prima della cache rallenterebbe anche gli hit da circa
   500 ms; se si sperimentasse ancora, dovrebbe girare soltanto dopo un miss.

## Raccomandazione pragmatica

Mantenere per ora il comportamento attuale e ridurre il rumore dopo il recall:

- conservare il gate meccanico già presente (`>20` caratteri);
- mantenere i floor del reranker e il limite dei risultati iniettati;
- misurare e migliorare la qualità dei risultati, perché il 44% dei prompt ha
  ricevuto memoria direttamente azionabile o un vincolo utile, ma il 53% ha
  ricevuto solo rumore;
- registrare nel debug log `total_ms`, `recall_ms`, `cache` e numero di risultati,
  così da avere una baseline continua senza nuovi LLM;
- se si riprova un gate, partire da una modalità osservativa: calcola la
  decisione ma non salta il recall, poi confronta con almeno 500 prompt e review
  umana dei falsi negativi.

`reflect` non deve entrare nel percorso automatico: è deliberatamente più lento
e serve per sintesi importanti richieste esplicitamente, non per decidere se
eseguire un recall ordinario.

## Test supplementare: decisione prudente a tre esiti

È stato poi provato un prompt più prudente con tre risposte possibili:
`recall`, `uncertain` e `skip`. Solo `skip` evita Hindsight; gli altri due
eseguono il recall. Errori e output invalidi sono trattati come `uncertain`.

| Misura | Risultato |
|---|---:|
| `recall` | 90% |
| `uncertain` | 9% |
| `skip` | 1% |
| Recall evitati | 1% |
| Recall utili mantenuti | 97,9% |
| Falsi negativi | 1 su 47 |
| Gate p50 / p95 | 1.587 / 3.139 ms |
| Tempo totale medio | 4.320 ms |
| Baseline senza gate | 2.536 ms |

Il prompt prudente raggiunge quasi l'obiettivo del 98%, ma non produce un
vantaggio reale: evita un solo recall e proprio quel caso era utile secondo il
giudice. Inoltre aumenta il tempo medio del 70%. Il motivo principale è che
il contesto recente contiene spesso riferimenti al lavoro precedente: Luna ha
classificato 76 prompt come `explicit_past_reference`, quindi il gate diventa
quasi equivalente a “sempre recall”, ma più lento.

**Conclusione del supplemento:** la logica a tre esiti riduce molto i falsi
negativi, però non è un gate utile in produzione con questo prompt. Per ottenere
un risparmio serve distinguere meglio tra continuità della conversazione corrente
e bisogno di memoria persistente; questa distinzione non emerge dal solo testo.

## Test post-recall: classificare i risultati

È stata provata anche una strategia diversa: il recall avviene sempre, poi i
risultati vengono filtrati. Lo score usato è `scores.reranker`, perché lo score
globale client-side era presente solo in 2 risultati su 231.

Regole del test:

- reranker >= 0,8: iniezione diretta, senza classificatore;
- `high`: iniezione automatica;
- `medium`: proposta all'utente solo se non esiste già una memoria `high`;
- `low`: scarto;
- errore del classificatore: iniezione di tutto, quindi fail-open.

| Misura | Risultato |
|---|---:|
| Risultati totali | 231 |
| Bypass >= 0,8 | 18 (7,8%) |
| `high` dal classificatore | 118 (51,1%) |
| `medium` | 40 (17,3%) |
| `low` | 55 (23,8%) |
| Prompt con iniezione automatica | 65% |
| Prompt che chiederebbero davvero all'utente | 9% |
| Prompt senza memoria | 26% |
| Recall utili iniettati automaticamente | 95,7% |
| Recall utili disponibili anche su richiesta | 100% |
| Recall utili persi | 0 su 47 |
| Iniezioni automatiche inutili | 3 su 65 (4,6%) |
| Richieste all'utente utili | 2 su 9 |
| Classificatore p50 / p95 | 2.585 / 3.845 ms |
| Tempo totale medio | 4.609 ms |
| Baseline | 2.536 ms |

Questa strategia migliora nettamente la qualità del contesto: elimina il rumore
automatico nella maggior parte dei casi e non perde nessuno dei 47 recall utili.
È quindi molto migliore del gate sul prompt. Il punto debole è il canale
`medium`: senza la regola “non chiedere se esiste già un high” disturberebbe il
30% dei prompt; con la regola scende al 9%, ma solo 2 richieste su 9 risultano
veramente utili.

Il bypass a 0,8 è ragionevole ma non perfetto: ha coperto 9 prompt, di cui uno
era rumore secondo il giudice. Non va quindi interpretato come certezza; va
mantenuto solo se si accetta questo piccolo rischio.

### Confronto Luna, Mini e Nano

Lo stesso test è stato ripetuto con Mini e Nano, mantenendo Luna come giudice.

| Classificatore | Utili automatici | Utili disponibili | Persi | Rumore automatico | Prompt all'utente | p50 classificatore | Tempo medio |
|---|---:|---:|---:|---:|---:|---:|---:|
| `gpt-5.6-luna` | 95,7% | 100,0% | 0 | 4,6% | 9% | 2.585 ms | 4.609 ms |
| `gpt-4.1-mini` | 83,0% | 85,1% | 7 | 10,7% | 21% | 1.334 ms | 3.696 ms |
| `gpt-4.1-nano` | 66,0% | 83,0% | 8 | 22,6% | 27% | 1.059 ms | 3.404 ms |

Nano ha avuto anche 5 errori del classificatore, gestiti fail-open. Mini non ha
avuto errori, ma perde 7 recall utili e propone all'utente molti risultati quasi
sempre inutili. La latenza inferiore non compensa il calo di qualità.

**Valutazione:** se la priorità è la qualità, Luna è l'unico candidato valido.
Mini è un compromesso possibile solo accettando una perdita del 14,9% dei recall
utili. Nano è dominato: risparmia meno di 300 ms rispetto a Mini, ma produce più
rumore, più richieste e più falsi negativi. Per il canale medium raccomando di
non interrompere il turno: mostrare uno stub breve e lasciare che l'utente chieda
di espanderlo.

## Limiti del test

- Il campione è recente ma concentrato su Trinity; non rappresenta ogni progetto.
- La classificazione dell'utilità è automatica. Il giudice e uno dei gate usano
  entrambi Luna, quindi il risultato di Luna può essere favorito.
- Cinque recall sono andati in timeout; sono stati trattati come richiami senza
  risultato utile, coerentemente con ciò che l'hook avrebbe iniettato.
- Non è stato modificato né riavviato il servizio di produzione.
