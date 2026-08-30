"""Mock-based unit tests for scripts/linear_prune.py.

Never hits Linear. Uses respx to intercept httpx; sqlite goes to tmp_path.
"""

from __future__ import annotations

import json
import sqlite3
import sys
from collections import Counter
from pathlib import Path

import httpx
import pytest
import respx

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import linear  # noqa: E402
import linear_prune as lp  # noqa: E402


@pytest.fixture
def api_key() -> str:
    return "lin_api_test_key"


def _resp(data: dict) -> httpx.Response:
    return httpx.Response(200, json={"data": data})


def _issue(
    id_: str = "i-1",
    identifier: str = "AGI-1",
    state_name: str = "Done",
    state_type: str = "completed",
    **overrides,
) -> dict:
    """Build a fully-shaped issue node. Overrides patch any top-level key."""
    base = {
        "id": id_,
        "identifier": identifier,
        "title": f"Issue {identifier}",
        "description": "some markdown body",
        "priority": 2,
        "estimate": 3.0,
        "url": f"https://linear.app/x/{identifier}",
        "createdAt": "2026-01-01T00:00:00.000Z",
        "updatedAt": "2026-05-01T00:00:00.000Z",
        "startedAt": "2026-04-01T00:00:00.000Z",
        "completedAt": "2026-05-01T00:00:00.000Z",
        "canceledAt": None,
        "archivedAt": None,
        "team": {"key": "AGI", "name": "AgileAndy"},
        "project": {"id": "p-1", "name": "Phase 4"},
        "cycle": {"id": "c-1", "number": 12},
        "state": {"id": "s-1", "name": state_name, "type": state_type},
        "assignee": {"id": "u-1", "name": "Andy"},
        "creator": {"id": "u-1", "name": "Andy"},
        "parent": {"id": "i-parent", "identifier": "AGI-100"},
        "children": {"nodes": []},
        "labels": {"nodes": [{"id": "l-1", "name": "bug"}]},
        "comments": {"nodes": [
            {"id": f"cm-{id_}", "body": "lgtm", "createdAt": "2026-04-15T00:00:00.000Z",
             "user": {"id": "u-1", "name": "Andy"}},
        ]},
        "attachments": {"nodes": [
            {"id": f"a-{id_}", "title": "PR #42", "url": "https://github.com/x/y/pull/42",
             "sourceType": "github", "createdAt": "2026-04-15T00:00:00.000Z"},
        ]},
    }
    base.update(overrides)
    return base


# ─── Schema init ──────────────────────────────────────────────────────────────


def test_init_db_creates_all_tables(tmp_path: Path) -> None:
    db = tmp_path / "p.db"
    conn = lp.open_db(db)
    tables = {row[0] for row in conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table'"
    )}
    assert {"issues", "labels", "comments", "children", "attachments"} <= tables
    conn.close()


def test_init_db_is_idempotent(tmp_path: Path) -> None:
    db = tmp_path / "p.db"
    lp.open_db(db).close()
    # Re-open should not raise (CREATE TABLE IF NOT EXISTS).
    conn = lp.open_db(db)
    lp.init_db(conn)
    conn.close()


# ─── archive_issue ────────────────────────────────────────────────────────────


def test_archive_issue_writes_all_columns(tmp_path: Path) -> None:
    conn = lp.open_db(tmp_path / "p.db")
    lp.archive_issue(conn, _issue(), pruned_at="2026-05-14T00:00:00+00:00")
    conn.commit()

    row = conn.execute("SELECT * FROM issues WHERE identifier='AGI-1'").fetchone()
    cols = [d[0] for d in conn.execute("SELECT * FROM issues").description]
    rec = dict(zip(cols, row))

    assert rec["id"] == "i-1"
    assert rec["title"] == "Issue AGI-1"
    assert rec["team_key"] == "AGI"
    assert rec["project_name"] == "Phase 4"
    assert rec["cycle_number"] == 12
    assert rec["state_name"] == "Done"
    assert rec["state_type"] == "completed"
    assert rec["parent_identifier"] == "AGI-100"
    assert rec["pruned_at"] == "2026-05-14T00:00:00+00:00"

    labels = conn.execute("SELECT label_name FROM labels WHERE issue_id='i-1'").fetchall()
    assert labels == [("bug",)]

    comments = conn.execute("SELECT body, user_name FROM comments WHERE issue_id='i-1'").fetchall()
    assert comments == [("lgtm", "Andy")]

    attachments = conn.execute(
        "SELECT url, source_type FROM attachments WHERE issue_id='i-1'"
    ).fetchall()
    assert attachments == [("https://github.com/x/y/pull/42", "github")]


