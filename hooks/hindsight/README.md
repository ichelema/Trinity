# `hooks/hindsight/` — mappa della cartella

Sottosistema di memoria persistente Hindsight per Claude Code. Questa cartella contiene
**gli hook veri**, le **librerie condivise**, gli **script operativi**, i **tool di
manutenzione** e i **dati/artefatti**. Sotto, cosa è cosa e chi lo invoca.

## 🪝 Hook veri (entry-point, in cima a questa cartella)

Sono gli unici file invocati direttamente da Claude Code. Registrati in
`hooks/hooks.json` del plugin (NON spostarli senza aggiornare hooks.json).

| File                         | Evento Claude Code | Cosa fa                                                                                 |
| ---------------------------- | ------------------ | --------------------------------------------------------------------------------------- |
| `hindsight-recall.sh`        | UserPromptSubmit   | inietta come `additionalContext` le memorie rilevanti al prompt (con cache client-side) |
| `hindsight-ensure-up.sh`     | SessionStart       | se il server :8888 è giù, lo avvia (`mise run start-hindsight`) e attende il boot       |
| `hindsight-mm-inject.sh`     | SessionStart       | (gated) inietta le "knowledge page" / mental model a inizio sessione                    |
| `hindsight-retain.sh`        | Stop               | lancia il worker async che memorizza la coda della sessione                             |
| `hindsight-shutdown.sh`      | SessionEnd         | retain finale forzato, poi ferma server + Postgres (via `ops/`)                         |
| `hindsight-retain-worker.py` | —                  | worker chiamato da `hindsight-retain.sh` (non è un hook a sé)                           |

## 📁 `lib/` — libreria condivisa

Moduli/config importati per nome da quasi tutti gli script (via `sys.path`). Il loro
posizionamento è il vincolo centrale: chi li importa deve puntare a `lib/`.

| File                      | Ruolo                                                                            |
| ------------------------- | -------------------------------------------------------------------------------- |
| `hindsight_config.py`     | loader della config a strati: DEFAULTS → `<plugin_root>/hindsight.config.json` → `<progetto>/hindsight.config.json` (override) → env |
| `hindsight_debug.py`      | logging strutturato JSONL su `logs/hindsight-debug.log`                          |
| `hindsight_recall_lib.py` | costruzione del payload di recall                                                |

> `hindsight.config.json` (i parametri: api_url, budget, tag, mental model, …) vive nella **root del plugin**, non più in `lib/`. Un progetto può sovrascrivere singole chiavi con un proprio `hindsight.config.json` nella sua root (merge a strati).

## 📁 `ops/` — script operativi e utility

Script non-hook, eseguiti a mano o richiamati da altri (hook/mise/scheduler).

| File                         | Chi lo chiama                                                     | Cosa fa                                                      |
| ---------------------------- | ----------------------------------------------------------------- | ------------------------------------------------------------ |
| `hindsight-stop-services.sh` | `hindsight-shutdown.sh`, `mise run stop-hindsight`                | ferma server MCP + Postgres embedded                         |
| `kill-port.sh`               | `mise` (control-plane/dashboard), `scheduler/cp-redirect-test.sh` | uccide il processo su una porta (via `Get-NetTCPConnection`) |
| `hindsight-mental-models.sh` | manuale, `tools/hindsight-check.sh`                               | seed/list/show/refresh delle knowledge page                  |
| `hindsight-set-mission.sh`   | manuale                                                           | imposta retain/reflect mission sul bank                      |
| `hindsight-reflect.sh`       | slash-command `/reflect` (fallback)                               | sintesi strategica via `reflect`                             |

## 📁 `tools/` — manutenzione manuale

| File                        | Cosa fa                                                                                                                                                            |
| --------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| `hindsight-check.sh`        | **suite di diagnostica** dell'intero setup (server, endpoint, hook, config, mental model, debug log). Uso: `bash hooks/hindsight/tools/hindsight-check.sh` |
| `hindsight_export.py`       | esporta i documenti del bank in JSON (output in `data/exports/`)                                                                                                   |
| `hindsight_import.py`       | re-importa/re-retain i documenti (es. dopo cambio modello embedding)                                                                                               |
| `hindsight-recall-bench.sh` | benchmark trasparente di rilevanza del recall                                                                                                                      |

## 📁 `data/` — artefatti

Vuota di default (non versionata): accoglie gli `exports/` di `tools/hindsight_export.py`.
I vecchi dump SQL del lab non sono stati migrati (dismessi nella fusione del 2026-06-12).

## 📁 altre sottocartelle

- `benchmark/` — corpora e script di benchmark embedding/reranker (task `mise embed-bench`, `rerank-bench`).
- `hindsight-dashboard/` — web app Ruby/Roda per analizzare `hindsight-debug.log` (task `mise dashboard`).

## Convenzione di risoluzione path

Ogni script trova i fratelli **relativamente a sé stesso**, mai con path assoluti cablati:

- `.sh`: `HOOKS_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"`, poi `sys.path` punta a `$HOOKS_DIR/lib` (hook in cima) o `$HOOKS_DIR/../lib` (script in `ops/`/`tools/`).
- `.py`: `sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "lib"))` (o `"..","lib"` dalle sottocartelle).

Spostando un file, aggiornare **solo** la sua riga di risoluzione path e i chiamanti esterni
(`hooks/hooks.json`, `mise.toml`, `scheduler/`, slash-command). Poi verificare con
`bash hooks/hindsight/tools/hindsight-check.sh`.
