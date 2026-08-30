# linear-api

> A Claude Code / Cowork **skill** that talks to Linear's GraphQL API directly — instead of carrying ~40 MCP tool schemas in context every turn. Progressive discovery: load `SKILL.md` once, load only the reference file the current task needs, compose GraphQL through a thin Python CLI.

[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/license-MIT-yellow.svg)](LICENSE)
[![Tests: 24 passing](https://img.shields.io/badge/tests-24%20passing-green.svg)](tests/)

## TL;DR

```bash
git clone https://github.com/agileandy/linear-api.git
cd linear-api
pip install httpx python-dotenv
cp .env.example .env                 # edit: paste your Linear API key
python scripts/linear.py query 'query { viewer { id name email } }'
```

That's it — you can query Linear. Read `SKILL.md` for the conceptual orientation, `references/common-queries.md` for 18 worked GraphQL operations covering the full Linear MCP surface, `references/mutations-cheatsheet.md` for the surface the MCP **can't** touch (webhooks, cycles, workflow states, relations, templates, audit log).

## Why a skill instead of the MCP

Three reasons, in order of how often they bite:

1. **Coverage.** The Linear MCP can't manage webhooks, cycle / workflow-state mutations, issue relations, templates, custom views, audit log, or admin surface. The API can. That gap is the whole reason this exists. Without webhooks, every Linear-aware agent reduces to polling.
2. **Token cost.** The MCP loads ~40 tool schemas into the agent's context **every turn**, whether the agent touches Linear or not. This skill loads `SKILL.md` (~120 lines) only when the routing layer says a Linear task is starting, and a reference file (~150–650 lines) only for the part of Linear the task touches. Net per-turn cost when Linear is dormant: zero.
3. **Control.** GraphQL only returns the fields you ask for. No fixed tool shapes — if a workflow needs a field MCP didn't expose (or a new field Linear ships next week), you ask for it.

The trade-off: the agent has to learn query composition rather than calling pre-baked tools. `references/common-queries.md` is the one-time price for that — 18 worked examples that cover the MCP-parity surface so the agent only composes from scratch when it goes off-piste.

## Coverage at a glance

| Surface | Linear MCP | this skill |
|---|---|---|
| Issues, comments, projects (CRUD) | ✅ | ✅ |
| Initiatives, milestones, documents, attachments | ✅ | ✅ |
| Cycles | read only | full CRUD + `shiftAll`, `startUpcomingCycleToday` |
| Workflow states | read only | full CRUD |
| Issue relations (blocks / duplicate / related) | ❌ | ✅ |
| Reactions on issues / comments / updates | ❌ | ✅ |
| Notification subscriptions | ❌ | ✅ (no delete — toggle `active: false`) |
| Templates, custom views, favorites | ❌ | ✅ |
| **Webhooks (CRUD + secret rotation)** | ❌ | ✅ |
| Audit log query | ❌ | ✅ (`auditEntries` filter) |
| User admin (`changeRole`, `suspend`, etc.) | ❌ | ✅ (admin scope only) |
| Org invites, domain claims, integration mgmt | ❌ | ✅ |

## Status

- **Phase 0 (spike)** — ✅ done. Live-tested CLI against a real workspace.
- **Phase 1 (MCP parity)** — ✅ done. SKILL.md, foundational refs, 18 worked GraphQL ops.
- **Phase 2 (gap five)** — ✅ done. Full webhooks reference, full mutations cheatsheet for cycles / states / relations / templates / admin.
- **Phase 3.1 (OAuth bot identity)** — ✅ done via `client_credentials` grant. Comments and writes attribute to a registered bot, not to the developer.
- **Phase 3 backlog** — tracked in Linear:
  - **AGI-88** — rate-limit-aware retry helper
  - **AGI-89** — schema introspection cache
  - **AGI-90** — structured mutation logging / telemetry

## Install

You can use this repo three ways. Pick whichever matches how you want it surfaced.

### 1. Standalone (just the CLI)

```bash
git clone https://github.com/agileandy/linear-api.git
cd linear-api
pip install httpx python-dotenv
cp .env.example .env                 # then edit
```

The CLI runs as `python scripts/linear.py …`. Reference docs and example scripts are at `references/` and `scripts/examples/`.

### 2. As a Claude Code skill (recommended for agent use)

Make the skill discoverable so an agent loads `SKILL.md` automatically when a Linear task starts.

```bash
# Project-scoped install (visible only inside one project)
mkdir -p .claude/skills
ln -s "$(pwd)" .claude/skills/linear-api

# Or global install (visible across every project)
mkdir -p ~/.claude/skills
ln -s "$(pwd)" ~/.claude/skills/linear-api
```

The skill's `name` and `description` (from `SKILL.md`'s frontmatter) become discoverable via Claude Code's skill list. The agent loads `SKILL.md` only on first use; per-domain reference files only when a task touches that surface. That progressive-discovery pattern is the whole reason this is cheaper in tokens than the Linear MCP.

### 3. As a slash command

The `.claude/commands/linear.md` file in this repo defines a `/linear` slash command for working assigned issues end-to-end (fetch → In Progress → implement → Done → comment).

```bash
# Symlink globally
ln -s "$(pwd)/.claude/commands/linear.md" ~/.claude/commands/linear.md
```

Then `/linear`, `/linear AGI-23`, or `/linear AGI-23, AGI-26` from any Claude Code session.

## Auth — pick your path

Three options, simplest first. Full walkthrough including OAuth-app setup and gotchas in [`references/auth.md`](references/auth.md).

### Option A — Personal API key (simplest)

Linear → **Settings → API → Personal API keys → Create**. Paste the `lin_api_…` token into `.env`:

```bash
LINEAR_API_KEY=lin_api_xxxxxxxx
```

Acts as you. ~2,500 req/hr. Use for personal scripts, dev work.

### Option B — Bot identity via `client_credentials` grant (recommended for autonomous use)

Comments and writes show the bot's name in Linear's UI and audit log instead of yours. ~30-day token, idempotent re-mint, 5,000 req/hr.

```bash
# 1. Linear → Settings → API → OAuth applications → Create new application.
#    Toggle "Client credentials" ON. Save. Copy Client ID + Secret.
# 2. Paste into .env:
#       LINEAR_OAUTH_CLIENT_ID=...
#       LINEAR_OAUTH_CLIENT_SECRET=...
# 3. Mint the bot token:
python scripts/client_credentials_token.py
# 4. Verify:
python scripts/linear.py query 'query { viewer { name displayName } }'
#    → returns the bot's identity, not yours
```

Re-run the mint script before each ~30-day expiry. Cron line in `references/auth.md`.

### Option C — OAuth `authorization_code` dance (multi-tenant distribution)

For when you ship the skill to other people who'll install it in their own workspaces. Browser-based consent flow with `actor=app` URL parameter. Uses 24h access tokens with rolling refresh.

```bash
python scripts/oauth_dance.py --write-env       # initial install (browser opens)
python scripts/oauth_refresh.py                 # cron-able, runs before each 24h expiry
```

Caveat from live testing: Linear's `actor=app` is sometimes silently downgraded to user-scoped tokens on the auth-code path — Option B is more reliable for solo use. Full notes in `references/auth.md`.

## CLI

```text
linear.py query     <doc-or-file> [--variables JSON|@file.json]
linear.py mutation  <doc-or-file> [--variables JSON|@file.json]
linear.py introspect <TypeName>
```

`<doc-or-file>` is either an inline GraphQL string or a path to a `.graphql` file.

Rate-limit (`x-ratelimit-*`) and complexity (`x-complexity`) headers go to **stderr** after every call. The CLI raises and exits non-zero on HTTP 429 with `retry-after` in the message — see `references/rate-limits.md` for the retry pattern.

### Worked example

```bash
# 1. Find the team UUID.
python scripts/linear.py query \
  'query { teams(filter: { key: { eq: "AGI" } }) { nodes { id key } } }'

# 2. Create an issue. Priority 2 = High.
python scripts/linear.py mutation \
  'mutation Create($input: IssueCreateInput!) {
     issueCreate(input: $input) {
       success
       issue { identifier title url }
     }
   }' \
  --variables '{"input": {
     "teamId": "a57f5901-…",
     "title": "auth: 401 on token refresh",
     "priority": 2
   }}'
```

Three calls, ~8 complexity points total. Every common operation has a copy-paste-ready snippet in `references/common-queries.md`.

## Reference docs

Six files under `references/`. Load only what the current task needs.

| File | Load when the task is about… |
|---|---|
| [`auth.md`](references/auth.md) | Token setup, OAuth flows, scope cheatsheet, revocation |
| [`schema-summary.md`](references/schema-summary.md) | Entity model, identifiers, pagination, filtering, soft / hard delete semantics |
| [`rate-limits.md`](references/rate-limits.md) | 429s, complexity errors, observed limits, retry strategy |
| [`common-queries.md`](references/common-queries.md) | 18 worked GraphQL ops covering the MCP-parity surface |
| [`webhooks.md`](references/webhooks.md) | Subscription mgmt, signing, delivery semantics, common pitfalls |
| [`mutations-cheatsheet.md`](references/mutations-cheatsheet.md) | The gap five — cycles, workflow states, relations, templates, admin |

## Example scripts

```bash
python scripts/examples/list_my_issues.py
python scripts/examples/create_issue.py --team-key AGI --title "..." --priority 2
python scripts/examples/paginate_issues.py --team-key AGI
python scripts/examples/subscribe_webhook.py \
  --url https://your-receiver.example.com/linear \
  --label "triage agent" --resource-types Issue Comment --team-key AGI
```

These exist to demonstrate **patterns** (read, write-then-read, cursor pagination, webhook provisioning), not to enumerate every operation. For breadth, load `references/common-queries.md`.

## Token-cost comparison

Concrete data for the "why this beats MCP" claim. Numbers are approximate, calibrated against Anthropic's tokeniser.

| Scenario | Linear MCP | this skill |
|---|---|---|
| Linear-irrelevant turn (e.g. frontend work) | **~2,000 tokens** (40 tool schemas always loaded) | **0 tokens** (skill not loaded) |
| First Linear-relevant turn | ~2,000 tokens | ~1,200 tokens (`SKILL.md`) + ~1,500 (one reference file) |
| Subsequent Linear turns same task | ~2,000 tokens | 0 tokens (already in context) |
| Coverage of webhooks / cycle mutations / admin | ❌ unsupported | ✅ via `references/mutations-cheatsheet.md` (~3,500 tokens, loaded only when needed) |

Net: **a project that touches Linear 10% of the time saves ~80% of the per-turn token cost** vs the MCP. A project that never touches Linear saves 100%.

## Project layout

```
linear-api/
├── SKILL.md                          # lean entry point — agent's first read
├── README.md                         # this file
├── LICENSE                           # MIT
├── pyproject.toml                    # httpx, python-dotenv (runtime); pytest, respx (dev)
├── .env.example                      # auth template
├── .claude/
│   └── commands/
│       └── linear.md                 # /linear slash command — works assigned issues
├── references/
│   ├── auth.md                       # personal key vs OAuth, scopes, revocation
│   ├── schema-summary.md             # entity model, identifiers, pagination, soft/hard delete
│   ├── rate-limits.md                # observed limits, complexity examples, retry pattern
│   ├── common-queries.md             # 18 worked GraphQL ops — full MCP-parity surface
│   ├── webhooks.md                   # subscription mgmt (resource types, signing, delivery)
│   └── mutations-cheatsheet.md       # the gap five — cycles, states, relations, templates, admin
├── scripts/
│   ├── linear.py                     # GraphQL CLI (query / mutation / introspect)
│   ├── client_credentials_token.py   # ⭐ recommended: mint a 30-day bot token
│   ├── oauth_dance.py                # multi-tenant install flow (browser dance)
│   ├── oauth_refresh.py              # rolling refresh for the dance's 24h tokens
│   └── examples/
│       ├── list_my_issues.py
│       ├── create_issue.py
│       ├── paginate_issues.py
│       └── subscribe_webhook.py
├── tests/
│   └── test_linear_client.py         # respx-mocked unit tests — never hit Linear
└── docs/
    ├── HANDOFF.md                    # original build brief
    └── Linear-API-Integration-Plan.md  # design rationale + MCP gap analysis
```

## Development

### Tests

```bash
pytest                 # mocked — never touches Linear; safe in CI
```

24 mock tests cover the GraphQL transport, header logging, auth-mode switching, the 429 / GraphQL-error paths, the OAuth dance and refresh shapes, and the `client_credentials` mint shape.

### Adding new operations

1. Run `scripts/linear.py introspect <TypeName>` to see the input shape.
2. Compose the GraphQL document.
3. Add a snippet to the relevant `references/*.md` so it's there next time.
4. (Optional) Add a worked example script if it demonstrates a *pattern* (not just an additional read or write).

### Contributing

PRs welcome. Conventions:

- **Tests are mocked, never live.** `tests/test_linear_client.py` uses `respx` to stub `httpx`. Don't introduce live tests — they leak rate-limit budget and break CI.
- **Reference files are the source of truth for "how to do X with Linear."** If you add a new GraphQL op, the snippet goes in `references/`. The example scripts demonstrate patterns, not coverage.
- **Trunk-based dev.** Cut a feature branch per outcome, ff-merge into `main` when done.
- **Follow the docs gotchas.** The "live findings" sections in `references/auth.md`, `rate-limits.md`, and `mutations-cheatsheet.md` are not stylistic preferences — they're things that bit during the build.

### Project history

- [`docs/HANDOFF.md`](docs/HANDOFF.md) — the original build brief.
- [`docs/Linear-API-Integration-Plan.md`](docs/Linear-API-Integration-Plan.md) — the design doc + gap analysis vs the Linear MCP. Worth reading if you want to understand *why* the project is shaped the way it is.
- Git log — phase-by-phase commit history. Each commit's message has the live-test findings that drove the changes.

## License

MIT. See [`LICENSE`](LICENSE).

## Acknowledgements

Built by Andy Spamer in collaboration with Claude (Anthropic). The Phase 0 spike, MCP-parity reference set, gap-five mutations, and OAuth bot-identity work were all live-validated against a real Linear workspace before each commit landed — see the per-commit messages on `main` for the live-test findings that shaped the docs.
