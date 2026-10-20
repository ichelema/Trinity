# Setup di Hindsight in Trinity

Indice: Setup attivo · Multi-bank · Mental model · Hook e strumenti operativi · Control Plane · Come
Hindsight processa un retain · Troubleshooting

## Setup attivo

In questo progetto Hindsight gira **solo sulla VPS `infomaniak`** (servizi `systemd --user`); i PC
sono client e lo raggiungono con un tunnel SSH.

**Stack:**

- Pacchetto Python: `hindsight-api-slim[embedded-db]` (installato via `mise run install-hindsight`;
  NON il meta-pacchetto `hindsight-api`, alias di `[all]` che tira giù i modelli locali/PyTorch)
- Entry-point: `hindsight-local-mcp` (sulla VPS, lanciato dal servizio via `mise exec`)
- Versione verificata: **1.0.0** (2026-10-14, PC Windows; la VPS va verificata a parte);
  query-analyzer del recall ristretto a `it,en` (`HINDSIGHT_API_QUERY_ANALYZER_LANGUAGES`)
- LLM: **`gpt-5.6-luna`** via provider `openai-responses` per retain/reflect/consolidation;
  **`gpt-4.1-mini`** è l'LLM globale per il query-analyzer del recall
  (chiavi da `$OPENAI_API_KEY`; vedi commenti in `mise.toml`)
- Retain automatico: attivo solo se `retain_enabled` è `true` in `hindsight.config.json`; con
  `false` si salva solo con `retain` MCP. Il gate: **`gpt-5.6-luna`** decide, **TypeSafe
  `jev-latest`** (`$TYPESAFE_API_KEY`) conferma come secondo filtro i soli `retain` (F1 ≥
  `retain_jev_threshold`); errore di Jev = nessun salvataggio
- Embeddings: **Google `gemini-embedding-001`** (1536d, cloud, multilingue; `$GEMINI_API_KEY`)
- Reranker: **`voyage/rerank-3`** via `litellm-sdk` (`$VOYAGE_API_KEY`), cap flat 100 candidati
  (per-budget spento). **Failover chain fail-open**:
  `HINDSIGHT_API_RERANKER_1_PROVIDER = "rrf"` — se Voyage non risponde il recall ripiega su RRF
  invece di dare HTTP 500; la degradazione è segnalata da `hindsight-failcheck.sh` (marker scritto
  da `hindsight-recall.sh` quando i risultati arrivano senza `scores.reranker`)
- Altre feature attive: recency decay esponenziale (halflife 60 giorni), audit log server-side
  (retention 30 giorni), `HINDSIGHT_API_FAIL_ON_EXTRACTION_ERRORS=true` (estrazione fallita dopo i
  retry → operation `failed`, intercettata da `hindsight-failcheck.sh`)
- Storage: embedded PostgreSQL in `~/.pg0/` sulla VPS
- Endpoint MCP: `http://localhost:8888/mcp/trinity-project/` (bank statico per-progetto)
- Registrato a **scope user** come shim stdio `hooks/hindsight/mcp/hindsight-mcp-shim.sh` (bank
  risolto per-progetto; vedi sotto)
- **Server (VPS):** `hindsight.service`, `hindsight-cp.service` e `hindsight-backup.timer`
  (`systemd --user`). Gestione: `systemctl --user status|restart hindsight`, log
  `journalctl --user -u hindsight`. Backup: gli ultimi 5 dump in `~/backups/hindsight`.
- **Client (PC):** env `HINDSIGHT_SSH_TUNNEL=hindsight-vps` (in `~/.claude/settings.json`, generato
  da chezmoi): `hindsight-ensure-up.sh` apre il tunnel che porta `127.0.0.1:8888` (API+MCP) e
  `localhost:9999` (Control Plane) in locale. Chiave SSH dedicata e ristretta
  (`restrict,port-forwarding,permitopen="127.0.0.1:8888",permitopen="localhost:9999",command="/bin/false"`).
  Nessun avvio locale e nessun fallback.
- **Restore del DB (VPS):** `systemctl --user stop hindsight-cp hindsight` → `mise run db-restore` →
  `systemctl --user start hindsight hindsight-cp`.
- **Upgrade Python (VPS):** dopo `mise upgrade python` serve `mise run install-hindsight` e
  `systemctl --user restart hindsight`.

Verifica veloce che il server risponda:

```bash
curl -fsS -m 3 http://localhost:8888/ -o /dev/null -w "%{http_code}\n"  # 404 = up
```

### Multi-bank: core + bank per progetto

La memoria è a due livelli: il bank **CORE** `trinity-project` (informazioni
trasversali) + un **bank per progetto** isolato, governati dal blocco `bank` di
`hindsight.config.json`:

- `retain_bank: "auto"` → il retain automatico (se `retain_enabled` è `true`) scrive sul bank del
  progetto corrente (slug dal remote `origin`, fallback basename; fuori da git o nel repo Trinity
  stesso → core). Il bank si auto-crea al primo retain.
- `recall_banks: ["auto", "core"]` → il recall fa fan-out parallelo su progetto+core e fonde i
  risultati con un rerank globale voyage/rerank-2.5 (fallback interleaving se Voyage non risponde).
  Il core entra solo se listato.
- URL risolti per il cwd corrente: `python hooks/hindsight/lib/hindsight_config.py --banks`

