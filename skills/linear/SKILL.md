---
name: linear
description: Read and change the user's Linear issue tracker (team Ichelema, key ICH) through Linear's GraphQL API. Use it whenever the request names an issue key such as ICH-273, or asks to check, read, summarize, comment on, create, update, assign, close or move an issue, ticket, project or cycle — also in Italian, e.g. "controlla la issue ICH-273", "leggi la issue", "cosa dice ICH-275", "commenta la issue", "apri un ticket", "sposta ICH-274 in Done", "chiudi la issue". Also covers webhooks, workflow states, relations, templates and the audit log.
context: fork
---

# linear

You are talking to **Linear** (linear.app — the user's issue tracker). You compose GraphQL operations and run them through `scripts/linear.py`, learning only the parts of Linear the task needs.

## When to use

Use this skill when the request:

- names a Linear issue key (`ICH-273`, `ICH-274`, any `ABC-123`)
- asks to check, read or summarize an issue: "controlla la issue ICH-273", "leggi la issue", "cosa dice ICH-275", "stato di ICH-274"
- asks to change Linear data: create, comment, assign, label, move state, close ("apri un ticket", "sposta in Done", "commenta la issue")
- touches projects, cycles, documents, workflow states, relations, webhooks, templates, the audit log or admin settings

Indice: Regole di sicurezza · First-run checklist · Default team · Reference file index · CLI ·
Worked example · Patterns to follow · Lingua · What this skill does NOT do · Where to look first

## Regole di sicurezza

- **Non modificare Linear quando l'utente chiede solo di consultare**, elencare
  o riepilogare. Una lettura che scrive è un effetto collaterale che l'utente
  non ha chiesto e non si aspetta di dover controllare.
- **Non inventare mai ID** (issue, progetto, stato, label, priorità, relazione).
  Un ID inventato non fallisce in modo rumoroso: crea silenziosamente un
  collegamento sbagliato o nessun collegamento. Recupera sempre i valori
  correnti via GraphQL prima di agire.

## First-run checklist

Serve:

- Python of mise with `httpx` and `python-dotenv`:
  `mise x python -- python -m pip install httpx python-dotenv`.
- `sqlite3` CLI, only for the cookbook in `references/prune-archive.md`:
  Arch `pacman -S --noconfirm sqlite`, MSYS2 `pacman -S --noconfirm mingw-w64-ucrt-x86_64-sqlite3`.

Paths `scripts/` and `references/` are relative to `${CLAUDE_PLUGIN_ROOT}/skills/linear/`. The
scripts find `skills/linear/.env` from any working directory, and `.env` wins over the shell env.

1. Smoke check: `python scripts/linear.py query 'query { viewer { id name email } }'`.
   If it fails with `LINEAR_API_KEY not set` or HTTP 401, see `references/auth.md`.
2. You're live. Pick the reference file matching the task and load only that one.

## Default team

If the user does not name a team, default to **Ichelema** (key `ICH`). Resolve its UUID once per session and reuse:

```graphql
query { teams(filter: { name: { eq: "Ichelema" } }) { nodes { id key name } } }
```

Cache the returned `id` for the rest of the session. Only override when the user explicitly names a different team.

## Reference file index — load only what you need

| File | Load when the task is about… |
|---|---|
| `references/auth.md` | Getting a key, switching to OAuth, token revocation, scopes |
| `references/schema-summary.md` | Entity model, identifiers, pagination, filtering, save / delete semantics |
| `references/rate-limits.md` | 429s, complexity errors, retry strategy, observed limits |
| `references/common-queries.md` | Day-to-day reads + writes — issues, projects, comments, docs |
| `references/webhooks.md` | Subscribing to issue / comment / project / cycle events |
| `references/mutations-cheatsheet.md` | The "gap five" — cycles, workflow states, relations, templates, admin |
| `references/prune-archive.md` | Querying the local sqlite archive of pruned issues (written by `scripts/linear_prune.py`) |
| `references/git-pr-workflow.md` | Branch/PR/merge: magic words, niente auto-merge, cleanup post-merge |

Don't load every file. Load `schema-summary.md` for orientation and one task-specific file. If you're stuck on an unknown type, run `scripts/linear.py introspect <TypeName>` rather than loading more references.

## CLI

```bash
python scripts/linear.py query     <doc-or-file> [--variables JSON|@file.json]
python scripts/linear.py mutation  <doc-or-file> [--variables JSON|@file.json]
python scripts/linear.py introspect <TypeName>

# Prune + sqlite archive (asks "yes" before deleting; --dry-run shows what it would delete).
python scripts/linear_prune.py --team ICH --dry-run [--limit N]
```

- `<doc-or-file>` is either an inline GraphQL string or a path to a `.graphql` file.
- Rate-limit headers (`x-ratelimit-*`) and `x-complexity` are logged to **stderr** after every call.
- 429 raises and exits non-zero with `retry-after` in the message. The CLI does not auto-retry.
- Irreversible operations (`permanentlyDelete`, `organizationDelete*`, `cycleArchive`,
  `commentDelete`) are refused without `--force`. Ask the user first, then re-run with `--force`.
- Personal keys (`lin_api_…`) go in `Authorization` raw; OAuth tokens (`lin_oauth_…`) get a `Bearer ` prefix automatically.

## One worked example end-to-end

Task: "Create a P1 bug in the ICH team titled `auth: 401 on token refresh`, then list its assignee and state."

```bash
# 1. Find the team's UUID (need it for the mutation).
python scripts/linear.py query \
  'query { teams(filter: { key: { eq: "ICH" } }) { nodes { id key } } }'
# → { "teams": { "nodes": [ { "id": "<team-uuid>", "key": "ICH" } ] } }

# 2. Create the issue. Priority 1 = Urgent.
python scripts/linear.py mutation \
  'mutation Create($input: IssueCreateInput!) {
     issueCreate(input: $input) {
       success
       issue { id identifier title priority url }
     }
   }' \
  --variables '{"input": {
     "teamId": "<team-uuid>",
     "title": "auth: 401 on token refresh",
     "priority": 1
   }}'
# → { "issueCreate": { "success": true, "issue": { "identifier": "ICH-87", … } } }

# 3. Read it back with assignee + state.
python scripts/linear.py query \
  'query Get($id: String!) {
     issue(id: $id) {
       identifier title priority
       assignee { name email }
       state { name type }
     }
   }' \
  --variables '{"id": "<id-from-step-2>"}'
```

That's the pattern: introspect or query for an id you don't have, run the mutation with variables, read it back. Three calls, ~8 complexity points total.

## Patterns to follow

- **Always select `success` on mutations.** Linear can return `success: false` with no error array. Check it.
- **Pass IDs as variables, not string interpolation.** GraphQL variables are typed and avoid injection.
- **Page with `nodes` + `pageInfo.endCursor`.** Don't fetch `first: 250` if you only need 10.
- **For unknown types, introspect one type at a time.** `__schema` will trip the complexity cap.
- **Soft vs hard delete is a real distinction.** `issueDelete(id)` trashes; add `permanentlyDelete: true` to purge.

## Lingua

La lingua la decide il **progetto Linear**, non la conversazione:

- default **italiano**;
- **inglese** se il progetto ha la label di progetto `lang:en`
  (librerie pubbliche, progetti da rilasciare).

Leggi le label con la stessa query che usi per risolvere l'id
(`projects { nodes { id name labels { nodes { name } } } }`); per una issue
esistente usa `issue(id: $id) { project { labels { nodes { name } } } }`.
Issue senza progetto: italiano. Repository non tracciato con Linear: inglese
(regola completa in `github-pr-release`, `references/changelog.md`, sezione "Lingua").

Esempi:

- progetto senza label `lang:en` → commit `fix(hooks): quota il path`, titolo PR in italiano;
- progetto con label `lang:en` → commit `fix(hooks): quote the path`, titolo PR in inglese.

La lingua del progetto vale per tutto ciò che resta nel tempo: titolo,
`description` e commenti delle issue, **messaggi di commit**, **titolo e
descrizione della PR** (Linear usa il titolo della PR come attachment della
issue). Termini tecnici, nomi di file e stringhe di codice restano nella forma
originale.

La conversazione con l'utente resta in italiano: riepiloghi, domande e output a
schermo non seguono questa regola.

## What this skill does NOT do (yet)

- Auto-retry on 429 / complexity errors. Caller decides.
- Bulk operations beyond what GraphQL exposes natively (`issueBatchCreate` is reachable; client doesn't add a multi-call wrapper).
- Webhook receiver scaffolding. The skill manages webhook *subscriptions*; you bring your own HTTP endpoint.

## Where to look first when something breaks

| Symptom | Look here |
|---|---|
| `error: LINEAR_API_KEY not set` | `references/auth.md` |
| `HTTP 429` or `rate limited` | `references/rate-limits.md` |
| `field "x" not allowed on type "Y"` | Run `linear.py introspect Y`; check `references/schema-summary.md` |
| `Entity not found` after a delete | Default delete is soft — see `schema-summary.md`'s soft-vs-hard section |
| Mutation returns `success: false` with empty error array | The op was rejected silently; introspect the input type for required fields you missed |
