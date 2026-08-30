# Common queries

> **Index** — [Issues](#issues) · [Comments](#comments) · [Projects](#projects) · [Initiatives & Milestones](#initiatives--milestones) · [Teams, Users, Labels](#teams-users-labels) · [Documents](#documents) · [Attachments](#attachments) · [Customers & Status updates](#customers--status-updates) · [Patterns](#patterns-cross-cutting)

This file is the day-to-day MCP-parity surface — the operations you'd reach for first when an agent says "look up X" or "save Y" in Linear. Each example is copy-paste ready: pass it to `scripts/linear.py query` or `mutation` with the variables shown.

Examples marked **✓ live-tested** ran against a real workspace during Phase 1 build. Unmarked examples are composed from live introspection of the input types — the field names are correct; tune the variables to your workspace.

For the entity model, identifiers, and pagination conventions, load `references/schema-summary.md` first. For mutation gotchas (soft delete, save-vs-create, etc.), the same file's later sections.

---

## Issues

### List my open issues ✓ live-tested

```graphql
query MyOpenIssues {
  issues(
    first: 20
    filter: {
      assignee: { isMe: { eq: true } }
      state: { type: { in: ["unstarted", "started"] } }
    }
    orderBy: updatedAt
  ) {
    nodes {
      identifier
      title
      priority
      state { name type }
      team { key }
      updatedAt
    }
    pageInfo { hasNextPage endCursor }
  }
}
```

### Get one issue, with relations ✓ live-tested

```graphql
query GetIssue($id: String!) {
  issue(id: $id) {
    id identifier title description priority url
    state { id name type }
    assignee { id name email }
    team { id key name }
    project { id name }
    cycle { id number startsAt endsAt }
    labels(first: 20) { nodes { id name color } }
    comments(first: 20) {
      nodes { id body createdAt user { name } }
    }
    children(first: 20) { nodes { identifier title state { name } } }
    parent { identifier title }
    relations(first: 20) { nodes { type relatedIssue { identifier title } } }
  }
}
```

Variables: `{"id": "dab332d1-…"}`

### Create an issue (minimal) ✓ live-tested

```graphql
mutation CreateIssue($input: IssueCreateInput!) {
  issueCreate(input: $input) {
    success
    issue { id identifier title url }
  }
}
```

Variables — the only required fields are `teamId` and `title`. The `teamId` below is the **AgileAndy** team (the default team unless the user names a different one — see SKILL.md "Default team"):

```json
{"input": {
  "teamId": "a57f5901-d47d-4a05-a18e-cfbcfceff6a2",
  "title": "auth: 401 on token refresh",
  "description": "Reproduces on Safari 17.x. See attached HAR.",
  "priority": 2
}}
```

`priority` is `0` (none) → `1` (urgent) → `2` (high) → `3` (medium) → `4` (low).

### Hierarchy convention — Epic vs Story

For workflows that distinguish epics (top-level containers) from stories (user-story-sized children), this repo's `/linear` slash command (`.claude/commands/linear.md`) defines a labels-plus-title-prefix convention:

| | Epic | Story |
|---|---|---|
| Title | prefix `Epic — <subject>` | no prefix |
| Label | `Epic` (orange `#F2994A`) | `Story` (green `#27AE60`) |
| Parent | none (top-level) | `parentId` = the Epic's UUID |

Resolve label UUIDs by name at use time:

```graphql
query { issueLabels(filter: { name: { in: ["Epic", "Story"] } }) { nodes { id name } } }
```

The label and the structural rule (prefix or parent) are applied **together**, never one without the other.

### Create an issue with assignee, labels, project

```graphql
mutation CreateIssueRich($input: IssueCreateInput!) {
  issueCreate(input: $input) {
    success
    issue { id identifier title }
  }
}
```

```json
{"input": {
  "teamId": "a57f5901-…",
  "title": "Investigate slow dashboard load",
  "assigneeId": "b59f3c26-…",
  "labelIds": ["<label-uuid-1>", "<label-uuid-2>"],
  "projectId": "<project-uuid>",
  "stateId": "<workflow-state-uuid>",
  "estimate": 3,
  "priority": 3
}}
```

### Update an issue (reassign, move state)

```graphql
mutation UpdateIssue($id: String!, $input: IssueUpdateInput!) {
  issueUpdate(id: $id, input: $input) {
    success
    issue { id identifier state { name } assignee { name } }
  }
}
```

```json
{"id": "<issue-uuid>",
 "input": { "assigneeId": "<user-uuid>", "stateId": "<state-uuid>" }}
```

`*UpdateInput` makes every field optional. Send only what changes.

### Delete an issue (soft, then hard)

```graphql
# Soft — moves to trash, keeps for 30 days.
mutation Trash($id: String!) {
  issueDelete(id: $id) { success }
}

# Hard — irreversible.
mutation Purge($id: String!) {
  issueDelete(id: $id, permanentlyDelete: true) { success }
}
```

Default is soft. Always confirm with the user before passing `permanentlyDelete: true`.

### Search issues by text

```graphql
query SearchIssues($q: String!) {
  searchIssues(term: $q, first: 20) {
    nodes { identifier title team { key } state { name } }
    totalCount
  }
}
```

`searchIssues` matches title and description. For filter-style search, use `issues(filter: …)` with `title: { containsIgnoreCase: … }`.

---

## Comments

### List comments on an issue

```graphql
query IssueComments($id: String!) {
  issue(id: $id) {
    comments(first: 50, orderBy: createdAt) {
      nodes {
        id body createdAt
        user { name email }
        reactions { id emoji user { name } }
      }
      pageInfo { hasNextPage endCursor }
    }
  }
}
```

### Create a comment on an issue

```graphql
mutation AddIssueComment($input: CommentCreateInput!) {
  commentCreate(input: $input) {
    success
    comment { id body createdAt user { name } }
  }
}
```

```json
{"input": {
  "issueId": "<issue-uuid>",
  "body": "Repro steps confirmed on staging. Attaching logs."
}}
```

`CommentCreateInput.body` accepts markdown. `bodyData` is the Prosemirror form — leave it for the agent's own use. To attach a comment to a project, document, or initiative instead, swap `issueId` for `projectId` / `documentContentId` / `initiativeId` etc.

### Delete a comment

```graphql
mutation DeleteComment($id: String!) {
  commentDelete(id: $id) { success }
}
```

`commentDelete` is hard delete (no trash).

---

## Projects

### List projects (active only)

```graphql
query ActiveProjects {
  projects(
    first: 50
    filter: { state: { in: ["started", "planned"] } }
  ) {
    nodes {
      id name slugId state progress
      lead { name }
      teams(first: 5) { nodes { key } }
      startDate targetDate
    }
  }
}
```

### Get a project with milestones and updates

```graphql
query GetProject($id: String!) {
  project(id: $id) {
    id name description state progress
    lead { name email }
    members(first: 20) { nodes { name } }
    teams(first: 10) { nodes { id key name } }
    issues(first: 50) {
      nodes { identifier title state { name } }
    }
    projectMilestones(first: 20) {
      nodes { id name targetDate sortOrder }
    }
    projectUpdates(first: 10, orderBy: createdAt) {
      nodes { id body health createdAt user { name } }
    }
  }
}
```

### Create a project

```graphql
mutation CreateProject($input: ProjectCreateInput!) {
  projectCreate(input: $input) {
    success
    project { id name slugId url }
  }
}
```

Required: `name` and **`teamIds`** (plural list — projects are M:N with teams):

```json
{"input": {
  "name": "Q3 onboarding revamp",
  "teamIds": ["<team-uuid-1>", "<team-uuid-2>"],
  "description": "Cut time-to-first-value from 12m to 5m.",
  "leadId": "<user-uuid>",
  "startDate": "2026-07-01",
  "targetDate": "2026-09-30",
  "priority": 2
}}
```

### Update / delete a project

`projectUpdate(id, input: ProjectUpdateInput)` and `projectDelete(id)`. Update accepts the same fields as Create with everything optional.

---

## Initiatives & Milestones

### List initiatives with linked projects

```graphql
query Initiatives {
  initiatives(first: 20) {
    nodes {
      id name description status
      owner { name }
      projects(first: 20) {
        nodes { id name state targetDate }
      }
    }
  }
}
```

### Create an initiative

```graphql
mutation CreateInitiative($input: InitiativeCreateInput!) {
  initiativeCreate(input: $input) {
    success
    initiative { id name }
  }
}
```

Required: `name`. Common optional fields: `description`, `ownerId`, `targetDate`, `color`, `icon`.

### List milestones for a project

```graphql
query ProjectMilestones($projectId: ID!) {
  project(id: $projectId) {
    projectMilestones(first: 20, orderBy: sortOrder) {
      nodes { id name description targetDate sortOrder }
    }
  }
}
```

`projectMilestoneCreate` and `projectMilestoneUpdate` mirror the project pattern — required fields are `name` and `projectId`.

---

## Teams, Users, Labels

### List teams ✓ live-tested

```graphql
query Teams { teams(first: 50) { nodes { id key name private } } }
```

### Get a team's workflow states ✓ usable

```graphql
query TeamStates($key: String!) {
  teams(filter: { key: { eq: $key } }) {
    nodes {
      id key name
      states(first: 20, orderBy: sortOrder) {
        nodes { id name type color position }
      }
    }
  }
}
```

`WorkflowStateType` enum: `triage`, `backlog`, `unstarted`, `started`, `completed`, `canceled`. Useful for status-driven filters.

### List users ✓ live-tested

```graphql
query Users {
  users(first: 100, filter: { active: { eq: true } }) {
    nodes { id name email displayName admin }
  }
}
```

### List labels for a team

```graphql
query TeamLabels($teamId: ID!) {
  team(id: $teamId) {
    labels(first: 100) {
      nodes { id name color description }
    }
  }
}
```

### Create a label

```graphql
mutation CreateLabel($input: IssueLabelCreateInput!) {
  issueLabelCreate(input: $input) {
    success
    issueLabel { id name color }
  }
}
```

```json
{"input": { "teamId": "<team-uuid>", "name": "needs-investigation", "color": "#FF6B6B" }}
```

Workspace-level labels: omit `teamId`.

---

## Cycles

### List cycles for a team

```graphql
query TeamCycles($key: String!) {
  teams(filter: { key: { eq: $key } }) {
    nodes {
      id key
      cycles(first: 10, orderBy: createdAt) {
        nodes {
          id number name
          startsAt endsAt
          progress completedIssueCountHistory
          issueCountHistory
        }
      }
    }
  }
}
```

The Linear MCP is read-only on cycles. For cycle **mutations** (`cycleCreate`, `cycleUpdate`, `cycleArchive`, `cycleShiftAll`, `cycleStartUpcomingCycleToday`), see `references/mutations-cheatsheet.md` (Phase 2).

---

## Project labels

### List project labels

```graphql
query ProjectLabels { projectLabels(first: 100) { nodes { id name color } } }
```

Project labels are workspace-level (unlike issue labels which can be team-scoped or workspace-scoped). The MCP has list-only; the API exposes `projectLabelCreate`, `projectLabelUpdate`, `projectLabelDelete`.

---

## Documents

### List documents in a project

```graphql
query ProjectDocs($projectId: ID!) {
  project(id: $projectId) {
    documents(first: 20) {
      nodes { id title icon updatedAt url }
    }
  }
}
```

### Create a document

```graphql
mutation CreateDoc($input: DocumentCreateInput!) {
  documentCreate(input: $input) {
    success
    document { id title url }
  }
}
```

Required: `title`. Attach to one of `projectId` / `initiativeId` / `teamId` / `issueId` / `cycleId`:

```json
{"input": {
  "title": "Onboarding playbook v2",
  "projectId": "<project-uuid>",
  "content": "# Goals\n\n…"
}}
```

### Get document content

```graphql
query GetDoc($id: String!) {
  document(id: $id) { id title content updatedAt url }
}
```

---

## Attachments

### List attachments on an issue

```graphql
query IssueAttachments($id: String!) {
  issue(id: $id) {
    attachments(first: 20) {
      nodes { id title subtitle url metadata }
    }
  }
}
```

### Create an attachment (link a URL to an issue)

```graphql
mutation Attach($input: AttachmentCreateInput!) {
  attachmentCreate(input: $input) {
    success
    attachment { id url title }
  }
}
```

```json
{"input": {
  "issueId": "<issue-uuid>",
  "url": "https://github.com/org/repo/pull/42",
  "title": "PR #42: fix token refresh",
  "subtitle": "Open · awaiting review"
}}
```

Attachments are how Linear surfaces external links (PRs, Figma, Notion). Run `linear.py introspect AttachmentCreateInput` for the full shape including `iconUrl` and `metadata`.

### Delete an attachment

```graphql
mutation Detach($id: String!) { attachmentDelete(id: $id) { success } }
```

Hard delete; the linked external resource is unaffected.

---

## Customers & Status updates

### List customers

```graphql
query Customers {
  customers(first: 50) {
    nodes { id name domains size status { name } }
  }
}
```

### Save a customer (create or update)

```graphql
mutation SaveCustomer($input: CustomerCreateInput!) {
  customerCreate(input: $input) {
    success
    customer { id name }
  }
}
```

For updates, use `customerUpdate(id, input)`. Required fields on create: typically `name`.

### Customer needs (save / delete)

```graphql
mutation SaveNeed($input: CustomerNeedCreateInput!) {
  customerNeedCreate(input: $input) {
    success
    customerNeed { id body priority }
  }
}

mutation DeleteNeed($id: String!) {
  customerNeedDelete(id: $id) { success }
}
```

Customer needs link customer feedback to issues / projects. Required: `customerId`, plus `body` and at least one of `issueId` / `projectId`.

### List status updates for a project

```graphql
query StatusUpdates($projectId: ID!) {
  project(id: $projectId) {
    projectUpdates(first: 20, orderBy: createdAt) {
      nodes { id body health createdAt user { name } }
    }
  }
}
```

### Post a status update

```graphql
mutation PostUpdate($input: ProjectUpdateCreateInput!) {
  projectUpdateCreate(input: $input) {
    success
    projectUpdate { id body health }
  }
}
```

```json
{"input": {
  "projectId": "<project-uuid>",
  "body": "Wk 3: hit the auth refactor milestone. Risk: scope creep on UI polish.",
  "health": "onTrack"
}}
```

`health` enum: `onTrack`, `atRisk`, `offTrack`.

### Delete a status update

```graphql
mutation DeleteUpdate($id: String!) {
  projectUpdateDelete(id: $id) { success }
}
```

---

## Patterns (cross-cutting)

### Resolve a human-readable identifier to a UUID

Many mutations want UUIDs. To go from `AGI-86` to a UUID:

```graphql
query Resolve($id: String!) {
  issue(id: $id) { id }       # 'id' arg accepts either UUID or "AGI-86"
}
```

Pass `"AGI-86"` as `$id`. Linear's `issue(id)` accepts both formats; the returned `id` is always the UUID.

### Paginate to exhaustion

Loop in code, not GraphQL:

```python
cursor = None
while True:
    body = post_graphql(QUERY, {"after": cursor}, api_key)
    page = body["data"]["issues"]
    yield from page["nodes"]
    if not page["pageInfo"]["hasNextPage"]:
        break
    cursor = page["pageInfo"]["endCursor"]
```

Set `first` low (20–50) on first call to keep latency snappy. Increase if you genuinely need more per page and the complexity headroom allows.

### Discover unknown fields

Don't guess — introspect:

```bash
python scripts/linear.py introspect IssueUpdateInput
python scripts/linear.py introspect WorkflowState
python scripts/linear.py introspect AttachmentCreateInput
```

One type, ~20–60 complexity points. Cheaper than a failed mutation round-trip.
