# promote_scan — job settimanale del funnel di promozione multi-bank

Scansiona i bank Hindsight di progetto e fa il triage LLM (gpt-4.1-nano) dei
fatti candidati alla promozione sul bank core. **Non promuove mai nulla**: il
move è riservato a `/trinity:promote` con review umana. Se ci sono candidati
apre un alert (notepad) che rimanda al comando.

## Catena di esecuzione (pattern cp-check)

```
System Scheduler (Splinterware, settimanale)
  └─ promote-scan-scheduled.cmd      ponte Windows → MSYS2 (env UCRT64 + HOME)
       └─ promote-scan-scheduled.sh  wrapper: server-check, log, alert, exit code
            └─ mise run promote-scan
                 └─ python hooks/hindsight/ops/hindsight-promote.py --triage
```

I verdetti del triage sono cachati in `logs/promote-state.json`: le run
successive interrogano il modello solo sui documenti nuovi.

## Exit code

| Codice | Significato |
|---|---|
| 0 | nessun candidato |
| 10 | candidati trovati (alert aperto, report in `logs/promote-candidates.json`) |
| 3 | server Hindsight giù → skip con log (nessun avvio da cron) |
| altro | errore (vedi `scheduler/promote_scan/promote-scan-scheduled.log`) |

## Registrazione in System Scheduler (manuale, GUI)

- **Application**: `E:\AI\Claude\Trinity\scheduler\promote_scan\promote-scan-scheduled.cmd`
- **Parameters**: vuoto
- **Working Dir**: `E:\AI\Claude\Trinity`
- **State**: Minimized o Hidden
- **Schedule**: settimanale

## Test manuale

```bash
PROMOTE_NO_OPEN=1 bash scheduler/promote_scan/promote-scan-scheduled.sh; echo "rc=$?"
```
