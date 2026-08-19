# Ponytail Gain

Mostra questo scoreboard quando viene invocato. One-shot: NON cambiare modalità, scrivere
file flag o persistere qualcosa.

Le cifre sono le mediane dei benchmark pubblicati (5 task quotidiani: email
validator, debounce, CSV sum, countdown timer, rate limiter; tre modelli:
Haiku, Sonnet, Opus). Sono misurate, non calcolate dal repo corrente.
Source: `benchmarks/` e il README.

## Scoreboard

Rendi barre ASCII semplici. La lunghezza della barra mostra l'intervallo misurato; l'etichetta
porta la cifra esatta:

```
  ponytail gain                     benchmark median · 5 tasks · 3 models

  Lines of code   no-skill  ████████████████████  100%
                  ponytail  ██▌·················    6–20%   ▼ 80–94%
  Cost            no-skill  ████████████████████  100%
                  ponytail  █████▌··············   23–53%  ▼ 47–77%
  Speed           ponytail  ▸ 3–6× faster

  This repo:  /trinity:ponytail:ponytail-debt  (shortcuts you deferred)
              /trinity:ponytail:ponytail-audit (what's still cuttable)
```

## Confine di onestà

Queste sono mediane dei benchmark, non questo repo. NON stampare MAI una cifra di risparmio
per-repo ("hai risparmiato X righe/token qui"): la versione mai costruita non è mai stata
scritta, quindi non c'è una baseline reale da cui sottrarre in un repo live. Le
uniche cifre reali per-repo vengono da `/trinity:ponytail:ponytail-debt` (un ledger contato), e
questa card punta lì invece di inventarne una.

## Confini

Display one-shot. Non modifica niente, non cambia alcuna modalità.
"stop ponytail" o "normal mode": ripristina.
