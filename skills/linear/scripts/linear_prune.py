#!/usr/bin/env python3
"""Export Done / Cancelled / Duplicate issues to a local sqlite archive, then hard-delete them.

Keeps the workspace under Linear's 250-issue free-tier cap. The sqlite archive is
the only copy after delete — `issueDelete(permanentlyDelete: true)` is irreversible.

Two-phase: fetch all targets first (paginated query, read-only), then per issue:
  1. INSERT/UPSERT into sqlite, commit
  2. Call issueDelete(permanentlyDelete=true)
  3. On Linear failure: append to failures.log, keep going

The sqlite write commits before the Linear delete fires. A mid-run crash leaves
exported rows in the DB; re-running picks up any survivors (UPSERT-safe).

Usage:
  python scripts/linear_prune.py --team AGI --dry-run
  python scripts/linear_prune.py --team AGI --limit 1
  python scripts/linear_prune.py --team AGI --no-confirm
"""

from __future__ import annotations

import argparse
import os
import sqlite3
import sys
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Iterator

from dotenv import load_dotenv

sys.path.insert(0, str(Path(__file__).resolve().parent))
from linear import LinearError, post_graphql  # noqa: E402

DEFAULT_TEAM_KEY = "AGI"
DEFAULT_DB_PATH = Path("data/linear-archive/pruned.db")
PRUNE_STATE_TYPES = ["completed", "canceled"]  # captures Done, Cancelled, Duplicate
PAGE_SIZE = 25  # keeps per-query complexity well under the 10k budget

# ─── GraphQL ──────────────────────────────────────────────────────────────────

PRUNE_TARGETS_QUERY = """
query PruneTargets($teamKey: String!, $stateTypes: [String!]!, $first: Int!, $after: String) {
  issues(
    first: $first
    after: $after
    filter: {
      team:  { key:  { eq: $teamKey } }
      state: { type: { in: $stateTypes } }
    }
    orderBy: updatedAt
  ) {
    nodes {
      id identifier title description priority estimate url
      createdAt updatedAt startedAt completedAt canceledAt archivedAt
      team    { key name }
      project { id name }
      cycle   { id number }
      state   { id name type }
      assignee { id name }
      creator  { id name }
      parent   { id identifier }
      children { nodes { id identifier } }
      labels   { nodes { id name } }
      comments { nodes { id body createdAt user { id name } } }
      attachments { nodes { id title url sourceType createdAt } }
    }
    pageInfo { hasNextPage endCursor }
  }
}
"""

PURGE_MUTATION = """
mutation Purge($id: String!) {
  issueDelete(id: $id, permanentlyDelete: true) { success }
}
"""


# ─── SQLite schema ────────────────────────────────────────────────────────────

SCHEMA = """
CREATE TABLE IF NOT EXISTS issues (
  id                TEXT PRIMARY KEY,
  identifier        TEXT UNIQUE NOT NULL,
  title             TEXT NOT NULL,
  description       TEXT,
  priority          INTEGER,
  estimate          REAL,
  team_key          TEXT NOT NULL,
  team_name         TEXT,
  project_id        TEXT,
  project_name      TEXT,
  cycle_id          TEXT,
  cycle_number      INTEGER,
  state_id          TEXT,
  state_name        TEXT,
  state_type        TEXT,
  assignee_id       TEXT,
  assignee_name     TEXT,
  creator_id        TEXT,
  creator_name      TEXT,
  parent_id         TEXT,
  parent_identifier TEXT,
  url               TEXT,
  created_at        TEXT,
  updated_at        TEXT,
  started_at        TEXT,
  completed_at      TEXT,
  canceled_at       TEXT,
  archived_at       TEXT,
  pruned_at         TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS labels (
  issue_id   TEXT NOT NULL,
  label_id   TEXT NOT NULL,
  label_name TEXT NOT NULL,
  PRIMARY KEY (issue_id, label_id)
);
CREATE TABLE IF NOT EXISTS comments (
  id         TEXT PRIMARY KEY,
  issue_id   TEXT NOT NULL,
  user_id    TEXT,
  user_name  TEXT,
  body       TEXT NOT NULL,
  created_at TEXT
);
CREATE TABLE IF NOT EXISTS children (
  parent_id         TEXT NOT NULL,
  parent_identifier TEXT NOT NULL,
  child_id          TEXT NOT NULL,
  child_identifier  TEXT NOT NULL,
  PRIMARY KEY (parent_id, child_id)
);
CREATE TABLE IF NOT EXISTS attachments (
  id          TEXT PRIMARY KEY,
  issue_id    TEXT NOT NULL,
  title       TEXT,
  url         TEXT NOT NULL,
  source_type TEXT,
  created_at  TEXT
);
CREATE INDEX IF NOT EXISTS idx_issues_state  ON issues(state_name);
CREATE INDEX IF NOT EXISTS idx_issues_team   ON issues(team_key);
CREATE INDEX IF NOT EXISTS idx_issues_pruned ON issues(pruned_at);
"""


