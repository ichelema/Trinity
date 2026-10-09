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
| `hindsight-failcheck.sh`     | UserPromptSubmit   | segnala via additionalContext i retain falliti in silenzio lato server (`GET .../operations?status=failed`: l'estrazione fatti è async e può fallire dopo l'accepted), i fallimenti locali del retain e la degradazione del reranker; de-dup via state file, una notifica per evento; indipendente da `recall_enabled` |
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
| `hindsight_multibank.py`  | recall multi-bank: fan-out parallelo sui bank + fusione con rerank globale (Voyage) |
| `hindsight_recall_lib.py` | costruzione del payload di recall                                                |
| `hindsight_recall_filter.py` | filtro Luna low/medium/high, consenso naturale e pending per-sessione          |
| `hindsight_recorder.py`   | recorder dei golden per il porting (ICH-173): con `HINDSIGHT_RECORD=1` ogni hook Python e il worker scrivono un record JSON in `$HS_CACHE_DIR/hs-golden/` (vedi «Recorder dei golden») |
| `hindsight_retain_gate.py` | gate semantico pre-retain (ICH-67): decide retain/skip/uncertain sulla finestra del turno, con dedup contro i candidati già nel bank; segnala anche i candidati smentiti dalla finestra (ICH-152): il worker chiede «Ritiro la memoria contraddetta?» e solo dopo il «sì» li ritira (PATCH `state=invalidated`, reversibile; pending in `$HS_CACHE_DIR/hs-invalidate-pending/`, mai nel drain); se il turno ha già la domanda del retain, la domanda di ritiro slitta al primo turno libero (ICH-166) |
| `hindsight_secrets.py`    | pattern dei segreti condivisi (ICH-159): `SECRET_PATTERNS` per il benchmark del gate, `OUTCOME_SECRET_PATTERNS` per gli esiti dei comandi nel retain worker |
| `hs-python.sh`            | sourced da ogni hook: risolve in `HS_PY` un interprete Python utilizzabile (indipendente dal PATH di sessione) ed esporta `PYTHONUTF8=1` |

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

## Recorder dei golden (`HINDSIGHT_RECORD`)

Per il porting nella mod `trinity-memory` (ICH-173): con `HINDSIGHT_RECORD=1` nell'ambiente di
Claude Code ogni esecuzione di `hindsight-recall.sh`, `hindsight-failcheck.sh`,
`hindsight-mm-inject.sh` e del worker (`--queued`, `--drain`, modalità script) scrive un record
JSON in `$HS_CACHE_DIR/hs-golden/<script>/<UTC>-<pid>.json` (`lib/hindsight_recorder.py`). Con un
valore diverso da `1`, o senza la variabile, il modulo non viene nemmeno importato.

Il record (`version: 1`) contiene: argv, pid/ppid, cwd, piattaforma, orari, `session_id`, `stdin`
(`HOOK_INPUT`; `null` nel worker `--queued`/`--drain`, il cui input è l'entry di coda in
`state_before`), config effettiva, presenza delle chiavi API (mai i valori), ogni `urlopen`
(metodo, URL, timeout, body inviato, status, body **letto dal chiamante**, errori), ogni
`subprocess.check_output` (git), stdout, `exit_code`, traceback, file di stato prima e dopo
(`state_before`/`state_after`, contenuto intero), coda dei transcript che il codice apre (le
ultime 200 righe come le ha lette, anche se Claude Code ci appende dopo l'avvio; `changed` se una
lettura successiva lo trova cresciuto) e `redacted`.

- **Privacy:** contiene testo delle conversazioni; resta nella cache per-utente (file 0600). Mai
  header HTTP né variabili d'ambiente. Una stringa in cui un pattern di `hindsight_secrets.py`
  trova un segreto diventa `[REDACTED]` per intero, e i valori di `OPENAI_API_KEY`,
  `TYPESAFE_API_KEY`, `VOYAGE_API_KEY` spariscono ovunque: `redacted: true` dice che il record non
  è più fedele all'esecuzione.
- **Limiti:** lo stato "dopo" del recall può dipendere dal worker staccato ancora in corso; se
  Claude Code chiude l'hook per timeout il record manca; su Windows la lettura dello stato non
  blocca cancellazioni e rename degli altri hook (`FILE_SHARE_DELETE`), ma un `os.replace` sopra un
  file nell'istante in cui il recorder lo legge fallisce comunque (Windows lo nega a ogni lettore,
  anche al codice degli hook). I record pesano (coda del
  transcript): il recorder va acceso solo per le sessioni di raccolta.

## 📁 `ops/` — script operativi e utility

Script non-hook, eseguiti a mano o richiamati da altri (hook/mise/scheduler).

| File                         | Chi lo chiama                                                     | Cosa fa                                                      |
| ---------------------------- | ----------------------------------------------------------------- | ------------------------------------------------------------ |
| `hindsight-drain-retain.py`  | `hindsight-sentinel.sh` (dopo il `--drain` del worker)            | attende che i retain in volo siano estratti dal server prima dello stop |
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
| `hs-db-dump.sh`             | dump portabile del DB Hindsight (`pg_dump -Fc`) per il sync tra macchine — `mise run db-dump`                                                                      |
| `hs-db-restore.sh`          | restore dal dump con guardrail anti-perdita (rifiuta se il DB locale ha scritture più recenti) — `mise run db-restore`                                             |
| `hs-db-lib.sh`              | sourced da `hs-db-dump.sh`/`hs-db-restore.sh`: risolve binari Postgres del cluster e parametri di connessione per-OS                                               |

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
