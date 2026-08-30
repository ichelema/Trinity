# Mutations cheatsheet — the gap five

> **Index** — [1. Webhooks](#1-webhooks-crud) · [2. Cycles & workflow states](#2-cycles--workflow-states) · [3. Relations, reactions, subscriptions](#3-relations-reactions-subscriptions) · [4. Templates, custom views, favorites](#4-templates-custom-views-favorites) · [5. Audit log & admin](#5-audit-log--admin)

This file covers the five mutation surfaces reachable via the Linear API but **not** via the Linear MCP. These are the operations that justify writing a skill at all — for everything else, the MCP is fine.

For the read paths, MCP-parity write paths, and entity model, see `references/common-queries.md` and `references/schema-summary.md`.

---

## 1. Webhooks CRUD

Lives in its own file: see **`references/webhooks.md`** for the full reference (resource types, signing, delivery semantics, common pitfalls). It's broken out because webhooks are the single biggest reason to use this skill instead of the MCP, and the receiver-side concerns (signature verification, idempotency) deserve their own page.

---

## 2. Cycles & workflow states

The MCP is read-only on both. The API exposes full CRUD plus two cycle-flow conveniences (`shiftAll`, `startUpcomingCycleToday`). Required for: automated cycle rollover, slip-the-sprint workflows, custom state-machine provisioning, status-driven automation.

### Create a cycle

Required: `teamId`, `startsAt`, `endsAt`. `name` is optional — Linear auto-numbers cycles per team if you omit it.

```graphql
mutation CreateCycle($input: CycleCreateInput!) {
  cycleCreate(input: $input) {
    success
    cycle { id number name startsAt endsAt }
  }
}
```

```json
{"input": {
  "teamId": "<team-uuid>",
  "name": "Sprint 12 — auth refactor",
  "description": "Wrap up the OAuth migration; ship the new token store.",
  "startsAt": "2026-05-12T00:00:00.000Z",
  "endsAt": "2026-05-26T00:00:00.000Z"
}}
```

### Update a cycle

Pass `id` as a top-level arg, plus a partial `CycleUpdateInput`. **`teamId` is not in the update input** — cycles can't be moved between teams.

```graphql
mutation UpdateCycle($id: String!, $input: CycleUpdateInput!) {
  cycleUpdate(id: $id, input: $input) {
    success
    cycle { id name startsAt endsAt completedAt }
  }
}
```

```json
{"id": "<cycle-uuid>", "input": { "endsAt": "2026-05-30T00:00:00.000Z" }}
```

### Archive a cycle

```graphql
mutation ArchiveCycle($id: String!) {
  cycleArchive(id: $id) { success }
}
```

Archiving hides the cycle from default UI and most queries. To list archived cycles, pass `includeArchived: true` to the connection.

> **One-way operation.** There is no `cycleUnarchive`, and `CycleUpdateInput` has no `archivedAt` field. A cycle archived via the API cannot be restored to the UI by any mutation we know of — only re-created. **For any "close out the sprint" intent, prefer `cycleUpdate(input: { completedAt: <now> })` instead** (see [Close a cycle](#close-a-cycle-without-archiving)). Reserve `cycleArchive` for cycles you genuinely want to disappear.

### Close a cycle (without archiving)

```graphql
mutation Close($id: String!, $input: CycleUpdateInput!) {
  cycleUpdate(id: $id, input: $input) {
    success
    cycle { id completedAt }
  }
}
```

```json
{"id": "<cycle-uuid>", "input": { "completedAt": "2026-05-09T16:00:00.000Z" }}
```

The cycle moves into Linear's "completed" status, stays visible, and remains queryable without `includeArchived`.

### Shift all cycles by N days

The slip-the-sprint move. From a starting cycle, all subsequent cycles shift forward by `daysToShift` days. Useful when a team commits and reality slips by a sprint.

```graphql
mutation ShiftCycles($input: CycleShiftAllInput!) {
  cycleShiftAll(input: $input) {
    success
  }
}
```

```json
{"input": { "id": "<starting-cycle-uuid>", "daysToShift": 7 }}
```

`daysToShift` is a `Float`. Negative values pull cycles earlier — confirm with the user before running this; it's destructive in the sense that scheduled work shifts under everyone's feet.

### Start the upcoming cycle today

For when a cycle is scheduled to begin tomorrow but the team is ready now:

```graphql
mutation StartNow($id: String!) {
  cycleStartUpcomingCycleToday(id: $id) { success }
}
```

The `id` is the upcoming cycle's id (not the active one). Linear adjusts `startsAt` to today and shifts the active cycle's `endsAt` to match.

### Sub-week / session-scoped cycles

The Linear UI only lets you pick cycle durations in whole weeks (1, 2, 3, 4). **The API does not enforce this.** `CycleCreateInput.startsAt` and `endsAt` are raw `DateTime` values — you can create cycles of any length: a few hours, one day, three days, whatever fits a single agentic-coding session.

Useful when you want **one cycle per coding session** rather than per calendar week.

The catch: the *team* still has auto-rollover settings that are week-bound and will keep generating cycles in parallel with your manual ones.

| Team field | Type | Behaviour |
|---|---|---|
| `cyclesEnabled` | `Boolean` | Master switch for the auto-rollover engine |
| `cycleDuration` | `Int` (weeks, ≥1) | Cadence for auto-generated cycles |
| `cycleCooldownTime` | `Int` (weeks) | Gap between auto-generated cycles |
| `upcomingCycleCount` | `Float` | How many future cycles Linear pre-creates |
| `cycleStartDay` | `Float` | Day of week the auto-cycle starts |

Two ways to run sub-week cycles cleanly:

**Manual-only (recommended for "1 cycle = 1 session"):** disable the auto-engine, then create cycles via `cycleCreate` per session.

```bash
python scripts/linear.py mutation \
  'mutation($id:String!,$i:TeamUpdateInput!){teamUpdate(id:$id,input:$i){success}}' \
  --variables '{"id":"<team-uuid>","i":{"cyclesEnabled":false}}'
```

Then create a session cycle with arbitrary boundaries:

```json
{"input": {
  "teamId": "<team-uuid>",
  "name": "Session 2026-05-08 — webhook receiver",
  "startsAt": "2026-05-08T09:00:00.000Z",
  "endsAt":   "2026-05-08T18:00:00.000Z"
}}
```

Close (`cycleUpdate(completedAt: …)`) at session end. Don't archive — that's irreversible.

**Override the auto-cycle:** keep `cyclesEnabled: true` and use `cycleUpdate` to truncate or extend Linear's auto-generated active cycle to your session length. Less tidy — Linear keeps generating future cycles on the week cadence regardless, so you accumulate empty phantom cycles.

### Sub-day boundaries — gotchas

These bite the moment cycles get shorter than the auto-cadence and you start `cycleUpdate`-ing them. Discovered the hard way on AGI; codified here so you don't.

**1. `cycleUpdate` requires `new_startsAt > previous_startsAt + 24h` *strictly*.** Equal is rejected. Linear's error message reads "Please choose a start date that is after the start of the previous cycle" — the actual rule is the strict 24h offset, not the start-vs-start it implies. Curiously, Linear's *own* auto-created cycles touch at exactly equal boundaries, but you can't reproduce that via `cycleUpdate`.

Workaround: stagger consecutive cycles' `startsAt` by **+1 ms per cycle**. The UI displays seconds (or coarser), so the drift is invisible. Over a year of daily cycles that's 365 ms — bounded and easy to reset by re-creating the chain.

**2. Adjacent `cycleUpdate` calls must run sequentially.** The validator races on concurrent writes, and parallel updates reject each other against the *unmodified* state of their predecessor. Issue them one at a time, in chronological order.

**3. `cycleArchive` is one-way (see [Archive](#archive-a-cycle)).** Use `cycleUpdate(completedAt: …)` for sprint-closing intent.

### Cycle rollover pattern

Closing a cycle and carrying its in-progress work forward is a **two-step**, in order:

```graphql
# 1. Reassign each in-progress issue to the new cycle.
mutation Move($id: String!, $input: IssueUpdateInput!) {
  issueUpdate(id: $id, input: $input) { success issue { id cycle { id } } }
}
```
Variables: `{"id": "<issue-uuid>", "input": {"cycleId": "<new-cycle-uuid>"}}`

```graphql
# 2. Close the old cycle. Don't archive — close.
mutation Close($id: String!, $input: CycleUpdateInput!) {
  cycleUpdate(id: $id, input: $input) { success cycle { completedAt } }
}
```
Variables: `{"id": "<old-cycle-uuid>", "input": {"completedAt": "2026-05-09T16:00:00.000Z"}}`

Order matters: move issues *before* closing, otherwise they're orphans on a completed cycle that may behave oddly in burndowns. Filter the move set with the issue list query (`issues(filter: { state: { type: { in: ["started"] } } })`) to scope to in-progress only, or include `unstarted` to also pull todos forward.

For a daily-cycle automation that does this on a schedule, see **`references/cycles-daily-automation.md`** and `scripts/cycles_maintain.py`.

### Workflow states — create

Required: `teamId`, `type` (string — see enum below), `name`, `color`. `type` is `String!` not an enum input — pass quoted strings.

```graphql
mutation CreateState($input: WorkflowStateCreateInput!) {
  workflowStateCreate(input: $input) {
    success
    workflowState { id name type color position }
  }
}
```

```json
{"input": {
  "teamId": "<team-uuid>",
  "type": "started",
  "name": "In Review",
  "color": "#5E6AD2",
  "description": "PR open, awaiting code review.",
  "position": 2.5
}}
```

`type` enum values:

| Value | Meaning |
|---|---|
| `triage` | Inbox, not yet refined |
| `backlog` | Refined but not committed |
| `unstarted` | Committed, not started |
| `started` | Work in progress |
| `completed` | Done |
| `canceled` | Won't do |

Each team needs at least one state of each functional type (Linear enforces this). `position` is a float for ordering — pick a value between two existing states, like `2.5` to slot between positions 2 and 3.

### Workflow states — update

Note: **`type` is not in the update input**. To change a state's type, archive the old one and create a new one with the right type.

```graphql
mutation UpdateState($id: String!, $input: WorkflowStateUpdateInput!) {
  workflowStateUpdate(id: $id, input: $input) {
    success
    workflowState { id name color position }
  }
}
```

### Workflow states — archive

```graphql
mutation ArchiveState($id: String!) {
  workflowStateArchive(id: $id) { success }
}
```

Linear refuses to archive a state that issues are currently in. Move issues out (`issueUpdate(id, input: { stateId: ... })`) first.

---

## 3. Relations, reactions, subscriptions

The three engagement primitives missing from the MCP. None of them are gated behind admin scope — any user-equivalent personal key can write them.

### Issue relations

Mark one issue as related to another. Use cases: "this is a duplicate of AGI-42", "AGI-87 blocks AGI-91", "see also AGI-58".

```graphql
mutation LinkIssues($input: IssueRelationCreateInput!) {
  issueRelationCreate(input: $input) {
    success
    issueRelation { id type issue { identifier } relatedIssue { identifier } }
  }
}
```

```json
{"input": {
  "type": "blocks",
  "issueId": "AGI-87",
  "relatedIssueId": "AGI-91"
}}
```

`type` is the `IssueRelationType` enum:

| Value | Meaning |
|---|---|
| `blocks` | `issueId` blocks `relatedIssueId`. Linear automatically adds the inverse "blocked by" relation. |
| `duplicate` | `issueId` is a duplicate of `relatedIssueId`. |
| `related` | Loose link — informational. |
| `similar` | Surfaced via Linear's similarity detection. |

Both `issueId` and `relatedIssueId` accept a UUID or a human-readable identifier (`AGI-87`). The mutation resolves either form.

`issueRelationUpdate(id, input)` accepts the same fields with everything optional. Note: in the *update* input, `type` is loosely typed as `String` rather than the enum — pass quoted strings (`"blocks"`).

`issueRelationDelete(id)` removes the link. The inverse relation goes with it.

### Reactions

Add an emoji reaction to a comment, issue, project update, or initiative update. The exact same surface emojis use in the Linear UI.

```graphql
mutation React($input: ReactionCreateInput!) {
  reactionCreate(input: $input) {
    success
    reaction { id emoji user { name } }
  }
}
```

`emoji` is required. Then **exactly one** target id — the schema allows several (`commentId`, `issueId`, `projectUpdateId`, `initiativeUpdateId`) but enforces "pick one" server-side. Don't send two; you'll get an error.

```json
{"input": { "emoji": "👍", "commentId": "<comment-uuid>" }}
```

```graphql
mutation Unreact($id: String!) {
  reactionDelete(id: $id) { success }
}
```

`reactionDelete(id)` is hard delete — no trash. To find the reaction id, query the parent's `reactions` field and filter by `user.id` and `emoji`.

### Notification subscriptions

Subscribe an agent (or any user) to events on a specific resource. This is how an agent says "watch this issue / project / cycle for me." It's distinct from webhooks: subscriptions feed Linear's notification system (the bell icon, email digests, push), not a custom HTTP endpoint.

```graphql
mutation Subscribe($input: NotificationSubscriptionCreateInput!) {
  notificationSubscriptionCreate(input: $input) {
    success
    notificationSubscription { id active notificationSubscriptionTypes }
  }
}
```

The input takes **one** of: `customerId`, `customViewId`, `cycleId`, `initiativeId`, `labelId`, `projectId`, `teamId`, `userId`. Pick the resource you want to follow.

```json
{"input": {
  "projectId": "<project-uuid>",
  "notificationSubscriptionTypes": ["issueCreated", "issueStatusChanged", "projectUpdateCreated"],
  "active": true
}}
```

`notificationSubscriptionTypes` is `[String!]` — passing an empty list (or omitting it) subscribes to **all** event types for that resource. Common values: `issueCreated`, `issueStatusChanged`, `issueDueDate`, `projectUpdateCreated`, `commentReaction`. Run `linear.py introspect Mutation` and grep for the related enum if you need the canonical list.

```graphql
mutation UpdateSubscription($id: String!, $input: NotificationSubscriptionUpdateInput!) {
  notificationSubscriptionUpdate(id: $id, input: $input) {
    success
    notificationSubscription { id active notificationSubscriptionTypes }
  }
}
```

`NotificationSubscriptionUpdateInput` only exposes `active` and `notificationSubscriptionTypes`. Pause notifications by setting `active: false` instead of deleting.

**There is no `notificationSubscriptionDelete` mutation.** Linear keeps subscription rows for audit purposes — toggle `active: false` and treat it as deleted. If you need a clean slate, the only way to remove the row entirely is via the UI.

---

## 4. Templates, custom views, favorites

Programmatic provisioning surface. The MCP only reads templates and views (and not always reliably) — the API exposes full CRUD for all three. Useful when an agent stands up a new team's scaffolding rather than just consuming an existing setup.

### Templates

Templates pre-fill an issue, project, or document with a baseline of fields and content. Type is one string of `"issue"`, `"project"`, or `"document"`.

```graphql
mutation CreateTemplate($input: TemplateCreateInput!) {
  templateCreate(input: $input) {
    success
    template { id name type teamId }
  }
}
```

Required: `type`, `name`, `templateData` (JSON object — the baseline payload). `teamId` optional; omit for workspace-level.

```json
{"input": {
  "type": "issue",
  "name": "[Bug] Triage template",
  "description": "Pre-fills the standard bug-report fields.",
  "teamId": "<team-uuid>",
  "templateData": {
    "title": "[Bug] ",
    "description": "## What happened\n\n## Expected\n\n## Repro steps\n",
    "labelIds": ["<bug-label-uuid>"],
    "priority": 3
  }
}}
```

The `templateData` shape mirrors `<Type>CreateInput` for the target entity. For an issue template, it's a partial `IssueCreateInput`-shaped object — same field names, same conventions. Unset fields are blank when the template materialises.

`templateUpdate(id, input)` swaps any of `name`, `description`, `icon`, `color`, `teamId`, `templateData`, `sortOrder`. `templateDelete(id)` is hard delete.

### Custom views

A saved filter + display configuration that shows up in Linear's UI sidebar. The MCP can't create or modify these.

```graphql
mutation CreateView($input: CustomViewCreateInput!) {
  customViewCreate(input: $input) {
    success
    customView { id name shared owner { name } }
  }
}
```

Required: `name`. `filterData` is an `IssueFilter` input — the same filter shape used in `issues(filter: …)` queries (see `references/schema-summary.md`). Pass `shared: true` to make the view visible to everyone in the workspace.

```json
{"input": {
  "name": "P1 bugs across all teams",
  "icon": "AlertCircle",
  "color": "#FF6B6B",
  "filterData": {
    "priority": { "eq": 1 },
    "labels": { "some": { "name": { "eq": "bug" } } }
  },
  "shared": true
}}
```

You can scope a view to one `teamId`, `projectId`, or `initiativeId` instead of leaving it workspace-wide — Linear renders the view inside the relevant area of the UI when scoped. There's also `projectFilterData` (a `ProjectFilter`) for project-style views and `feedItemFilterData` for activity-feed views.

`customViewUpdate(id, input)` accepts the same fields with everything optional. `customViewDelete(id)` is hard delete; users who had it favorited lose the link.

### Favorites

Favorites are the items in a user's sidebar pin list. Each favorite points at **one** target entity. The schema lists many possible target ids (`issueId`, `projectId`, `cycleId`, `customViewId`, `documentId`, `labelId`, `userId`, `customerId`, `releaseId`, `dashboardId`, etc.) — supply exactly one. Server-side enforces it.

```graphql
mutation Pin($input: FavoriteCreateInput!) {
  favoriteCreate(input: $input) {
    success
    favorite { id sortOrder folderName }
  }
}
```

```json
{"input": {
  "issueId": "AGI-87",
  "folderName": "Right now"
}}
```

`folderName` groups the favorite into a named folder; pass a `parentId` to nest under an existing folder. Folders themselves are favorites with a `folderName` and no target id.

```graphql
mutation MovePin($id: String!, $input: FavoriteUpdateInput!) {
  favoriteUpdate(id: $id, input: $input) {
    success
    favorite { id sortOrder folderName parent { id } }
  }
}

mutation Unpin($id: String!) { favoriteDelete(id: $id) { success } }
```

`favoriteUpdate` only changes `sortOrder`, `parentId`, or `folderName` — you can't switch a favorite from one target to another. To change targets, delete and recreate.

---

## 5. Audit log & admin

The compliance / IT-admin surface. Required for any agent that triages users, manages invites, audits actions, or wires integrations. Most of these need either a personal API key owned by a workspace admin, or an OAuth flow that requested the `admin` scope. **OAuth `actor=app` does not get `admin`** — workspace-wide bots can't perform user-management actions; that's an intentional safety boundary.

### Audit entries (read)

```graphql
query AuditEntries($filter: AuditEntryFilter, $after: String) {
  auditEntries(first: 100, after: $after, filter: $filter) {
    nodes {
      id type createdAt
      ip countryCode
      actor { name email }
      requestInformation
      metadata
    }
    pageInfo { hasNextPage endCursor }
  }
}
```

`AuditEntryFilter` accepts `type` (StringComparator), `actor` (NullableUserFilter), `ip`, `countryCode`, and `createdAt` / `updatedAt` (DateComparator), plus `and`/`or` for compounds. The `type` field is a string like `"Issue.create"`, `"User.update"`, `"OAuthApp.install"` — introspect the enum-shaped strings via a sample query and grep the workspace's actual entry types rather than guessing.

```json
{"filter": {
  "type": { "in": ["User.changeRole", "User.suspend", "OAuthApp.install"] },
  "createdAt": { "gte": "2026-04-01T00:00:00.000Z" }
}}
```

### User management

| Mutation | Args | When |
|---|---|---|
| `userChangeRole(id, role)` | `role` is `UserRoleType` enum | Promote / demote a user |
| `userSuspend(id, forceBypassScimRestrictions)` | bypass needed if SCIM-managed | Lock out a compromised or off-boarded user |
| `userUnsuspend(id, forceBypassScimRestrictions)` | as above | Re-enable a suspended user |
| `userRevokeAllSessions(id)` | n/a | Force re-auth across all of a user's devices — security-incident tool |
| `userRevokeSession(id, sessionId)` | n/a | Kill one specific session |

`UserRoleType` enum values: `owner`, `admin`, `user`, `guest`, `app`. Note `app` — that's the actor=app role, not assignable via this mutation in normal flows.

```graphql
mutation Demote($id: String!) {
  userChangeRole(id: $id, role: user) {
    success
    user { id name email }
  }
}
```

`role` is the `UserRoleType` enum on this mutation — pass enum literal `user`, not the string `"user"`. (Yes, this contradicts most of the rest of Linear's API; it's an inconsistency worth knowing.)

### Organization invites

```graphql
mutation Invite($input: OrganizationInviteCreateInput!) {
  organizationInviteCreate(input: $input) {
    success
    organizationInvite { id email role }
  }
}
```

Required: `email`. Optional: `role` (UserRoleType, defaults to `user`), `teamIds` (auto-add to teams on accept).

```json
{"input": {
  "email": "new-engineer@agiledimensions.com.au",
  "role": "admin",
  "teamIds": ["<team-uuid>"]
}}
```

`organizationInviteUpdate(id, input)` re-sends the invite or changes its role/teams. `organizationInviteDelete(id)` revokes a pending invite.

### Organization-level settings

| Mutation | Use |
|---|---|
| `organizationUpdate(input: OrganizationUpdateInput)` | Workspace name, logo, slug, allowed domains, default-team setting, etc. |
| `organizationDomainCreate / Update / Delete / Verify / Claim` | Manage email domains that auto-join the workspace. Verify before Claim. |
| `organizationDeleteChallenge`, `organizationDelete(input: DeleteOrganizationInput)` | Two-step destruction. The challenge returns a token you echo back to confirm. **Do not script this without explicit approval each time** — it deletes the workspace. |
| `organizationCancelDelete` | Abort a pending deletion within the grace window. |
| `organizationStartTrialForPlan(input)` | Start a paid-plan trial. |

### Integration management — pattern, not enumeration

There are ~58 integration mutations covering Slack, GitHub, Jira, GitLab, Figma, Sentry, Salesforce, Zendesk, PagerDuty, Opsgenie, Microsoft Teams, Google Sheets / Calendar, Intercom, Front, Discord, LaunchDarkly, MCP servers, and more. Listing them here would be a snapshot that rots within months. The patterns are stable:

- **OAuth-based connect:** `integrationSlack(code, redirectUri, …)`, `integrationGithubConnect(code, installationId, …)`, etc. The agent runs the OAuth flow, captures the `code`, calls the connect mutation. The integration row appears in `integrations` query output.
- **Per-integration update/config:** `integrationJiraUpdate(input: JiraUpdateInput)`, `integrationsSettingsUpdate(id, input)`. Each integration with deep config has its own input type — introspect when needed.
- **Disconnect:** `integrationDelete(id, skipInstallationDeletion)` (full removal) or `integrationArchive(id)` (soft).
- **Posting destinations:** `integrationSlackPost`, `integrationSlackProjectPost`, `integrationSlackInitiativePost`, `integrationSlackCustomViewNotifications`, etc. — wire a Linear surface to a specific Slack channel.
- **MCP server provisioning:** `integrationMcpServerConnect(serverUrl, customHeaders, teamId, workflowDefinitionId)` — register an MCP server with a Linear team. Distinct from this skill (this skill talks to Linear directly; MCP server provisioning is for connecting a Linear workspace *to* an MCP server).

To find the exact mutation you need, introspect the `Mutation` type and grep the integration name:

```bash
python scripts/linear.py introspect Mutation 2>/dev/null \
  | python3 -c "import json,sys; d=json.load(sys.stdin); [print(f['name']) for f in d['fields'] if 'jira' in f['name'].lower()]"
```

Then introspect that mutation's input type for the precise field shape. The mutations all follow the same `success` + entity-payload return convention as the rest of the API.

---

Sources:
- <https://linear.app/developers/graphql>
- <https://github.com/linear/linear/blob/master/packages/sdk/src/schema.graphql>
