# scheduler/notebooklm — auth refresh schedulato

Tiene viva la sessione di `notebooklm-py` rinnovando i cookie Google prima che
scadano, così non devi rifare la procedura cURL ogni volta.

## Cosa fa

`auth-refresh-scheduled.cmd` (ponte Windows→MSYS2) lancia
`auth-refresh-scheduled.sh`, che esegue:

```
/e/AI/tools/notebooklm-data/notebooklm auth refresh
```

tramite il launcher exe-free (Python di mise + `truststore` per il proxy Eni +
profilo cookie via `NOTEBOOKLM_HOME`). `auth refresh` rinnova `__Secure-1PSIDTS`
in place; la rigenerazione manuale dei cookie serve solo quando scade il cookie
di base `SID`.

## Configurazione in System Scheduler

| Campo             | Valore                                                                 |
| ----------------- | ---------------------------------------------------------------------- |
| Event Type        | Run Application                                                        |
| Application       | `E:\AI\Claude\Trinity\scheduler\notebooklm\auth-refresh-scheduled.cmd` |
| Parameters        | *(vuoto)*                                                              |
| Working Directory | `E:\AI\Claude\Trinity`                                                 |
| State             | Minimized o Hidden                                                     |
| Cadenza           | ogni 15–20 minuti (consigliata per profili idle)                       |

## Esiti e log

- Log: `scheduler/notebooklm/nb-auth-refresh-scheduled.log` (accanto allo script), una riga per run.
- Exit `0` = sessione rinnovata; rimuove un eventuale alert vecchio e azzera il contatore.
- Exit ≠ `0` = refresh fallito. Un singolo fallimento (glitch di rete) viene solo loggato.
  Dopo **3 fallimenti consecutivi** (`NB_FAIL_THRESHOLD`, cookie `SID` probabilmente
  scaduto) viene scritto e aperto `scheduler/notebooklm/nb-auth-ALERT.txt` con le istruzioni per
  rigenerare i cookie.
- Contatore fallimenti: `scheduler/notebooklm/nb-auth-refresh-fails.count`.

## Variabili

- `NB_FAIL_THRESHOLD` — fallimenti consecutivi prima dell'alert (default `3`).
- `NB_NO_OPEN=1` — non aprire Notepad sull'alert (per i test).
- `NB_LAUNCHER` — override del path del launcher notebooklm (default `/e/AI/tools/notebooklm-data/notebooklm`; usato nei test per simulare un fallimento).

## Test manuale

```bash
# run normale
bash scheduler/notebooklm/auth-refresh-scheduled.sh

# test senza aprire Notepad e con soglia bassa per forzare l'alert-path
NB_NO_OPEN=1 NB_FAIL_THRESHOLD=1 bash scheduler/notebooklm/auth-refresh-scheduled.sh
```
