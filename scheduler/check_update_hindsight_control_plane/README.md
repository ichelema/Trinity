# Reminder aggiornamenti — Hindsight Control Plane

Sistema che **avvisa (una volta sola) quando esce su npm una nuova release del
Control Plane di Hindsight**, così puoi leggerne i breaking changes e valutare
l'allineamento dell'API.

## Perché esiste

Il Control Plane (Web UI di Hindsight, `@vectorize-io/hindsight-control-plane`)
è avviato dal task `control-plane` nel `mise.toml` via `npx --yes` **senza pin**
(rimosso il 2026-07-31, commit 5723fd0): al prossimo avvio `npx` scarica da solo
l'ultima versione. Non c'è quindi nulla da aggiornare a mano — ma conviene
*accorgersi* che una release nuova esiste, per leggerne i breaking changes e
valutare `mise run install-hindsight` per allineare `hindsight-api-slim`
(un CP più nuovo dell'API può chiamare endpoint che l'API non espone ancora).

La baseline è l'**ultima release vista**, salvata in `cp-last-seen.state`
accanto allo script: si auto-avanza a ogni rilevamento, quindi ogni release
viene segnalata una volta sola. Al primo run (stato assente) fa un seed
silenzioso alla latest, senza alert.

## File in questa cartella

| File | Ruolo |
| ---- | ----- |
| `cp-check.rb` | **Il check vero.** Ruby. Confronta l'ultima su npm con l'ultima vista (`cp-last-seen.state`). Esce `0` (niente) / `10` (novità) / `1` (errore). |
| `cp-check-scheduled.cmd` | **Il ponte Windows→MSYS.** Lanciato da System Scheduler; imposta l'ambiente MSYS2 ed esegue lo script con `bash --noprofile --norc`. |
| `cp-check-scheduled.sh` | **Il wrapper schedulato.** Esegue il check, scrive il log e, se c'è novità, crea/apre il file di alert. |
| `README.md` | Questo file. |

## Catena di esecuzione (automatica)

```
System Scheduler (Splinterware)        ← innesco a orario programmato
        │  lancia il campo "Application"
        ▼
cp-check-scheduled.cmd                  ← ponte: env MSYS2 + bash --noprofile --norc
        │
        ▼
cp-check-scheduled.sh                   ← cd root, log, gestione alert
        │  mise run cp-check
        ▼
mise run cp-check (mise.toml)           ← dà Ruby giusto + env (TLS proxy)
        │  ruby cp-check.rb
        ▼
cp-check.rb                             ← confronto ultima vista vs ultima npm, exit 0/10
```

L'exit code risale: `cp-check.rb` esce `10` → `mise` lo propaga → lo `.sh` vede `10` e scrive l'alert.

## Configurazione in System Scheduler

| Campo | Valore |
| ----- | ------ |
| Event Type | `Run Application` |
| Application | `E:\AI\Claude\Trinity\scheduler\check_update_hindsight_control_plane\cp-check-scheduled.cmd` |
| Parameters | *(vuoto)* |
| Working Dir | `E:\AI\Claude\Trinity` |
| State | `Minimized` (o `Hidden`) |
| Schedule | settimanale (il check è leggero e silenzioso quando non c'è nulla) |

## Uso manuale (da terminale, nel progetto)

```bash
mise run cp-check          # c'è una versione nuova da valutare? (exit 10 = sì)
```

> Va lanciato via `mise run`: serve l'`[env]` del `mise.toml` (`SSL_CERT_FILE` /
> `NODE_EXTRA_CA_CERTS`) per superare il MITM TLS del proxy aziendale.

## Cosa succede quando esce una versione nuova

Quando `cp-check` trova `latest > ultima vista`, lo `.sh` schedulato:

1. scrive l'alert con ultima vista, ultima su npm e i prossimi passi
   (breaking changes + eventuale `mise run install-hindsight`);
2. apre quel file in primo piano (Notepad).

Lo stato si auto-avanza al rilevamento, quindi il run successivo esce `0` e
**rimuove** l'alert: la notifica vera è il Notepad in primo piano, il file è
solo traccia. Non c'è nulla da aggiornare a mano per il CP (npx è sempre-latest).

File prodotti (accanto a questo script):

- `cp-check-scheduled.log` — storico di ogni run (una riga, con JSON).
- `cp-update-ALERT.txt` — presente tra un rilevamento e il run successivo.
- `cp-last-seen.state` — ultima release vista (baseline del confronto).

Sono esclusi da git nel `.gitignore` principale del repo.

## Note tecniche / gotcha

- **Avvio robusto**: il `.cmd` imposta esplicitamente `TRINITY_PLUGIN_DIR` e il
  PATH di MSYS, ed esegue lo script con `bash --noprofile --norc` (niente config
  utente, che altrimenti farebbe partire zsh interattivo invece dello script).
- **`mise` non è nel PATH MSYS**: lo script lo invoca col path assoluto
  `/e/msys64/home/Sphynx/.local/bin/mise.exe` (fallback se non in PATH).
- **Trust di mise**: `cp-check-scheduled.sh` esegue `mise trust` prima di ogni
  `mise run` — idempotente, ri-fida dopo ogni modifica del `mise.toml`.
- **TLS dietro proxy ENINET**: `cp-check.rb` usa `Net::HTTP`, che rispetta
  `SSL_CERT_FILE` (impostato nell'`[env]` del `mise.toml`): fa passare la
  chiamata a npm attraverso il MITM del proxy.
- **`CP_NO_OPEN=1`**: variabile per testare lo `.sh` senza far comparire Notepad.
