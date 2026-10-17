# Ponytail Gain

Mostra questo scoreboard quando viene invocato. One-shot: non cambiare modalità, non scrivere
file flag e non persistere niente.

Le cifre sono il benchmark agentico pubblicato di Ponytail 5: Claude Code headless (Opus 5.5,
effort di default) su 39 task (ticket di feature in un vero repo FastAPI + React, bug fix, casi di
sicurezza e privacy, piccole app), 5 run ciascuno, contro lo stesso agente senza la skill. 18 task
hanno controlli nascosti di correttezza e sicurezza. Ogni cifra è la media geometrica delle
mediane per task. Sono misurate, non calcolate dal repo corrente.
Fonte: `benchmarks/results/2026-10-07-agentic.md` e README del progetto upstream,
https://github.com/DietrichGebert/ponytail.

## Scoreboard

Rendi barre ASCII semplici. La lunghezza della barra mostra ponytail come quota della baseline
senza skill; l'etichetta porta la cifra esatta:

```
  ponytail gain           benchmark · 39 tasks × 5 runs · Opus 5.5

  no-skill        ████████████████████  100%
  Lines of code   █████████···········   47%   ▼ 53%
  Output tokens   ███████████·········   55%   ▼ 45%
  Cost            ███████████████·····   74%   ▼ 26%
  Time            ████████████········   59%   ▼ 41%
  Hidden checks passed   97%  (no-skill 96%)
  Tests where the logic needs one   98%  (no-skill 68%)

  This repo:  /trinity:ponytail:ponytail-debt  (shortcuts you deferred)
              /trinity:ponytail:ponytail-audit (what's still cuttable)
```

## Confine di onestà

Queste sono medie di benchmark, non questo repo. Non stampare una cifra di risparmio per-repo
("hai risparmiato X righe/token qui"): la versione mai costruita non è mai stata scritta, quindi
non c'è una baseline reale da cui sottrarre in un repo live. Le uniche cifre reali per-repo
vengono da `/trinity:ponytail:ponytail-debt` (un ledger contato), e questa card punta lì invece
di inventarne una.

## Confini

Display one-shot. Non modifica niente, non cambia alcuna modalità.
"stop ponytail" o "normal mode": ripristina.
