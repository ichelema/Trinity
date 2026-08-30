# Schema summary

> **Index** — [Top-level entities](#top-level-entities) · [Identifier patterns](#identifier-patterns) · [Pagination (Connection)](#pagination-connection) · [Filtering](#filtering) · [The "save" pattern](#the-save-pattern) · [Soft delete vs hard delete](#soft-delete-vs-hard-delete) · [When to introspect](#when-to-introspect)

Linear's GraphQL schema is large (hundreds of types). This file is **not** a transcript of it — it's the mental model you need to compose queries without re-introspecting every time. For unknown types, run `scripts/linear.py introspect <TypeName>` and load just that one.

## Top-level entities

```
Organization
├── Team ──┬── Issue ──┬── Comment
│          │           ├── IssueLabel  (M:N via labels)
│          │           ├── IssueRelation  (blocks, duplicates, related)
│          │           ├── Reaction
│          │           ├── Attachment
│          │           ├── IssueHistory  (audit-style trail)
│          │           └── WorkflowState  (current state pointer)
│          ├── Cycle ──── Issue (M:N — issues belong to cycles)
│          ├── WorkflowState  (per-team state machine)
│          ├── Template
│          └── ProjectMilestone
├── Project ──┬── Issue (M:N)
│             ├── ProjectUpdate
│             ├── ProjectMilestone
│             └── Document
├── Initiative ──── Project (M:N)
├── User ──── Issue (assignee, creator, subscribers)
├── Document  (workspace-level docs)
├── Customer ──── CustomerNeed
└── Webhook  (workspace-level, optional team filter)
```

Mental model: **Organization → Team → Issue is the spine**. Almost everything attaches to an Issue or sits beside a Team. Projects and Initiatives cut across teams. Cycles are team-scoped time boxes that contain issues.

## Identifier patterns

Linear consistently uses **two** identifiers per entity. Know the difference:

| Field | Type | Example | Use |
|---|---|---|---|
| `id` | `String` (UUID v4) | `dab332d1-98c7-48e4-aa0a-0d987d033074` | Always accepted by mutations and `node(id)` lookups |
| `identifier` | `String` (issues only) | `AGI-86` | Human-readable. Accepted by some queries but **not** mutations |
| `key` (Team) | `String` | `AGI` | Short team prefix; rendered in `identifier` |
| `slug` (Workspace, Project) | `String` | `agileandy` | URL fragment |

**Rule:** mutations almost always want the UUID `id`, not `identifier` or `key`. If a query accepts both, the docs say so explicitly.

## Pagination (Connection)

Every list field follows the Relay Connection spec:

```graphql
issues(first: 50, after: "cursor") {
  nodes { id identifier title }
  pageInfo {
    hasNextPage
    endCursor
  }
}
```

| Field | Notes |
|---|---|
| `first` / `last` | Page size. Cap at 250. Higher = more complexity points. |
| `after` / `before` | Opaque cursor from a previous `pageInfo.endCursor`. |
| `nodes` | Convenience field — flat list. Prefer this over `edges { node { … } }`. |
| `pageInfo.hasNextPage` | Loop until this is false. |

**Complexity warning:** complexity multiplies with `first`. `issues(first: 250)` with 5 nested fields is heavier than 5 sequential `issues(first: 50)` queries. Tune for the workload.

## Filtering

Most list fields take a `filter` arg with the connection's `*Filter` input type. Filters compose AND/OR/NOT and use field-specific comparators:

```graphql
issues(
  filter: {
    team: { key: { eq: "AGI" } }
    state: { type: { in: ["started", "unstarted"] } }
    assignee: { isMe: { eq: true } }
    priority: { lte: 2 }
  }
)
```

Common comparators by field type:

| Field type | Comparators |
|---|---|
| String | `eq`, `neq`, `in`, `nin`, `contains`, `startsWith`, `endsWith` (and `*IgnoreCase` variants). Enum-typed entity fields (e.g. `WorkflowState.type`) still expose **String** comparators on their filter input — pass quoted strings (`["unstarted", "started"]`), not bare enum literals. |
| Number / DateTime | `eq`, `neq`, `lt`, `lte`, `gt`, `gte`, `in`, `nin` |
| Boolean | `eq`, `neq` |
| Relation | Nested filter object (`team: { key: { eq: "AGI" } }`) |
| Logical | `and: [Filter]`, `or: [Filter]`, `not: Filter` |

When in doubt, introspect the `*Filter` type: `linear.py introspect IssueFilter`.

## The "save" pattern

Linear's MCP exposes a `save_*` operation that maps to **two** GraphQL mutations under the hood:

| Caller intent | GraphQL mutation |
|---|---|
| New row, no `id` supplied | `*Create` (e.g. `issueCreate`) |
| Existing row, `id` supplied | `*Update` |

The skill calls these directly. `*Create` accepts a `*CreateInput`; `*Update` accepts an `id` plus a `*UpdateInput`. The two input types overlap heavily but are not interchangeable — Update inputs make every field optional, Create inputs require the minimum set (e.g. `teamId` + `title` for issues).

Both return a payload of shape:

```graphql
{
  success: Boolean!
  lastSyncId: Float          # for delta sync, ignore unless using webhooks
  <entity>: <Entity>          # the created/updated record, hydrated
}
```

Always select `success` and the entity's id/identifier so you have something to chain.

## Soft delete vs hard delete

Caught this in Phase 0 — write it down loudly:

| Mutation | Default behaviour | Force hard delete |
|---|---|---|
| `issueDelete(id)` | Soft delete: sets `trashed=true`, 30-day retention | `issueDelete(id, permanentlyDelete: true)` |
| `issueArchive(id)` | Archives (still queryable) | `issueArchive(id, trash: true)` then `issueDelete(id, permanentlyDelete: true)` |
| `commentDelete(id)` | Hard delete (no trash) | n/a |
| `projectDelete(id)` | Soft delete | Confirm via introspection — semantics drift |

When an agent says "delete the issue," ask whether it means trash or purge. Default to soft for safety; require an explicit flag for hard.

## When to introspect

Run `linear.py introspect <TypeName>` instead of guessing when you need to:

- Check whether an input field exists or is named differently than expected.
- Discover the args on a mutation you haven't used before.
- Find which enum values a field accepts (`introspect WorkflowStateType` → started/unstarted/completed/canceled/triage/backlog).
- Resolve a `field "x" not allowed on type "Y"` error.

Cheap (low-tens of complexity points each). Don't try to introspect `__schema` directly — it'll trip the 10k cap. One type at a time.
