# Reminder aggiornamenti — notebooklm-py

Sistema che **avvisa quando esce su PyPI una versione di `notebooklm-py` più recente di quella installata in `E:/AI/tools/notebooklm`**, così si può fare l'upgrade quando si vuole.

## Contesto

`notebooklm-py` è installato in **modalità exe-free** (flat-extract manuale) perché l'EDR aziendale blocca i file `.exe` scritti su disco. Il package è in `E:/AI/tools/notebooklm`, i dati e il launcher sono in `E:/AI/tools/notebooklm-data`.

Al 2026-06-28 la versione **0.8.0** (con supporto MCP via `fastmcp`) è installata da GitHub (branch `main`, commit `781dd4c9`), poiché su PyPI è ancora pubblicata la 0.7.2 senza MCP.

Quando 0.8.0 (o versioni successive) arriveranno su PyPI, questo scheduler darà l'alert.

## File in questa cartella

| File                        | Ruolo                                                                                                       |
| --------------------------- | ----------------------------------------------------------------------------------------------------------- |
| `nb-check.rb`               | **Il check vero.** Legge la versione dal dist-info locale, interroga PyPI, decide se c'è un update. Exit `0` / `10` / `1`. |
| `nb-check-scheduled.cmd`    | **Il ponte Windows→MSYS.** Lanciato da System Scheduler; imposta l'ambiente MSYS2.                         |
| `nb-check-scheduled.sh`     | **Il wrapper schedulato.** Esegue il check, scrive il log, crea/apre l'alert se c'è novità.                |
| `README.md`                 | Questo file.                                                                                                |

## Catena di esecuzione

```
System Scheduler (Splinterware)        ← innesco a orario programmato
        │
        ▼
nb-check-scheduled.cmd                  ← ponte: env MSYS2 + bash --noprofile --norc
        │
        ▼
nb-check-scheduled.sh                   ← cd root, log, gestione alert
        │  mise run nb-check
        ▼
mise run nb-check (.mise.toml)          ← fornisce Ruby + env TLS (SSL_CERT_FILE)
        │  ruby nb-check.rb
        ▼
nb-check.rb                             ← glob dist-info, PyPI query, exit 0/10
```

## Configurazione in System Scheduler

**Tab _Event_:**

| Campo       | Valore                                                                               |
| ----------- | ------------------------------------------------------------------------------------ |
| Event Type  | `Run Application`                                                                    |
| Title       | `notebooklm-py — check nuova versione`                                               |
| Application | `E:\AI\Claude\Trinity\scheduler\check_update_notebooklm\nb-check-scheduled.cmd`     |
| Parameters  | _(vuoto)_                                                                            |
| Working Dir | `E:\AI\Claude\Trinity`                                                               |
| State       | `Minimized` (o `Hidden`)                                                             |

**Tab _Schedule_:** cadenza **settimanale** consigliata.

## Uso manuale

```bash
mise run nb-check          # controlla (exit 10 = update disponibile)
```

> Lanciare via `mise run` per avere `SSL_CERT_FILE` corretto (proxy ENINET).

## Come aggiornare (quando arriva l'alert)

`notebooklm-py` è installato in modalità exe-free — **non usare `pip install`**.

1. Backup: `cp -r /e/AI/tools/notebooklm /e/AI/tools/notebooklm.bak-$(date +%Y%m%d)`
2. Download wheel da PyPI (o sorgente da GitHub `teng-lin/notebooklm-py`)
3. Estrai solo il package `notebooklm/` e il dist-info in `E:/AI/tools/notebooklm`
4. Verifica assenza exe: `find /e/AI/tools/notebooklm -iname '*.exe' -o -iname '*.dll'` (output vuoto)
5. Smoke test: `PYTHONPATH=E:/AI/tools/notebooklm python -m notebooklm.mcp --help`

Vedi Hindsight (`recall "notebooklm aggiornamento exe-free"`) per la procedura completa.

## Note tecniche

- **Baseline = versione installata**: `nb-check.rb` legge il METADATA dal dist-info con un glob (`notebooklm_py-*.dist-info/METADATA`) — funziona indipendentemente dalla versione installata.
- **TLS proxy ENINET**: `Net::HTTP` rispetta `SSL_CERT_FILE` impostato nell'`[env]` del `.mise.toml` (`C:/certs/cacert.pem`).
- **`mise` non nel PATH MSYS**: invocato col path assoluto `/e/msys64/home/Sphynx/.local/bin/mise.exe`.
- **`NB_NO_OPEN=1`**: disabilita l'apertura di Notepad (utile per i test da terminale).
- **`NB_FORCE_ALERT=1`**: forza la scrittura dell'alert anche se non c'è update (per testare il flusso).