def init_db(conn: sqlite3.Connection) -> None:
    """Create tables and indexes if they don't yet exist. Idempotent."""
    conn.executescript(SCHEMA)
    conn.commit()


def open_db(db_path: Path) -> sqlite3.Connection:
    """Open (and init) the archive DB. Parent dir is created if missing."""
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path)
    conn.execute("PRAGMA foreign_keys = ON")
    init_db(conn)
    return conn


# ─── Fetch ────────────────────────────────────────────────────────────────────


def iter_prune_targets(
    api_key: str,
    team_key: str,
    state_types: list[str] = PRUNE_STATE_TYPES,
    page_size: int = PAGE_SIZE,
) -> Iterator[dict[str, Any]]:
    """Paginate the prune-target query, yielding each issue node."""
    cursor: str | None = None
    while True:
        body = post_graphql(
            PRUNE_TARGETS_QUERY,
            {
                "teamKey": team_key,
                "stateTypes": state_types,
                "first": page_size,
                "after": cursor,
            },
            api_key,
        )
        page = body["data"]["issues"]
        yield from page["nodes"]
        if not page["pageInfo"]["hasNextPage"]:
            return
        cursor = page["pageInfo"]["endCursor"]


# ─── Archive ──────────────────────────────────────────────────────────────────


def _get(node: dict[str, Any] | None, *path: str) -> Any:
    """Safe nested-dict read. Returns None if any link is null."""
    cur: Any = node
    for key in path:
        if cur is None:
            return None
        cur = cur.get(key)
    return cur


