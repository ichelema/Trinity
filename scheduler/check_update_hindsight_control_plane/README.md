# Reminder aggiornamenti — Hindsight Control Plane

Sistema che **avvisa quando esce una versione nuova del Control Plane di Hindsight**, così si può valutare se alzare il pin nel `.mise.toml`.

## Perché esiste

Il Control Plane (Web UI di Hindsight, `@vectorize-io/hindsight-control-plane`) è avviato dal task `control-plane` nel `.mise.toml`, **pinnato a `0.8.2`** (dal 2026-06-12).

Storia del pin: dalle `0.7.0` in poi `/` entrava in un loop di redirect infinito (`ERR_TOO_MANY_REDIRECTS`), per cui il pin è rimasto a lungo bloccato a `0.6.2`. Il 2026-06-12 è emersa la root cause: non un bug i18n in sé ma un **origin-mismatch di Next.js standalone** ([vercel/next.js#91844](https://github.com/vercel/next.js/issues/91844)) — `NextURL` normalizza `127.0.0.1` in `localhost` nel rewrite del middleware next-intl, mentre il router usa l'hostname di bind, quindi il rewrite interno viene trattato come esterno e va in loop. **Workaround**: bind su `localhost` invece di `127.0.0.1` (task `control-plane` e `cp-redirect-test.sh`). Con quello la `0.8.2` funziona.

Vogliamo comunque accorgerci **quando upstream pubblica una versione nuova** per valutarla (e, quando il bug Next sarà fixato upstream, poter eventualmente togliere il workaround). Questo sistema controlla npm periodicamente e avvisa solo quando vale la pena.

## File in questa cartella

| File                     | Ruolo                                                                                                                                                                   |
| ------------------------ | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `cp-check.rb`            | **Il check vero.** Ruby. Legge il pin dal `.mise.toml`, interroga npm, decide se c'è una versione nuova da segnalare. Esce `0` (niente) / `10` (novità) / `1` (errore). |
| `cp-redirect-test.sh`    | **Il test del bug.** Avvia una versione del Control Plane su una porta usa-e-getta (9998) e verifica se `/` va in loop o raggiunge `/dashboard`.                        |
| `cp-check-scheduled.cmd` | **Il ponte Windows→MSYS.** Lanciato da System Scheduler; imposta `MSYSTEM=UCRT64` ed entra in bash.                                                                     |
| `cp-check-scheduled.sh`  | **Il wrapper schedulato.** Esegue il check, scrive il log e, se c'è novità, crea/apre il file di alert.                                                                 |
| `README.md`              | Questo file.                                                                                                                                                            |

> `kill-port.sh` (usato da `cp-redirect-test.sh`) **non** è qui: vive in `hooks/hindsight/ops/` di questo stesso repo. Lo script usa `$TRINITY_PLUGIN_DIR` se presente, con fallback relativo alla root del repo (`../..`).

## Catena di esecuzione (automatica)

```
System Scheduler (Splinterware)        ← innesco a orario programmato
        │  lancia il campo "Application"
        ▼
cp-check-scheduled.cmd                  ← ponte: set MSYSTEM=UCRT64 + bash -lc
        │
        ▼
cp-check-scheduled.sh                   ← cd root, log, gestione alert
        │  mise run cp-check
        ▼
mise run cp-check (.mise.toml)          ← dà Ruby giusto + env (TLS proxy)
        │  ruby cp-check.rb
        ▼
cp-check.rb                             ← confronto versioni, exit 0/10
```

L'exit code risale: `cp-check.rb` esce `10` → `mise` lo propaga → lo `.sh` vede `10` e scrive l'alert.

## Configurazione in System Scheduler

**Tab _Event_:**

| Campo       | Valore                                                                                    |
| ----------- | ----------------------------------------------------------------------------------------- |
| Event Type  | `Run Application`                                                                         |
| Title       | `Hindsight Control Plane — check nuova versione`                                          |
| Application | `D:\AI\Claude\Trinity\scheduler\check_update_hindsight_control_plane\cp-check-scheduled.cmd` |
| Parameters  | _(vuoto)_                                                                                 |
| Working Dir | `D:\AI\Claude\Trinity`                                                                       |
| State       | `Minimized` (o `Hidden`)                                                                  |

**Tab _Schedule_:** cadenza a piacere — consigliato **settimanale** (es. lunedì 9:00). Il check è leggero (~5 s) e silenzioso quando non c'è nulla, quindi anche giornaliero va bene.

## Uso manuale (da terminale, nel progetto)

```bash
mise run cp-check                          # c'è una versione nuova da valutare? (exit 10 = sì)
VERSION=0.7.1 mise run cp-redirect-test    # quella versione ha ancora il bug? (sostituisci la versione)
```

> Vanno lanciati via `mise run`: serve l'`[env]` del `.mise.toml` (`SSL_CERT_FILE` / `NODE_EXTRA_CA_CERTS`) per superare il MITM TLS del proxy aziendale.

## Cosa succede quando esce una versione nuova

Quando `cp-check` trova una versione **> pin** (al netto delle ignorate), lo `.sh` schedulato:

1. scrive `logs\cp-update-ALERT.txt` con versione pinnata, ultima su npm e il comando per testarla;
2. apre quel file in primo piano (Notepad), così te ne accorgi.

Quando invece non c'è nulla da segnalare, **rimuove** un eventuale alert vecchio: la sola presenza di `cp-update-ALERT.txt` è quindi un segnale affidabile.

File prodotti (nella cartella `logs\` del progetto):

- `logs\cp-check-scheduled.log` — storico di ogni esecuzione (una riga per run, con JSON).
- `logs\cp-update-ALERT.txt` — presente **solo** quando c'è una versione da valutare.

## La soglia "intelligente" (perché non spamma)

`cp-check` **non** confronta col solo pin, ma con `max(pin, versioni-ignorate)`.

`IGNORED_VERSIONS` è **vuota** dal 2026-06-12 (pin alzato a `0.8.2`, le vecchie bocciate sono sotto soglia da sole): torna utile se una futura versione `> pin` risultasse rotta anche col workaround — la si aggiunge lì e non viene più segnalata a ogni giro.

Override della lista a runtime:

```bash
CP_IGNORE_VERSIONS="0.7.0,0.7.2" mise run cp-check
```

## Quando esce una versione nuova — cosa fare

1. Ricevi l'alert (es. `0.9.0`).
2. Testa: `VERSION=0.9.0 mise run cp-redirect-test` (il test usa già il bind `localhost` come la produzione).
   - `VERDETTO: OK` → procedi.
   - `VERDETTO: ANCORA ROTTO` → aggiungi quella versione a `IGNORED_VERSIONS` in `cp-check.rb` e aspetta la prossima.
3. Se OK, aggiorna il pin nel `.mise.toml`, task `control-plane`: la riga `... hindsight-control-plane@0.9.0 ...` e il commento sopra.
4. Una volta alzato il pin, puoi **svuotare** `IGNORED_VERSIONS` (la soglia si alza da sola col nuovo pin).

## Note tecniche / gotcha

- **Ponte Windows→MSYS**: System Scheduler è un'app Windows e non conosce MSYS2. Il `.cmd` imposta `MSYSTEM=UCRT64` + `CHERE_INVOKING=1` e invoca `bash -lc`; il flag `-l` (login shell) ricostruisce il `PATH` UCRT64 da `/etc/profile`. Senza questo, Ruby/mise non sarebbero nel path.
- **`mise` non è nel PATH MSYS**: gli script lo invocano col path assoluto `C:\msys64\home\EN27553\.local\bin\mise.exe`.
- **Trust di mise**: mise rifiuta di parsare un `.mise.toml` non "trusted" (errore `not trusted` / `error parsing config file`, `rc=1`). Il trust è legato al contesto utente: da un terminale/scheduler Windows "nudo" il config risulta non fidato anche se lo è in una sessione interattiva. Per questo `cp-check-scheduled.sh` esegue `mise trust "$PROJ/.mise.toml"` prima di ogni `mise run` — idempotente, e ri-fida automaticamente dopo ogni modifica del `.mise.toml` (che altrimenti invaliderebbe il trust). Non serve quindi fare `mise trust` a mano.
- **TLS dietro proxy ENINET**: `cp-check.rb` usa `Net::HTTP`, che rispetta `SSL_CERT_FILE` (impostato nell'`[env]` del `.mise.toml` a `C:/certs/cacert.pem`). È ciò che fa passare la chiamata a npm attraverso il MITM del proxy.
- **`CP_NO_OPEN=1`**: variabile per testare lo `.sh` senza far comparire Notepad.
- **Verifica nel contesto reale**: dopo aver creato l'evento, premi **▶ (Run)** in System Scheduler e controlla che compaia una riga fresca in `logs\cp-check-scheduled.log`. È la prova che il ponte funziona anche da scheduler (non solo da shell interattiva).