def test_archive_issue_handles_null_nested_fields(tmp_path: Path) -> None:
    conn = lp.open_db(tmp_path / "p.db")
    sparse = _issue(
        project=None, cycle=None, assignee=None, parent=None,
        description=None, estimate=None,
        children={"nodes": []}, labels={"nodes": []},
        comments={"nodes": []}, attachments={"nodes": []},
    )
    lp.archive_issue(conn, sparse, pruned_at="2026-05-14T00:00:00+00:00")
    conn.commit()

    row = conn.execute(
        "SELECT project_id, cycle_id, assignee_id, parent_id, description FROM issues"
    ).fetchone()
    assert row == (None, None, None, None, None)


def test_archive_issue_with_children_records_each(tmp_path: Path) -> None:
    conn = lp.open_db(tmp_path / "p.db")
    parent = _issue(id_="ep-1", identifier="AGI-100", children={"nodes": [
        {"id": "i-2", "identifier": "AGI-101"},
        {"id": "i-3", "identifier": "AGI-102"},
    ]})
    lp.archive_issue(conn, parent, pruned_at="2026-05-14T00:00:00+00:00")
    conn.commit()
    rows = conn.execute(
        "SELECT child_identifier FROM children WHERE parent_id='ep-1' ORDER BY child_identifier"
    ).fetchall()
    assert rows == [("AGI-101",), ("AGI-102",)]


def test_archive_issue_upserts_and_replaces_child_collections(tmp_path: Path) -> None:
    """Re-archiving the same issue updates the row and replaces (not appends to) children."""
    conn = lp.open_db(tmp_path / "p.db")
    first = _issue(labels={"nodes": [{"id": "l-1", "name": "bug"}]})
    lp.archive_issue(conn, first, pruned_at="2026-05-14T00:00:00+00:00")
    conn.commit()

    # Re-archive with different title + different label set.
    second = _issue(title="renamed", labels={"nodes": [{"id": "l-2", "name": "feature"}]})
    lp.archive_issue(conn, second, pruned_at="2026-05-14T00:01:00+00:00")
    conn.commit()

    # One row, updated.
    rows = conn.execute("SELECT title, pruned_at FROM issues WHERE id='i-1'").fetchall()
    assert rows == [("renamed", "2026-05-14T00:01:00+00:00")]

    # Labels fully replaced.
    labels = conn.execute(
        "SELECT label_name FROM labels WHERE issue_id='i-1' ORDER BY label_name"
    ).fetchall()
    assert labels == [("feature",)]


# ─── pagination ───────────────────────────────────────────────────────────────


@respx.mock
def test_iter_prune_targets_paginates(api_key: str) -> None:
    pages = [
        {"issues": {"nodes": [_issue(id_="i-a", identifier="AGI-1")],
                    "pageInfo": {"hasNextPage": True, "endCursor": "cur-1"}}},
        {"issues": {"nodes": [_issue(id_="i-b", identifier="AGI-2")],
                    "pageInfo": {"hasNextPage": False, "endCursor": None}}},
    ]
    seen_cursors: list[str | None] = []

    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        seen_cursors.append(body["variables"]["after"])
        return _resp(pages.pop(0))

    respx.post(linear.DEFAULT_URL).mock(side_effect=handler)

    issues = list(lp.iter_prune_targets(api_key, "AGI"))
    assert [i["identifier"] for i in issues] == ["AGI-1", "AGI-2"]
    assert seen_cursors == [None, "cur-1"]


# ─── purge ────────────────────────────────────────────────────────────────────


@respx.mock
def test_purge_issue_success(api_key: str) -> None:
    captured: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        captured.update(body)
        return _resp({"issueDelete": {"success": True}})

    respx.post(linear.DEFAULT_URL).mock(side_effect=handler)
    lp.purge_issue(api_key, "i-1")

    assert captured["variables"] == {"id": "i-1"}
    assert "permanentlyDelete: true" in captured["query"]


@respx.mock
def test_purge_issue_raises_when_success_false(api_key: str) -> None:
    respx.post(linear.DEFAULT_URL).mock(
        return_value=_resp({"issueDelete": {"success": False}})
    )
    with pytest.raises(linear.LinearError, match="success=false"):
        lp.purge_issue(api_key, "i-1")


# ─── summary ──────────────────────────────────────────────────────────────────


def test_summarise_groups_by_state_name() -> None:
    issues = [
        _issue(id_="i-1", identifier="AGI-1", state_name="Done", state_type="completed"),
        _issue(id_="i-2", identifier="AGI-2", state_name="Done", state_type="completed"),
        _issue(id_="i-3", identifier="AGI-3", state_name="Cancelled", state_type="canceled"),
        _issue(id_="i-4", identifier="AGI-4", state_name="Duplicate", state_type="canceled"),
    ]
    assert lp.summarise(issues) == Counter({"Done": 2, "Cancelled": 1, "Duplicate": 1})


def test_format_summary_renders_totals_and_breakdown() -> None:
    text = lp.format_summary("AGI", Counter({"Done": 5, "Duplicate": 2}))
    assert "AGI" in text
    assert "7 issue" in text
    assert "Done" in text and "5" in text
    assert "Duplicate" in text and "2" in text


# ─── run_prune orchestration ──────────────────────────────────────────────────