def archive_issue(conn: sqlite3.Connection, issue: dict[str, Any], pruned_at: str) -> None:
    """UPSERT the issue and its related rows. Caller commits the transaction."""
    conn.execute(
        """
        INSERT INTO issues (
            id, identifier, title, description, priority, estimate,
            team_key, team_name,
            project_id, project_name,
            cycle_id, cycle_number,
            state_id, state_name, state_type,
            assignee_id, assignee_name,
            creator_id, creator_name,
            parent_id, parent_identifier,
            url,
            created_at, updated_at, started_at, completed_at, canceled_at, archived_at,
            pruned_at
        ) VALUES (
            ?, ?, ?, ?, ?, ?,
            ?, ?,
            ?, ?,
            ?, ?,
            ?, ?, ?,
            ?, ?,
            ?, ?,
            ?, ?,
            ?,
            ?, ?, ?, ?, ?, ?,
            ?
        )
        ON CONFLICT(id) DO UPDATE SET
            title             = excluded.title,
            description       = excluded.description,
            priority          = excluded.priority,
            estimate          = excluded.estimate,
            team_key          = excluded.team_key,
            team_name         = excluded.team_name,
            project_id        = excluded.project_id,
            project_name      = excluded.project_name,
            cycle_id          = excluded.cycle_id,
            cycle_number      = excluded.cycle_number,
            state_id          = excluded.state_id,
            state_name        = excluded.state_name,
            state_type        = excluded.state_type,
            assignee_id       = excluded.assignee_id,
            assignee_name     = excluded.assignee_name,
            creator_id        = excluded.creator_id,
            creator_name      = excluded.creator_name,
            parent_id         = excluded.parent_id,
            parent_identifier = excluded.parent_identifier,
            url               = excluded.url,
            created_at        = excluded.created_at,
            updated_at        = excluded.updated_at,
            started_at        = excluded.started_at,
            completed_at      = excluded.completed_at,
            canceled_at       = excluded.canceled_at,
            archived_at       = excluded.archived_at,
            pruned_at         = excluded.pruned_at
        """,
        (
            issue["id"],
            issue["identifier"],
            issue["title"],
            issue.get("description"),
            issue.get("priority"),
            issue.get("estimate"),
            _get(issue, "team", "key"),
            _get(issue, "team", "name"),
            _get(issue, "project", "id"),
            _get(issue, "project", "name"),
            _get(issue, "cycle", "id"),
            _get(issue, "cycle", "number"),
            _get(issue, "state", "id"),
            _get(issue, "state", "name"),
            _get(issue, "state", "type"),
            _get(issue, "assignee", "id"),
            _get(issue, "assignee", "name"),
            _get(issue, "creator", "id"),
            _get(issue, "creator", "name"),
            _get(issue, "parent", "id"),
            _get(issue, "parent", "identifier"),
            issue.get("url"),
            issue.get("createdAt"),
            issue.get("updatedAt"),
            issue.get("startedAt"),
            issue.get("completedAt"),
            issue.get("canceledAt"),
            issue.get("archivedAt"),
            pruned_at,
        ),
    )

    issue_id = issue["id"]
    # Replace child collections wholesale on re-archive (UPSERT semantics).
    conn.execute("DELETE FROM labels      WHERE issue_id = ?", (issue_id,))
    conn.execute("DELETE FROM comments    WHERE issue_id = ?", (issue_id,))
    conn.execute("DELETE FROM children    WHERE parent_id = ?", (issue_id,))
    conn.execute("DELETE FROM attachments WHERE issue_id = ?", (issue_id,))

    for label in (_get(issue, "labels", "nodes") or []):
        conn.execute(
            "INSERT INTO labels (issue_id, label_id, label_name) VALUES (?, ?, ?)",
            (issue_id, label["id"], label["name"]),
        )

    for comment in (_get(issue, "comments", "nodes") or []):
        conn.execute(
            """INSERT INTO comments (id, issue_id, user_id, user_name, body, created_at)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (
                comment["id"],
                issue_id,
                _get(comment, "user", "id"),
                _get(comment, "user", "name"),
                comment.get("body", ""),
                comment.get("createdAt"),
            ),
        )

    for child in (_get(issue, "children", "nodes") or []):
        conn.execute(
            """INSERT INTO children (parent_id, parent_identifier, child_id, child_identifier)
               VALUES (?, ?, ?, ?)""",
            (issue_id, issue["identifier"], child["id"], child["identifier"]),
        )

    for att in (_get(issue, "attachments", "nodes") or []):
        conn.execute(
            """INSERT INTO attachments (id, issue_id, title, url, source_type, created_at)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (
                att["id"],
                issue_id,
                att.get("title"),
                att.get("url"),
                att.get("sourceType"),
                att.get("createdAt"),
            ),
        )


# ─── Purge ────────────────────────────────────────────────────────────────────


def purge_issue(api_key: str, issue_id: str) -> None:
    """Hard-delete an issue. Raises LinearError on failure."""
    body = post_graphql(PURGE_MUTATION, {"id": issue_id}, api_key)
    payload = body["data"]["issueDelete"]
    if not payload.get("success"):
        raise LinearError(f"issueDelete returned success=false for {issue_id}")


def log_failure(failures_path: Path, identifier: str, message: str) -> None:
    """Append a failure record to failures.log. Parent dir must already exist."""
    stamp = datetime.now(tz=UTC).isoformat(timespec="seconds")
    with failures_path.open("a", encoding="utf-8") as fh:
        fh.write(f"{stamp}\t{identifier}\t{message}\n")


# ─── Orchestration ────────────────────────────────────────────────────────────


def summarise(issues: list[dict[str, Any]]) -> Counter[str]:
    """Group by state.name → count. Used for the pre-purge breakdown."""
    return Counter(_get(i, "state", "name") or "(unknown)" for i in issues)


def format_summary(team_key: str, counts: Counter[str]) -> str:
    total = sum(counts.values())
    lines = [f"Prune targets for team {team_key}: {total} issue(s)"]
    for name, n in counts.most_common():
        lines.append(f"  {name:<20} {n}")
    return "\n".join(lines)