**Tool MCP `hindsight/*` — quale bank vedono** (MCP per-progetto): il server
"hindsight" è definito SOLO a scope user (`claude mcp add-json hindsight --scope user`) come shim
stdio `hooks/hindsight/mcp/hindsight-mcp-shim.sh`, unico per tutti i progetti (non definirlo anche
nel `.mcp.json` di Trinity: produce il warning "Conflicting scopes").
Lo shim risolve il bank con la stessa `resolve_bank` degli hook (slug dal remote origin via
`CLAUDE_PROJECT_DIR`; repo Trinity o fuori-git → core `trinity-project`), attende la readiness del
server e fa da ponte via `mcp-remote` sul node di mise.

I tool MCP parlano comunque con UN solo bank per sessione: il fan-out progetto+core
(`recall_banks: ["auto", "core"]`) resta esclusivo degli hook REST. Per accedere a un bank
arbitrario usa l'API REST (`http://127.0.0.1:8888/v1/default/banks/<nome>/...`).

**Promozione progetto → core**: comando `/trinity:promote` (curata, mai automatica: scan → triage
gpt-4.1-nano → review umana → move con strip dei tag `repo:`/`branch:`). Meccanica in
`hooks/hindsight/ops/hindsight-promote.py` (`--scan/--triage/--move/--reject/--status`); lo
scan+triage si lancia a mano e genera `logs/promote-candidates.json`.

### Mental model: knowledge page iniettate a inizio sessione

Tre mental model sono definiti nel blocco `mental_models` di `hindsight.config.json`:
`user-profile`, `project-conventions`, `recurring-learnings`. I primi due vengono iniettati come
`additionalContext` all'avvio di una sessione nuova (`startup`) dall'hook `hindsight-mm-inject.sh`
(gated da `mental_models_inject_on_start: true`, ids in `mental_models_inject_ids`);
`recurring-learnings` resta nel bank ma non viene iniettato.

- **refresh** rigenera il contenuto dal bank; **inject** mostra solo il contenuto già esistente.
- Refresh manuale immediato (necessario dopo aver cancellato/corretto un fatto):
  `bash hooks/hindsight/ops/hindsight-mental-models.sh refresh --all`

### Hook di sessione e strumenti operativi

| Componente                                          | Trigger/uso               | Cosa fa                                                                                                                                                         |
| --------------------------------------------------- | ------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `hindsight-ensure-up.sh`                            | SessionStart              | Attende la readiness dell'endpoint MCP, aprendo prima il tunnel SSH se `HINDSIGHT_SSH_TUNNEL` è impostata (elimina la race "tool `hindsight/*` non registrati") |
| `hindsight-mm-inject.sh`                            | SessionStart              | Inietta i mental model (vedi sopra)                                                                                                                             |
| `hindsight-failcheck.sh`                            | UserPromptSubmit          | Segnala operation async `failed` lato server (retain accettato ma estrazione fallita) e la degradazione del reranker; de-dup via state file                     |
| `mise run db-dump` / `db-restore`                   | manuale                   | `pg_dump`/restore del DB Hindsight, solo sulla VPS (`tools/hs-db-dump.sh`, `hs-db-restore.sh` con guardrail anti-perdita)                                       |
| `tools/hindsight_export.py` / `hindsight_import.py` | cambio provider embedding | Export dei documenti → re-retain sul nuovo embedding (il cambio di dimensione obbliga al rebuild del bank)                                                      |

### Interfaccia web: Control Plane

UI web opzionale, servita sulla VPS da `hindsight-cp.service` e raggiunta via tunnel su
`http://localhost:9999`. Avvio a mano: `mise run control-plane`. Dettagli, architettura e gotcha in
`../README.md` §15.

## Come Hindsight processa un retain

1. Il client (Claude Code) chiama `retain(content=...)`
2. Il server accetta sincrono → `{status: "accepted", operation_id: "..."}` e mette in coda
3. Worker async chiama `gpt-5.6-luna` (provider `openai-responses`) per estrarre:
   - **observation facts** (fatti atomici, es. "Ichelema prefers Ruby for scripting")
   - **world facts** (versione timestamped + entity-linked, es. "Ichelema prefers Ruby for scripting
     | When: 2026-05-23 | Involving: Ichelema")
4. Entrambi i tipi vengono indicizzati con embeddings nel bank che ha ricevuto il retain (vedi
   «Multi-bank»)
5. `recall` cerca semanticamente su observation + world, restituisce ranked

## Troubleshooting rapido

| Sintomo                                                                        | Causa probabile                                                                        | Fix                                                                                                                                                  |
| ------------------------------------------------------------------------------ | -------------------------------------------------------------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------- |
| Tool `hindsight/*` non visibile in sessione                                    | Tunnel SSH non attivo o servizio giù sulla VPS                                         | Verifica `HINDSIGHT_SSH_TUNNEL`, poi `systemctl --user status hindsight` (VPS) e nuova sessione                                                      |
| A metà sessione i tool danno `mcp-remote: fetch failed` e `/mcp` va in timeout | Tunnel SSH chiuso durante la sessione: `hindsight-ensure-up.sh` lo apre solo all'avvio | Riapri il tunnel con lo stesso comando `ssh -N` dell'hook, controlla `curl http://127.0.0.1:8888/health` (200), poi ricollega `hindsight` con `/mcp` |
| `recall` torna vuoto subito dopo un `retain`                                   | Estrazione fatti ancora in corso, perché è async                                       | Polla `get_operation(operation_id)` finché `completed`, poi ricalla                                                                                  |
| `OPENAI_API_KEY not set` nel log del server                                    | Variabile non disponibile al servizio sulla VPS                                        | Verifica con `mise env` e `journalctl --user -u hindsight`                                                                                           |
