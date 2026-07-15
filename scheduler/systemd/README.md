# Timer systemd (server Linux)

Equivalente Linux di System Scheduler + bridge `.cmd` di Windows: i timer
lanciano **direttamente** gli `*-scheduled.sh` (gia' bash portabile). Solo i
job sensati sul server:

| Unit | Cadenza | Job |
|---|---|---|
| `trinity-promote-scan` | dom 09:00 | scan+triage candidati promozione (parla con Hindsight locale) |
| `trinity-api-check` | dom 09:15 | nuove versioni `hindsight-api`/`-slim` su PyPI |
| `trinity-cp-check` | dom 09:30 | nuova versione Control Plane su npm vs pin `mise.toml` |

`nb-check`, `yt-check` e `nb-auth-refresh` restano su Windows: dipendono dalle
installazioni exe-free in `E:/AI/tools` e dai cookie del browser dell'utente.

## Installazione (unit utente, niente root)

```bash
# 1. se il clone NON e' in ~/ai/trinity, adatta TRINITY_PLUGIN_DIR ed ExecStart nei .service
mkdir -p ~/.config/systemd/user
cp ~/ai/trinity/scheduler/systemd/trinity-*.{service,timer} ~/.config/systemd/user/
systemctl --user daemon-reload
systemctl --user enable --now trinity-promote-scan.timer trinity-api-check.timer trinity-cp-check.timer

# 2. i timer utente girano anche senza sessione attiva solo con il linger:
loginctl enable-linger "$USER"
```

## Verifica e gestione

```bash
systemctl --user list-timers 'trinity-*'          # prossime esecuzioni
systemctl --user start trinity-promote-scan       # run manuale immediata
journalctl --user -u trinity-promote-scan -n 50   # log dell'ultima run
```

Gli alert NON aprono nulla a video (env `*_NO_OPEN=1` nelle unit): quando un
job trova qualcosa scrive il file `*-ALERT.txt` nella sua cartella sotto
`scheduler/` — la sola presenza del file e' il segnale (identico a Windows).
Exit code trattati come successo: `10` (novita'/candidati) e, per
promote-scan, `3` (server Hindsight giu': il job salta senza connettersi).
