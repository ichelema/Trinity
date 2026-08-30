# Prune archive — sqlite schema & query cookbook

Reference for the sqlite store that `/linear-prune` writes to. Load this file when you need to **query** the archive of previously-pruned issues, **debug** a failed prune, or **understand the schema**.

The archive lives at `./data/linear-archive/pruned.db` (override with `--db`). Failures go to `./data/linear-archive/failures.log` (append-only, tab-separated: `ISO-timestamp \t identifier \t message`).

---

## Schema

Five tables. `issues` is the spine; the rest hang off it by `issue_id` (or `parent_id` for `children`).

### `issues`

| Column | Type | Notes |
|---|---|---|
| `id` | TEXT PRIMARY KEY | Linear UUID (e.g. `2bb6ed30-…`) |
| `identifier` | TEXT UNIQUE NOT NULL | `AGI-187` |
| `title` | TEXT NOT NULL | |
| `description` | TEXT | Raw markdown body |
| `priority` | INTEGER | 0–4 (0=No, 1=Urgent, 4=Low) |
| `estimate` | REAL | Story points / hours |
| `team_key` | TEXT NOT NULL | e.g. `AGI` |
| `team_name` | TEXT | e.g. `AgileAndy` |
| `project_id`, `project_name` | TEXT | Null if unassigned |
| `cycle_id`, `cycle_number` | TEXT / INTEGER | Null if no cycle |
| `state_id`, `state_name`, `state_type` | TEXT | `state_type` ∈ `completed`, `canceled` |
| `assignee_id`, `assignee_name` | TEXT | |
| `creator_id`, `creator_name` | TEXT | |
| `parent_id`, `parent_identifier` | TEXT | Epic relationship |
| `url` | TEXT | Linear web URL |
| `created_at`, `updated_at`, `started_at`, `completed_at`, `canceled_at`, `archived_at` | TEXT | ISO-8601 UTC (Linear's `Z` suffix preserved) |
| `pruned_at` | TEXT NOT NULL | ISO-8601 UTC — local archive timestamp |

Indexes: `idx_issues_state(state_name)`, `idx_issues_team(team_key)`, `idx_issues_pruned(pruned_at)`.

### `labels`

| Column | Type | Notes |
|---|---|---|
| `issue_id` | TEXT | FK → `issues.id` |
| `label_id` | TEXT | Linear UUID |
| `label_name` | TEXT NOT NULL | |
| PRIMARY KEY | `(issue_id, label_id)` | |

### `comments`

| Column | Type | Notes |
|---|---|---|
| `id` | TEXT PRIMARY KEY | Linear comment UUID |
| `issue_id` | TEXT NOT NULL | FK → `issues.id` |
| `user_id`, `user_name` | TEXT | Author |
| `body` | TEXT NOT NULL | Markdown |
| `created_at` | TEXT | ISO-8601 UTC |

### `children`

| Column | Type | Notes |
|---|---|---|
| `parent_id` | TEXT NOT NULL | The pruned issue's id |
| `parent_identifier` | TEXT NOT NULL | e.g. `AGI-100` |
| `child_id`, `child_identifier` | TEXT NOT NULL | Each child of that parent |
| PRIMARY KEY | `(parent_id, child_id)` | |

Note: the **children rows are written from the parent's perspective**. If you prune an epic `AGI-100` that had three stories, you get three rows pointing back at the epic. If you prune one of those stories independently, it gets its own row in `issues` with `parent_identifier='AGI-100'`, but no `children` rows are added (a story has no children).

### `attachments`

| Column | Type | Notes |
|---|---|---|
| `id` | TEXT PRIMARY KEY | Linear attachment UUID |
| `issue_id` | TEXT NOT NULL | FK → `issues.id` |
| `title` | TEXT | Optional |
| `url` | TEXT NOT NULL | The actual link |
| `source_type` | TEXT | e.g. `github`, `slack` |
| `created_at` | TEXT | ISO-8601 UTC |

Metadata only — binary contents are **not** downloaded.

---

## Cookbook

```bash
# How many issues have we ever pruned, by state name?
sqlite3 data/linear-archive/pruned.db \
  "SELECT state_name, COUNT(*) FROM issues GROUP BY state_name ORDER BY 2 DESC;"
```

```bash
# Pretty tabular listing (header row + aligned columns instead of pipe-delimited).
sqlite3 -header -column data/linear-archive/pruned.db \
  "SELECT identifier, substr(title,1,60) AS title, state_name, completed_at, pruned_at
   FROM issues ORDER BY pruned_at DESC LIMIT 20;"
```

```bash
# Most recently pruned 20.
sqlite3 data/linear-archive/pruned.db \
  "SELECT identifier, state_name, title, pruned_at
   FROM issues ORDER BY pruned_at DESC LIMIT 20;"
```

```bash
# Full-record inspection — every column, one per line.
# Invaluable for fidelity audits (e.g. "did the description survive?").
sqlite3 data/linear-archive/pruned.db ".mode line" \
  "SELECT * FROM issues WHERE identifier='AGI-167';"
```

```bash
# What was pruned in today's session (vs pre-existing rows from prior runs)?
# Filters on pruned_at, which is the local archive timestamp — independent of
# Linear's completed_at. Useful for end-of-session reconciliation.
sqlite3 data/linear-archive/pruned.db \
  "SELECT identifier, state_name, title
   FROM issues WHERE pruned_at >= date('now','start of day')
   ORDER BY pruned_at DESC;"
```

```bash
# Find a pruned issue by title fragment.
sqlite3 data/linear-archive/pruned.db \
  "SELECT identifier, state_name, completed_at
   FROM issues WHERE title LIKE '%refresh token%';"
```

```bash
# All pruned issues that carried the 'bug' label.
sqlite3 data/linear-archive/pruned.db \
  "SELECT i.identifier, i.title
   FROM issues i JOIN labels l ON l.issue_id = i.id
   WHERE l.label_name = 'bug'
   ORDER BY i.completed_at DESC;"
```

```bash
# Reconstruct the comment thread on a pruned issue.
sqlite3 data/linear-archive/pruned.db \
  "SELECT user_name, created_at, body
   FROM comments
   WHERE issue_id = (SELECT id FROM issues WHERE identifier = 'AGI-180')
   ORDER BY created_at;"
```

```bash
# All children of a pruned epic.
sqlite3 data/linear-archive/pruned.db \
  "SELECT child_identifier FROM children
   WHERE parent_identifier = 'AGI-100'
   ORDER BY child_identifier;"
```

```bash
# Duplicates only — what was deduped to what?
# (Linear stores the "duplicate of" link as an IssueRelation, which we don't
# currently capture; for now, use state_name='Duplicate' and the description body.)
sqlite3 data/linear-archive/pruned.db \
  "SELECT identifier, title, description
   FROM issues WHERE state_name = 'Duplicate'
   ORDER BY pruned_at DESC;"
```

```bash
# Failed deletes — issues that were archived locally but Linear refused to delete.
# These still exist in Linear; re-running /linear-prune will retry the delete.
cat data/linear-archive/failures.log
```

---

## Idempotency

`archive_issue` uses `INSERT … ON CONFLICT(id) DO UPDATE`. Re-archiving the same Linear UUID (which only happens if the previous Linear delete failed) updates every column, including `pruned_at`, and **fully replaces** the child collections (labels / comments / children / attachments) — old rows are deleted first, then the current set is re-inserted. No stale or duplicated child rows.

You can therefore safely re-run `/linear-prune` after a partial failure. The archive will converge to the latest snapshot.

---

## Recovery

Linear deletes from `/linear-prune` use `issueDelete(permanentlyDelete: true)` — **there is no trash to recover from**. The sqlite archive is the only copy.

If you need to re-create a pruned issue in Linear:

1. Read the row: `SELECT * FROM issues WHERE identifier='AGI-180'`.
2. Read its labels, comments, children, attachments via the relations above.
3. Use the `linear` skill to `issueCreate` a new issue with the captured fields. You'll get a new identifier (Linear doesn't let you reuse old ones), so the original `AGI-180` is gone forever — only the body, labels, comments, and links survive.

There is **no automated re-import**. By design — if you needed it back automatically, you wouldn't have pruned it.

---

## Operational notes

- The archive grows over time. Even at 10 KB per issue with full comment threads, 10 000 pruned issues fits in ~100 MB. No retention policy is enforced.
- `data/linear-archive/` is gitignored. Back it up out-of-band if you care about its contents (it contains issue bodies and comment threads, which may include sensitive info).
- The `failures.log` file is append-only and small (one line per failure). Truncate it manually after addressing the underlying issue.