@respx.mock
def test_run_prune_dry_run_makes_no_writes_or_deletes(
    api_key: str, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    respx.post(linear.DEFAULT_URL).mock(
        return_value=_resp({"issues": {
            "nodes": [_issue()],
            "pageInfo": {"hasNextPage": False, "endCursor": None},
        }})
    )
    db = tmp_path / "p.db"
    exported, deleted, failed = lp.run_prune(
        api_key=api_key, team_key="AGI", db_path=db,
        dry_run=True, limit=None, no_confirm=True,
    )
    assert (exported, deleted, failed) == (0, 0, 0)
    assert not db.exists()  # No archive writes in dry-run.
    assert "dry-run" in capsys.readouterr().out


@respx.mock
def test_run_prune_end_to_end_archives_then_deletes(
    api_key: str, tmp_path: Path,
) -> None:
    issues = [_issue(id_="i-1", identifier="AGI-1"),
              _issue(id_="i-2", identifier="AGI-2", state_name="Duplicate", state_type="canceled")]
    calls: list[dict] = []

    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        calls.append(body)
        if "PruneTargets" in body["query"]:
            return _resp({"issues": {
                "nodes": issues,
                "pageInfo": {"hasNextPage": False, "endCursor": None},
            }})
        if "issueDelete" in body["query"]:
            return _resp({"issueDelete": {"success": True}})
        raise AssertionError(f"unexpected query: {body['query'][:80]}")

    respx.post(linear.DEFAULT_URL).mock(side_effect=handler)
    db = tmp_path / "p.db"

    exported, deleted, failed = lp.run_prune(
        api_key=api_key, team_key="AGI", db_path=db,
        dry_run=False, limit=None, no_confirm=True,
    )
    assert (exported, deleted, failed) == (2, 2, 0)

    # Both issues archived.
    conn = sqlite3.connect(db)
    rows = conn.execute("SELECT identifier, state_name FROM issues ORDER BY identifier").fetchall()
    conn.close()
    assert rows == [("AGI-1", "Done"), ("AGI-2", "Duplicate")]

    # Two delete mutations fired, one per issue.
    delete_ids = [
        c["variables"]["id"] for c in calls if "issueDelete" in c["query"]
    ]
    assert sorted(delete_ids) == ["i-1", "i-2"]


@respx.mock
def test_run_prune_logs_failure_when_linear_delete_fails(
    api_key: str, tmp_path: Path,
) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        if "PruneTargets" in body["query"]:
            return _resp({"issues": {
                "nodes": [_issue()],
                "pageInfo": {"hasNextPage": False, "endCursor": None},
            }})
        if "issueDelete" in body["query"]:
            return _resp({"issueDelete": {"success": False}})
        raise AssertionError("unexpected query")

    respx.post(linear.DEFAULT_URL).mock(side_effect=handler)
    db = tmp_path / "p.db"

    exported, deleted, failed = lp.run_prune(
        api_key=api_key, team_key="AGI", db_path=db,
        dry_run=False, limit=None, no_confirm=True,
    )
    # Archive succeeded; delete failed. Issue stays in Linear, but we have the row.
    assert exported == 1
    assert deleted == 0
    assert failed == 1

    conn = sqlite3.connect(db)
    n = conn.execute("SELECT count(*) FROM issues").fetchone()[0]
    conn.close()
    assert n == 1

    failures_log = db.parent / "failures.log"
    assert failures_log.exists()
    assert "AGI-1" in failures_log.read_text()


@respx.mock
def test_run_prune_limit_caps_processing(api_key: str, tmp_path: Path) -> None:
    issues = [_issue(id_=f"i-{i}", identifier=f"AGI-{i}") for i in range(1, 6)]

    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        if "PruneTargets" in body["query"]:
            return _resp({"issues": {
                "nodes": issues,
                "pageInfo": {"hasNextPage": False, "endCursor": None},
            }})
        return _resp({"issueDelete": {"success": True}})

    respx.post(linear.DEFAULT_URL).mock(side_effect=handler)
    db = tmp_path / "p.db"

    exported, deleted, _ = lp.run_prune(
        api_key=api_key, team_key="AGI", db_path=db,
        dry_run=False, limit=2, no_confirm=True,
    )
    assert exported == 2
    assert deleted == 2

    conn = sqlite3.connect(db)
    n = conn.execute("SELECT count(*) FROM issues").fetchone()[0]
    conn.close()
    assert n == 2


@respx.mock
def test_run_prune_empty_workspace_returns_zeros(
    api_key: str, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    respx.post(linear.DEFAULT_URL).mock(
        return_value=_resp({"issues": {
            "nodes": [],
            "pageInfo": {"hasNextPage": False, "endCursor": None},
        }})
    )
    db = tmp_path / "p.db"
    result = lp.run_prune(
        api_key=api_key, team_key="AGI", db_path=db,
        dry_run=False, limit=None, no_confirm=True,
    )
    assert result == (0, 0, 0)
    assert "Nothing to prune." in capsys.readouterr().out
