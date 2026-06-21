# Reminder aggiornamenti — hindsight-api / hindsight-api-slim

Sistema che **avvisa quando esce su PyPI una versione di `hindsight-api` o `hindsight-api-slim` più recente di quella installata**, così si può lanciare l'upgrade quando si vuole.

## Perché esiste (e in cosa differisce dal check del Control Plane)

Il server Python di Hindsight è installato/aggiornato dal task `install-hindsight` del `.mise.toml`, che fa semplicemente `pip install --upgrade hindsight-api`. **Non c'è nessun pin di versione.**

Per questo il check è diverso dal gemello `check_update_hindsight_control_plane`:

|                       | Control Plane (`cp-check`)            | API (`api-check`)                                       |
| --------------------- | ------------------------------------- | ------------------------------------------------------- |
| Baseline (soglia)     | versione **pinnata** nel `.mise.toml` | versione **installata** (letta da `importlib.metadata`) |
| Registry interrogato  | npm                                   | **PyPI**                                                |
| Pacchetti controllati | 1                                     | **2** (`hindsight-api` + `hindsight-api-slim`)          |

Siccome la baseline è la versione installata, la soglia **si alza da sola** dopo ogni upgrade: non c'è niente da aggiornare a mano in questi script.

## File in questa cartella

| File                      | Ruolo                                                                                                                                                                |
| ------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `api-check.rb`            | **Il check vero.** Ruby. Legge le versioni installate dal Python di mise, interroga PyPI, decide se c'è un update. Esce `0` (niente) / `10` (novità) / `1` (errore). |
| `api-check-scheduled.cmd` | **Il ponte Windows→MSYS.** Lanciato da System Scheduler; imposta `MSYSTEM=UCRT64` ed entra in una login shell.                                                       |
| `api-check-scheduled.sh`  | **Il wrapper schedulato.** Esegue il check, scrive il log e, se c'è novità, crea/apre il file di alert.                                                              |
| `README.md`               | Questo file.                                                                                                                                                         |

## Catena di esecuzione (automatica)

```
System Scheduler (Splinterware)        ← innesco a orario programmato
        │  lancia il campo "Application"
        ▼
api-check-scheduled.cmd                 ← ponte: set MSYSTEM=UCRT64 + login shell
        │
        ▼
api-check-scheduled.sh                  ← cd root, log, gestione alert
        │  mise run api-check
        ▼
mise run api-check (.mise.toml)         ← dà Ruby + Python giusti + env (TLS proxy)
        │  ruby api-check.rb
        ▼
api-check.rb                            ← confronto versioni, exit 0/10
```

L'exit code risale: `api-check.rb` esce `10` → `mise` lo propaga → lo `.sh` vede `10` e scrive l'alert.

## Configurazione in System Scheduler

**Tab _Event_:**

| Campo       | Valore                                                                              |
| ----------- | ----------------------------------------------------------------------------------- |
| Event Type  | `Run Application`                                                                   |
| Title       | `Hindsight API — check nuova versione`                                              |
| Application | `D:\AI\Claude\Trinity\scheduler\check_update_hindsight_api\api-check-scheduled.cmd` |
| Parameters  | _(vuoto)_                                                                           |
| Working Dir | `D:\AI\Claude\Trinity`                                                              |
| State       | `Minimized` (o `Hidden`)                                                            |

**Tab _Schedule_:** cadenza a piacere — consigliato **settimanale**. Il check è leggero (~5 s) e silenzioso quando non c'è nulla.

## Uso manuale (da terminale, nel progetto)

```bash
mise run api-check          # c'è una versione nuova da installare? (exit 10 = sì)
mise run install-hindsight  # aggiorna entrambi i pacchetti (pip install --upgrade)
```

> Va lanciato via `mise run`: serve l'`[env]` del `.mise.toml` (`SSL_CERT_FILE` / `REQUESTS_CA_BUNDLE`) per superare il MITM TLS del proxy aziendale, e il `_.path` che mette il Python di mise nel PATH (è quello da cui si legge la versione installata).

## Cosa succede quando esce una versione nuova

Quando `api-check` trova un pacchetto con `latest > installed`, lo `.sh` schedulato:

1. scrive `logs\api-update-ALERT.txt` con il dettaglio installed/latest per pacchetto e il comando per aggiornare;
2. apre quel file in primo piano (Notepad), così te ne accorgi.

Quando invece non c'è nulla da segnalare, **rimuove** un eventuale alert vecchio: la sola presenza di `api-update-ALERT.txt` è quindi un segnale affidabile.

File prodotti (nella cartella `logs\` del progetto):

- `logs\api-check-scheduled.log` — storico di ogni esecuzione (una riga per run, con JSON).
- `logs\api-update-ALERT.txt` — presente **solo** quando c'è una versione da installare.

## La lista "ignora" (di solito non serve)

Poiché la baseline è la versione installata, normalmente non serve nessuna lista. Ma se una release fosse rotta e volessi restare indietro **senza** essere riavvisato a ogni giro, puoi ignorarla:

```bash
API_IGNORE_VERSIONS="0.7.2,0.7.3" mise run api-check
```

La lista è globale (applicata a entrambi i pacchetti). Nello scheduler la imposteresti nell'`.cmd` con `set "API_IGNORE_VERSIONS=..."`.

## Note tecniche / gotcha

- **Baseline = versione installata**: `api-check.rb` interroga il Python di mise via `importlib.metadata` (istantaneo, non avvia il server). È lo stesso Python che `install-hindsight` aggiorna, perché `mise run` lo mette nel PATH.
- **Pacchetto non installato**: viene riportato con `"not_installed": true` e **non** conta come update (manca una baseline). Utile se in futuro togli `hindsight-api-slim`.
- **TLS dietro proxy ENINET**: `api-check.rb` usa `Net::HTTP`, che rispetta `SSL_CERT_FILE` (impostato nell'`[env]` del `.mise.toml` a `C:/certs/cacert.pem`). È ciò che fa passare la chiamata a PyPI attraverso il MITM del proxy.
- **`mise` non è nel PATH MSYS**: gli script lo invocano col path assoluto `C:\msys64\home\$USERNAME\.local\bin\mise.exe`.
- **Trust di mise**: `api-check-scheduled.sh` esegue `mise trust` prima di ogni `mise run` — idempotente, ri-fida dopo ogni modifica del `.mise.toml`. Non serve fare `mise trust` a mano.
- **`API_NO_OPEN=1`**: variabile per testare lo `.sh` senza far comparire Notepad.
- **Verifica nel contesto reale**: dopo aver creato l'evento, premi **▶ (Run)** in System Scheduler e controlla che compaia una riga fresca in `logs\api-check-scheduled.log`.
