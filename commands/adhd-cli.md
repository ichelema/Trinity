---
description: Lancia la CLI adhd-agent (ideazione divergente parallela) con parametri formali
argument-hint: "<problema>" [--frames N] [--ideas N] [--top N] [--context PATH] [--json]
allowed-tools: Bash(bash:*), Bash(*/scripts/bin/adhd:*)
---
Esegui col tuo Bash tool la CLI `adhd` passando gli argomenti dell'utente
così come sono (problema tra virgolette + eventuali flag):

```bash
"$TRINITY_PLUGIN_DIR/scripts/bin/adhd" $ARGUMENTS
```

Note operative:
- Ogni run lancia più chiamate LLM tramite l'Agent SDK: usa un timeout di
  almeno 5 minuti (300000 ms).
- Se il wrapper fallisce con "ADHD_LIB non definita", la CLI non è installata
  su questa macchina: serve l'installazione per-macchina dei pacchetti npm e
  la variabile ADHD_LIB in ~/.claude/settings.json (env).
- Se l'utente non passa flag, non aggiungerne.
- Al termine riporta l'output della CLI (shortlist, idee approfondite,
  trappole) in forma leggibile; se c'è `--json`, riassumi i campi
  `shortlist` e `deepened` e indica dove è finito il JSON completo.
- Flag disponibili: --frames N, --ideas N, --top N, --concurrency N,
  --context PATH, --model NAME, --no-code-mode, --json, --quiet.
