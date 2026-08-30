# Rate limits and complexity

> **Index** — [Headers](#headers) · [Limits in practice](#limits-in-practice) · [Complexity examples](#complexity-examples-live-data) · [Retry pattern](#retry-pattern) · [Authoritative source](#authoritative-source)

Linear rate-limits on **two axes simultaneously**: request count and query complexity. Both are reported on every response. The CLI in `scripts/linear.py` already logs the relevant headers to stderr after every call — read those rather than trusting any number written here.

## Headers

`scripts/linear.py` parses these (case-insensitive — httpx normalises to lowercase):

| Header | Meaning |
|---|---|
| `x-ratelimit-requests-limit` | Max requests in the current window |
| `x-ratelimit-requests-remaining` | Requests left in the current window |
| `x-ratelimit-requests-reset` | Unix-ms timestamp when the window resets |
| `x-complexity` | Complexity points charged for **this call** |
| `retry-after` | Seconds to wait, only present on 429 |

There is no separate "complexity remaining" header. The complexity budget is per-query (10,000-point cap) **and** per-hour (3M-point pool for personal keys) — but only the per-query value comes back on each response. If you want hourly burn telemetry, sum `x-complexity` across calls in your own log.

## Limits in practice

Linear's docs quote 5,000 req/hr for personal API keys. **This workspace's key is currently 2,500 req/hr** (observed live during Phase 0 smoke). Treat the published number as a ceiling, not a guarantee — read `x-ratelimit-requests-limit` from the first response on a new key.

| Auth flow | Typical req/hr | Per-query complexity cap | Hourly complexity |
|---|---|---|---|
| Personal API key | 2,500 – 5,000 | 10,000 | 3,000,000 |
| OAuth (user) | ~1,200 | 10,000 | 250,000 |
| OAuth `actor=app` | scales with seats | 10,000 | scales with seats |

## Complexity examples (live data)

Captured against a real workspace during Phase 0:

| Operation | Complexity |
|---|---|
| `query { viewer { id name email } }` | 2 |
| `query { teams(first: 50) { nodes { id key name } } }` | 65 |
| `mutation issueCreate(input: …)` returning id/identifier/title/url | 3 |
| `mutation issueDelete(id: …)` returning success | 2 |
| `query { issue(id) { id identifier title trashed archivedAt } }` | 2 |
| `__type(name: "IssueCreateInput")` introspection | 26 |
| `__type(name: "Mutation")` introspection (every mutation arg) | low hundreds |

Rule of thumb: scalar fetches under ~10, list operations scale with `first:` × nesting, full schema introspection blows the cap. **Never call `__schema` with deep `fields → type → ofType` chains** — it 5xx's or trips the 10k limit. Use `__type(name: ...)` for one entity at a time (see `scripts/linear.py introspect`).

## Retry pattern

The client raises `LinearError("rate limited (429); retry-after=…")` on HTTP 429 and exits non-zero. Callers that want to retry should:

1. Catch the error, parse `retry-after` from the message (or — better — refactor `post_graphql` to surface the response object on 429).
2. Sleep the requested seconds plus a small jitter (e.g. `retry_after + random.uniform(0, 1)`).
3. Cap retries at 3. Linear's reset is a hard window — beyond 3 retries you're hitting the same wall.
4. For *complexity* errors (HTTP 400 with `extensions.code = "RATELIMITED"` or similar), the fix is to reduce `first:` and prune fields, not to retry.

The current CLI does **not** auto-retry. That's intentional for Phase 0 — agents calling this skill should see the failure and decide whether retry makes sense for their workflow. A retry helper can be added in Phase 4 (polish).

## Authoritative source

When in doubt, hit the docs:

- <https://linear.app/developers/rate-limiting>
- <https://linear.app/developers/graphql#complexity>

Both pages occasionally lag the actual schema. The live `x-ratelimit-*` and `x-complexity` headers are the source of truth.
