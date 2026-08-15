# Piano — Mental model per-progetto (ICH-77)

Issue: `ICH-77` — "Define how to set per-project mental models with the Trinity plugin".
Branch: `miboscol/ich-77-define-how-to-set-per-project-mental-models-with-the-trinity`.

## Verdetto di fattibilità

**Fattibile.** Il meccanismo di risoluzione bank per-progetto esiste già ed è condiviso:
`resolve_bank()` / `bank_url()` in `hooks/hindsight/lib/hindsight_config.py` (righe ~481 e ~529).
Lo shim MCP (`hooks/hindsight/mcp/hindsight-mcp-shim.sh`) lo usa già per i mental model: in un
progetto non-Trinity i tool `mcp__hindsight__create_mental_model` / `list_mental_models` /
`get_mental_model` / `refresh_mental_model` operano **già sul bank del progetto**. Il gap è solo
nei due path REST che leggono `cfg["api_url"]` (che `load_config()` risolve sempre al core):

- `hooks/hindsight/hindsight-mm-inject.sh:30` — iniezione SessionStart, solo core.
- `hooks/hindsight/ops/hindsight-mental-models.sh:27` — seed/list/show/refresh, solo core.

## Design

I mental model diventano speculari ai fatti: i **modelli core** (le 3 knowledge page condivise)
restano nel core e sono iniettati ovunque; un progetto può definire i **propri modelli** nel
proprio bank, iniettati in aggiunta.

Decisioni confermate:

- **D1** — scope di iniezione: `mental_model_inject_banks` default **`["auto", "core"]`**
  (simmettrico a `recall_banks`; il bank progetto è vuoto finché non lo popoli, quindi zero
  cambiamenti osservabili nei progetti che non definiscono modelli).
- **D2** — dichiarazione dei modelli di progetto: nuove chiavi additive **`project_mental_models`**
  e **`project_mental_models_inject_ids`** (non clobberano i 3 core nel merge a strati).

Vincolo: i knob per-progetto NON possono stare sotto `bank` (è in `PROJECT_BLOCKED_KEYS` per
sicurezza). Sono chiavi top-level.

## Nuove chiavi di config (in `DEFAULTS` di `hindsight_config.py`)

| Chiave | Default | Ruolo |
|---|---|---|
| `mental_model_inject_banks` | `["auto", "core"]` | da quali bank iniettare a SessionStart |
| `mental_models` | `[]` (plugin: 3 core) | modelli **core**, definiti dal plugin |
| `mental_models_inject_ids` | `["user-profile", "project-conventions"]` (plugin: 3) | id core da iniettare |
| `project_mental_models` | `[]` | modelli **del progetto**, definiti nel suo `hindsight.config.json` |
| `project_mental_models_inject_ids` | `[]` | id progetto da iniettare |

## Touch point

| File | Modifica |
|---|---|
| `hooks/hindsight/lib/hindsight_config.py` | + 3 chiavi in `DEFAULTS`; + helper `mental_model_bank_urls()` |
| `hooks/hindsight/hindsight-mm-inject.sh` | fan-out sui bank risolti, id-list per-bank (core vs progetto), dedup per id |
| `hooks/hindsight/ops/hindsight-mental-models.sh` | risolve il bank dal cwd (setta `CLAUDE_PROJECT_DIR` dal toplevel git); `seed` sceglie la lista modelli in base al bank |
| `hooks/hindsight/tools/hindsight-check.sh` §16 | + check nuove chiavi e helper; i check core restano |
| `README.md` §9 | + sottosezione "Mental model per-progetto" |
| `commands/hindsight-create-agent.md` | fix nota obsoleta "Bank inchiodato /mcp/trinity-project/" |

## Passi di implementazione

1. **Config** — aggiungere `mental_model_inject_banks`, `project_mental_models`,
   `project_mental_models_inject_ids` ai `DEFAULTS`; aggiungere `mental_model_bank_urls()`
   (speculare a `recall_bank_urls`, con retrocompat `_api_url_explicit`); aggiornare il
   commento del retrocompat `api_url` (riga ~606) togliendo `mm-inject` dall'elenco.
2. **Inject** — `hindsight-mm-inject.sh`: importare `resolve_bank`/`bank_url`; risolvere i nomi
   bank di `mental_model_inject_banks` (dedup per nome); per ogni bank scegliere la id-list
   (`mental_models_inject_ids` se bank == core, altrimenti `project_mental_models_inject_ids`);
   fetch `?detail=content` per coppia (url, id) con dedup per id; il resto (header/trailer,
   truncation equa su `mental_models_inject_max_chars`) invariato.
3. **Ops** — `hindsight-mental-models.sh`: prima di `load_config()`, settare
   `CLAUDE_PROJECT_DIR` dal toplevel git del cwd (i hook ce l'hanno, lo script manuale no);
   `BASE = bank_url(cfg, resolve_bank(retain_bank, cfg, cwd))`; in `seed`, scegliere
   `mental_models` se il bank risolto è il core, altrimenti `project_mental_models`.
4. **Check** — `hindsight-check.sh` §16: check che le nuove chiavi siano riconosciute e che
   `mental_model_bank_urls` risolva `["auto","core"]` → core deduplicato nel repo Trinity.
   I check esistenti sui 3 modelli core restano.
5. **Doc** — `README.md` §9 + fix `commands/hindsight-create-agent.md`.
6. **Commit + PR** — commit atomici in inglese; PR unica con `Fixes ICH-77`.

## Verifica manuale (fuori da check.sh)

- In Trinity: `bash hooks/hindsight/ops/hindsight-mental-models.sh seed` → idempotente, core.
- In un repo non-Trinity con `hindsight.config.json` che definisce `project_mental_models` +
  `project_mental_models_inject_ids`: `seed` crea i modelli nel bank del progetto;
  `hindsight-mm-inject.sh` inietta core + progetto (testabile con
  `HS_CFG_MENTAL_MODELS_INJECT_ON_START=1` + input JSON).

## Rischi / edge case

- **Retrocompat**: con `["auto","core"]`, un progetto senza `project_mental_models` non cambia
  comportamento (bank progetto vuoto). In Trinity `"auto"` collassa sul core → `[core, core]`
  deduplicato → identico a oggi.
- **Collisione id**: gli id dei modelli progetto non devono riusare i 3 id core (`user-profile`,
  `project-conventions`, `recurring-learnings`); il dedup per id fa vincere il primo bank
  (progetto, elencato prima), quindi un riuso oscurerebbe il modello core. Da documentare.
- **Tag nel refresh**: un modello nel bank progetto, taggato `["claude-code"]` o senza tag, legge
  i fatti del progetto (che portano `claude-code`) — nessun tag speciale serve nel caso semplice.
  `exclude_mental_models: true` è già nel seed (anti-feedback-loop).
- **Anti-loop retain**: header/trailer del blocco iniettato sono già coperti da `strip_memory_block`.
- **`CLAUDE_PROJECT_DIR`** nello script ops va derivato dal toplevel git del cwd, non assunto.
