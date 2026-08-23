# `hooks/hindsight/` — mappa della cartella

Sottosistema di memoria persistente Hindsight per Claude Code. Questa cartella contiene
**gli hook veri**, le **librerie condivise**, gli **script operativi**, i **tool di
manutenzione** e i **dati/artefatti**. Sotto, cosa è cosa e chi lo invoca.

## 🪝 Hook veri (entry-point, in cima a questa cartella)

Sono gli unici file invocati direttamente da Claude Code. Registrati in
`hooks/hooks.json` del plugin (NON spostarli senza aggiornare hooks.json).

| File                         | Evento Claude Code | Cosa fa                                                                                 |
| ---------------------------- | ------------------ | --------------------------------------------------------------------------------------- |
| `hindsight-recall.sh`        | UserPromptSubmit   | delega il lato retain al worker (`retain_at_prompt`: pickup dell'esito del gate del prompt precedente, consenso del retain pending, poi gate differito dell'entry accodata allo Stop precedente in un processo detached parallelo al recall, ICH-86), esegue recall fresco, filtra i risultati e inietta solo memorie high o autorizzate; fonde l'esito del gate all'emit (attesa max 6 s, altrimenti raccolto al prompt dopo) — un solo JSON in output |
| `hindsight-ensure-up.sh`     | SessionStart       | se il server :8888 è giù, lo avvia (`mise run start-hindsight`) e attende il boot; spawna la sentinella |
| `hindsight-mm-inject.sh`     | SessionStart       | (gated) inietta le "knowledge page" / mental model a inizio sessione                    |
| `hindsight-retain.sh`        | Stop               | puro bash: accoda il payload del hook in `$HS_CACHE_DIR/hs-retain-queue/` e risponde `{}` (nessuna valutazione qui) |
| `hindsight-sentinel.sh`      | — (detached)       | singleton spawnato da ensure-up: quando non resta alcun processo claude vivo drena la coda del retain (`hindsight-retain-worker.py --drain`), attende i retain in volo e ferma server + Postgres (sostituisce l'hook SessionEnd, sempre cancellato: issue #32712) |
| `hindsight-retain-worker.py` | —                  | worker del retain: tutta la logica retain del prompt (`retain_at_prompt()`: pickup + consenso + lancio del gate differito, importato da `hindsight-recall.sh`), `--queued <session>` come processo detached lanciato da `retain_at_prompt` (valuta l'entry della sessione e scrive l'outbox `hs-retain-queue/<session>.out.json`), `--drain` dalla sentinella (non è un hook a sé) |

## 📁 `lib/` — libreria condivisa

Moduli/config importati per nome da quasi tutti gli script (via `sys.path`). Il loro
posizionamento è il vincolo centrale: chi li importa deve puntare a `lib/`.

| File                      | Ruolo                                                                            |
| ------------------------- | -------------------------------------------------------------------------------- |
| `hindsight_config.py`     | loader della config a strati: DEFAULTS → `<plugin_root>/hindsight.config.json` → `<progetto>/hindsight.config.json` (override) → env |
| `hindsight_debug.py`      | logging strutturato JSONL su `logs/hindsight-debug.log`                          |
| `hindsight_file_lock.py`  | lock interprocesso best-effort su file (`flock`/`msvcrt`), condiviso da retain worker e recall filter |
| `hindsight_recall_lib.py` | costruzione del payload di recall                                                |
| `hindsight_recall_filter.py` | filtro Luna low/medium/high, consenso naturale e pending per-sessione          |

> `hindsight.config.json` (i parametri: api_url, budget, tag, mental model, …) vive nella **root del plugin**, non più in `lib/`. Un progetto può sovrascrivere singole chiavi con un proprio `hindsight.config.json` nella sua root (merge a strati).

## Filtro post-recall e consenso

Ogni prompt normale esegue un recall fresco: non esiste una cache dei risultati o delle classificazioni.
I risultati con `scores.reranker >= 0.8` sono iniettati direttamente; gli altri sono
classificati in una sola chiamata a `gpt-5.6-luna`:

- `high`: iniezione automatica;
- `low`: scarto;
- `medium`: se non esiste alcun high, salvataggio temporaneo isolato per `session_id + cwd`
  e domanda “Ho delle memorie che potrebbero essere utili, le vuoi usare?”. Un consenso naturale
  nel turno successivo le consuma e inietta una sola volta; qualsiasi altro prompt le elimina.

Il classificatore è fail-open: chiave mancante, timeout o output invalido iniettano i risultati
originali. `recall_debug_in_context: true` sostituisce il blocco normale con una diagnostica che
mostra route, conteggi e testo completo delle sole memorie effettivamente iniettate.

## 📁 `ops/` — script operativi e utility

Script non-hook, eseguiti a mano o richiamati da altri (hook/mise/scheduler).

| File                         | Chi lo chiama                                                     | Cosa fa                                                      |
| ---------------------------- | ----------------------------------------------------------------- | ------------------------------------------------------------ |
| `hindsight-stop-services.sh` | `hindsight-sentinel.sh`, `mise run stop-hindsight`                | ferma server MCP + Postgres embedded                         |
| `kill-port.sh`               | `mise` (control-plane/dashboard)                                  | uccide il processo su una porta (via `Get-NetTCPConnection`) |
| `hindsight-mental-models.sh` | manuale, `tools/hindsight-check.sh`                               | seed/list/show/refresh delle knowledge page                  |
| `hindsight-set-mission.sh`   | manuale                                                           | imposta retain/reflect mission sul bank                      |
| `hindsight-reflect.sh`       | slash-command `/reflect` (fallback)                               | sintesi strategica via `reflect`                             |

## 📁 `tools/` — manutenzione manuale

| File                        | Cosa fa                                                                                                                                                            |
| --------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| `hindsight-check.sh`        | **diagnostica live** del setup (server, endpoint, hook, mental model, debug log). Uso: `bash hooks/hindsight/tools/hindsight-check.sh` |
| `hindsight_export.py`       | esporta i documenti del bank in JSON (output in `data/exports/`)                                                                                                   |
| `hindsight_import.py`       | re-importa/re-retain i documenti (es. dopo cambio modello embedding)                                                                                               |

## 📁 `data/` — artefatti

Vuota di default (non versionata): accoglie gli `exports/` di `tools/hindsight_export.py`.
I vecchi dump SQL del lab non sono stati migrati (dismessi nella fusione del 2026-06-12).

## 📁 altre sottocartelle

- `benchmark/` — corpora e script di benchmark embedding/reranker (task `mise embed-bench`, `rerank-bench`).

Per analizzare `hindsight-debug.log` (JSONL) basta una riga di Nushell:

```bash
nu -c "open logs/hindsight-debug.log | lines | each { from json } | where event == 'recall'"
```

## Convenzione di risoluzione path

Ogni script trova i fratelli **relativamente a sé stesso**, mai con path assoluti cablati:

- `.sh`: `HOOKS_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"`, poi `sys.path` punta a `$HOOKS_DIR/lib` (hook in cima) o `$HOOKS_DIR/../lib` (script in `ops/`/`tools/`).
- `.py`: `sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "lib"))` (o `"..","lib"` dalle sottocartelle).

Spostando un file, aggiornare **solo** la sua riga di risoluzione path e i chiamanti esterni
(`hooks/hooks.json`, `mise.toml`, `scheduler/`, slash-command). Poi verificare con
`bash hooks/hindsight/tools/hindsight-check.sh`.
