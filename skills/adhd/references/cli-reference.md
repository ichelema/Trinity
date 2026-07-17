# CLI Reference — adhd-agent

**Status:** Active
**Last Updated:** 2026-07-17

Riferimento della CLI `adhd-agent` (v0.1.4): la stessa logica della skill
(diverge → score → prune → deepen) eseguita in autonomia via Claude Agent SDK,
con parametri formali e output strutturato. Upstream:
https://github.com/UditAkhourii/adhd (`documentation/api.md`).

## Invocazione in questo setup (mai `npm install -g`)

La CLI è installata **per-macchina, fuori dal repo** (root = env `ADHD_LIB`,
vedi README §10/§12.3) e si lancia SEMPRE dal wrapper versionato:

```bash
"$TRINITY_PLUGIN_DIR/scripts/bin/adhd" "<problema>" [flags]
```

- Il wrapper risolve Node a runtime via `run-node.sh` (mise → PATH): nessun
  path hardcoded, funziona su Windows/MSYS2 e Linux.
- Se esce con `[adhd] ADHD_LIB non definita`, la CLI non è installata su
  questa macchina (Windows: tarball npm scompattati a mano in
  `$ADHD_LIB/node_modules/`; Linux: `npm install adhd-agent` in una cartella
  locale) e va definita `ADHD_LIB` in `~/.claude/settings.json` → `env`.
- Da una sessione Claude Code: slash command `/trinity:adhd-cli "problema" [flags]`.
- Autenticazione: usa quella di `claude` già presente (Agent SDK con Claude
  Code vendorizzato) — nessuna API key da configurare, consuma la quota reale.

## Sintassi e flag

```bash
adhd "<problem>" [flags]
```

| Flag | Default | Effetto |
|---|---|---|
| `--frames N` | 5 | rami di divergenza paralleli (frame cognitivi diversi) |
| `--ideas N` | 6 | idee generate per ramo |
| `--top N` | 3 | quante idee approfondire nella fase focus |
| `--concurrency N` | 4 | massimo di chiamate LLM parallele |
| `--context PATH` | — | inietta un file come contesto (codice, vincoli, stack) |
| `--model NAME` | default SDK | override del modello (generatore) |
| `--critic-model NAME` | default SDK | override del modello per il critic pass |
| `--no-code-mode` | — | non orientare i frame verso l'ingegneria |
| `--json` | — | emette il `RunResult` come JSON machine-readable |
| `--quiet` | — | sopprime gli eventi di progresso |
| `-h, --help` | — | aiuto |

## Esempi

```bash
# Run standard
adhd "design a rate limiter that survives a leader election"

# Naming, run ridotta
adhd "name this function" --frames 3 --ideas 8 --top 2

# Con contesto di codice, output JSON su file
adhd "..." --context ./snippet.ts --json > out.json

# Smoke test economico (validato 2026-07-17: ~pochi token, modello Haiku)
adhd "problema di prova" --frames 1 --ideas 2 --top 1 \
  --model claude-haiku-4-5-20251001 --quiet
```

## Output

In modalità testo: `Wide set` (idee per frame con punteggi `[N V F]` =
novelty/viability/fit), `Converge — shortlist` (pick non ovvi motivati),
`Traps` (idee che sembrano buone ma non lo sono, col perché), `Focus`
(approfondimento dei top: sketch, rischio portante, primo passo concreto,
sub-idee), `Provocation`.

Con `--json` il `RunResult` contiene i campi principali:

| Campo | Contenuto |
|---|---|
| `shortlist` | le idee migliori con punteggi e motivazione |
| `deepened` | gli approfondimenti dei top-N (sketch, rischi, sub-idee) |
| `clusters` | la forma dello spazio ideativo (raggruppamenti tematici) |
| `traps` | le idee-trappola scartate con la ragione |

## Uso programmatico (Node/TS)

Per integrarla in un agent loop invece che da shell:

```ts
import { run, renderText } from "adhd-agent";
const result = await run({ problem, context, framesPerRun, topK });
```

Il modulo si risolve da `$ADHD_LIB/node_modules` (es. `NODE_PATH=$ADHD_LIB/node_modules`).

## Costi e tempi

Ogni run fa **più chiamate LLM reali** (≈ frames × 2 + critic): con i default
sono minuti di wall clock e quota non banale. Dai tool Bash usare timeout
≥ 300000 ms; per prove usare sempre la run ridotta dell'esempio sopra.