def confirm_or_abort(prompt: str) -> bool:
    """Read y/N from stdin. Anything not 'y' / 'yes' aborts."""
    try:
        reply = input(prompt).strip().lower()
    except EOFError:
        return False
    return reply in {"y", "yes"}


def run_prune(
    api_key: str,
    team_key: str,
    db_path: Path,
    dry_run: bool,
    limit: int | None,
    no_confirm: bool,
) -> tuple[int, int, int]:
    """Fetch → confirm → archive + purge. Returns (exported, deleted, failed)."""
    all_targets = list(iter_prune_targets(api_key, team_key))
    counts = summarise(all_targets)
    print(format_summary(team_key, counts), flush=True)

    targets = all_targets[:limit] if limit is not None else all_targets
    if limit is not None and limit < len(all_targets):
        print(f"(--limit {limit}: processing first {len(targets)} of {len(all_targets)})",
              flush=True)

    if not targets:
        print("Nothing to prune.", flush=True)
        return (0, 0, 0)

    if dry_run:
        print("(dry-run — no archive writes, no deletes)", flush=True)
        return (0, 0, 0)

    if not no_confirm:
        print(f"\nArchive to {db_path} and PERMANENTLY DELETE from Linear?", flush=True)
        if not confirm_or_abort("Type 'yes' to proceed: "):
            print("Aborted.", flush=True)
            return (0, 0, 0)

    conn = open_db(db_path)
    failures_path = db_path.parent / "failures.log"
    pruned_at = datetime.now(tz=UTC).isoformat(timespec="seconds")
    exported = deleted = failed = 0

    total = len(targets)
    for idx, issue in enumerate(targets, start=1):
        ident = issue["identifier"]
        state_name = _get(issue, "state", "name") or "?"
        try:
            archive_issue(conn, issue, pruned_at)
            conn.commit()
            exported += 1
        except sqlite3.Error as exc:
            conn.rollback()
            failed += 1
            log_failure(failures_path, ident, f"sqlite: {exc}")
            print(f"[{idx}/{total}] {ident} ({state_name}) — archive FAILED: {exc}",
                  file=sys.stderr)
            continue

        try:
            purge_issue(api_key, issue["id"])
            deleted += 1
            print(f"[{idx}/{total}] {ident} ({state_name}) — archived + deleted",
                  file=sys.stderr)
        except LinearError as exc:
            failed += 1
            log_failure(failures_path, ident, f"linear: {exc}")
            print(f"[{idx}/{total}] {ident} ({state_name}) — archive OK, delete FAILED: {exc}",
                  file=sys.stderr)

    conn.close()
    print(f"\nDone. exported={exported}  deleted={deleted}  failed={failed}")
    if failed:
        print(f"Failure log: {failures_path}")
    print(f"Archive:     {db_path}")
    return (exported, deleted, failed)


# ─── CLI ──────────────────────────────────────────────────────────────────────


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="linear_prune",
        description="Archive Done/Cancelled/Duplicate Linear issues to sqlite, then hard-delete.",
    )
    p.add_argument("--team", default=DEFAULT_TEAM_KEY,
                   help=f"Team key (default: {DEFAULT_TEAM_KEY})")
    p.add_argument("--db", type=Path, default=DEFAULT_DB_PATH,
                   help=f"SQLite archive path (default: {DEFAULT_DB_PATH})")
    p.add_argument("--dry-run", action="store_true",
                   help="Print the breakdown only; no archive writes, no deletes")
    p.add_argument("--limit", type=int, default=None,
                   help="Process at most N issues (useful for first live run)")
    p.add_argument("--no-confirm", action="store_true",
                   help="Skip the interactive confirmation prompt")
    return p


def main(argv: list[str] | None = None) -> int:
    load_dotenv(override=True)
    args = build_parser().parse_args(argv)

    api_key = os.environ.get("LINEAR_API_KEY")
    if not api_key:
        print("error: LINEAR_API_KEY not set", file=sys.stderr)
        return 2

    try:
        run_prune(
            api_key=api_key,
            team_key=args.team,
            db_path=args.db,
            dry_run=args.dry_run,
            limit=args.limit,
            no_confirm=args.no_confirm,
        )
        return 0
    except LinearError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
