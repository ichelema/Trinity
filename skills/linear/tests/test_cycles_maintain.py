"""Mock-based unit tests for scripts/cycles_maintain.py.

Never hits Linear. Pure helpers tested directly; orchestration tested
through respx-mocked GraphQL endpoints.
"""

from __future__ import annotations

import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path

import httpx
import pytest
import respx

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import cycles_maintain as cm  # noqa: E402
import linear  # noqa: E402

# ─── Pure helpers ──────────────────────────────────────────────────────────────


def test_awst_midnight_utc_for_morning_awst() -> None:
    # 2026-05-08 09:00 AWST (= 01:00 UTC same day) → AWST midnight on 2026-05-08
    # is 16:00 UTC on 2026-05-07.
    now = datetime(2026, 5, 8, 1, 0, tzinfo=UTC)
    assert cm.awst_midnight_utc(now) == datetime(2026, 5, 7, 16, 0, tzinfo=UTC)


def test_awst_midnight_utc_for_late_evening_utc_crosses_awst_day() -> None:
    # 16:30 UTC on 2026-05-08 = 00:30 AWST on 2026-05-09
    now = datetime(2026, 5, 8, 16, 30, tzinfo=UTC)
    assert cm.awst_midnight_utc(now) == datetime(2026, 5, 8, 16, 0, tzinfo=UTC)


def test_daily_window_drift_zero() -> None:
    anchor = datetime(2026, 5, 8, 1, 0, tzinfo=UTC)
    starts, ends = cm.daily_window(anchor, day_offset=0, drift_ms=0)
    assert starts == datetime(2026, 5, 7, 16, 0, tzinfo=UTC)
    assert ends == datetime(2026, 5, 8, 16, 0, tzinfo=UTC)


def test_daily_window_drift_one_ms_offsets_start_and_pulls_end_back() -> None:
    anchor = datetime(2026, 5, 8, 1, 0, tzinfo=UTC)
    starts, ends = cm.daily_window(anchor, day_offset=1, drift_ms=1)
    # day-offset 1 = AWST 2026-05-09 00:00 = UTC 2026-05-08 16:00 + 1ms
    assert starts == datetime(2026, 5, 8, 16, 0, tzinfo=UTC) + timedelta(milliseconds=1)
    # Ends = next AWST midnight + (drift_ms - 1) ms = exactly 24h after start - drift_ms + (drift_ms - 1)
    # Practically: 1ms before the next cycle's startsAt (which would carry drift_ms=2).
    assert ends == datetime(2026, 5, 9, 16, 0, tzinfo=UTC)


def test_daily_window_drift_compounds_correctly() -> None:
    """Each cycle's startsAt > previous cycle's startsAt + 24h, strict."""
    anchor = datetime(2026, 5, 8, 1, 0, tzinfo=UTC)
    s0, _ = cm.daily_window(anchor, 0, drift_ms=0)
    s1, _ = cm.daily_window(anchor, 1, drift_ms=1)
    s2, _ = cm.daily_window(anchor, 2, drift_ms=2)
    assert s1 > s0 + timedelta(days=1)
    assert s2 > s1 + timedelta(days=1)


def test_fmt_dt_emits_milliseconds_z_suffix() -> None:
    d = datetime(2026, 5, 8, 16, 0, 0, microsecond=1000, tzinfo=UTC)
    assert cm.fmt_dt(d) == "2026-05-08T16:00:00.001Z"


def test_parse_dt_round_trips_with_fmt() -> None:
    s = "2026-05-08T16:00:00.123Z"
    assert cm.fmt_dt(cm.parse_dt(s)) == s


def _cycle(id_: str, starts: datetime, ends: datetime, completed: datetime | None = None) -> cm.Cycle:
    return cm.Cycle(id=id_, number=0, name=None, starts_at=starts, ends_at=ends, completed_at=completed)


def test_cycle_for_awst_date_within_tolerance() -> None:
    anchor = datetime(2026, 5, 8, 1, 0, tzinfo=UTC)
    target = cm.awst_midnight_utc(anchor)  # 2026-05-07 16:00 UTC
    near = _cycle("a", target + timedelta(milliseconds=42), target + timedelta(days=1))
    far = _cycle("b", target + timedelta(minutes=10), target + timedelta(days=1))
    assert cm.cycle_for_awst_date([near, far], anchor, 0) is near


def test_cycle_for_awst_date_returns_none_when_no_match() -> None:
    anchor = datetime(2026, 5, 8, 1, 0, tzinfo=UTC)
    far = _cycle("x",
                 datetime(2026, 1, 1, 0, 0, tzinfo=UTC),
                 datetime(2026, 1, 2, 0, 0, tzinfo=UTC))
    assert cm.cycle_for_awst_date([far], anchor, 0) is None


# ─── Orchestration via mocked GraphQL ─────────────────────────────────────────


@pytest.fixture
def api_key() -> str:
    return "lin_api_test_key"


def _resp(data: dict) -> httpx.Response:
    return httpx.Response(200, json={"data": data})


@respx.mock
def test_create_cycle_sends_expected_variables(api_key: str) -> None:
    captured: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        import json as _json
        captured.update(_json.loads(request.content))
        return _resp({"cycleCreate": {
            "success": True,
            "cycle": {
                "id": "c-1", "number": 13, "name": "Day 2026-05-09",
                "startsAt": "2026-05-08T16:00:00.000Z",
                "endsAt": "2026-05-09T16:00:00.000Z",
                "completedAt": None,
            },
        }})

    respx.post(linear.DEFAULT_URL).mock(side_effect=handler)

    starts = datetime(2026, 5, 8, 16, 0, tzinfo=UTC)
    ends = datetime(2026, 5, 9, 16, 0, tzinfo=UTC)
    new = cm.create_cycle(api_key, "team-uuid", "Day 2026-05-09", starts, ends)

    assert new.id == "c-1"
    assert new.starts_at == starts
    assert captured["variables"]["input"] == {
        "teamId": "team-uuid",
        "name": "Day 2026-05-09",
        "startsAt": "2026-05-08T16:00:00.000Z",
        "endsAt": "2026-05-09T16:00:00.000Z",
    }


@respx.mock
def test_close_cycle_sends_completed_at(api_key: str) -> None:
    captured: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        import json as _json
        captured.update(_json.loads(request.content))
        return _resp({"cycleUpdate": {
            "success": True,
            "cycle": {
                "id": "c-old", "number": 5,
                "startsAt": "2026-05-06T16:00:00.000Z",
                "endsAt": "2026-05-08T14:00:00.000Z",
                "completedAt": "2026-05-08T16:00:00.000Z",
            },
        }})

    respx.post(linear.DEFAULT_URL).mock(side_effect=handler)

    cm.close_cycle(api_key, "c-old", datetime(2026, 5, 8, 16, 0, tzinfo=UTC))

    assert captured["variables"] == {
        "id": "c-old",
        "input": {"completedAt": "2026-05-08T16:00:00.000Z"},
    }


@respx.mock
def test_move_issue_sends_cycle_id(api_key: str) -> None:
    captured: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        import json as _json
        captured.update(_json.loads(request.content))
        return _resp({"issueUpdate": {
            "success": True,
            "issue": {"id": "i-1", "identifier": "AGI-100", "cycle": {"id": "c-today"}},
        }})

    respx.post(linear.DEFAULT_URL).mock(side_effect=handler)

    cm.move_issue_to_cycle(api_key, "i-1", "c-today")

    assert captured["variables"] == {"id": "i-1", "input": {"cycleId": "c-today"}}


@respx.mock
def test_rollover_skips_today_and_already_completed(api_key: str) -> None:
    """Sanity: closed cycles and today's cycle aren't disturbed."""
    now = datetime(2026, 5, 8, 16, 30, tzinfo=UTC)
    today = _cycle("today",
                   datetime(2026, 5, 8, 16, 0, tzinfo=UTC),
                   datetime(2026, 5, 9, 16, 0, tzinfo=UTC))
    already_closed = _cycle("closed",
                            datetime(2026, 5, 6, 16, 0, tzinfo=UTC),
                            datetime(2026, 5, 7, 16, 0, tzinfo=UTC),
                            completed=datetime(2026, 5, 7, 16, 5, tzinfo=UTC))
    future = _cycle("future",
                    datetime(2026, 5, 10, 16, 0, tzinfo=UTC),
                    datetime(2026, 5, 11, 16, 0, tzinfo=UTC))

    # No requests should be issued because no cycle qualifies.
    summary = cm.rollover_open_cycles(api_key, [today, already_closed, future], today,
                                      carry_states=["started"], now=now, dry_run=False)
    assert summary == {}


@respx.mock
def test_rollover_moves_in_progress_then_closes(api_key: str) -> None:
    """An expired open cycle: query its in-progress issues, move them, then close."""
    now = datetime(2026, 5, 9, 16, 30, tzinfo=UTC)
    today = _cycle("today",
                   datetime(2026, 5, 9, 16, 0, tzinfo=UTC),
                   datetime(2026, 5, 10, 16, 0, tzinfo=UTC))
    stale = _cycle("stale",
                   datetime(2026, 5, 8, 16, 0, tzinfo=UTC),
                   datetime(2026, 5, 9, 16, 0, tzinfo=UTC))

    calls: list[dict] = []

    def handler(request: httpx.Request) -> httpx.Response:
        import json as _json
        body = _json.loads(request.content)
        calls.append(body)
        if "CycleIssues" in body["query"]:
            return _resp({"cycle": {"issues": {"nodes": [
                {"id": "i-1", "identifier": "AGI-100", "title": "wip", "state": {"type": "started"}},
                {"id": "i-2", "identifier": "AGI-101", "title": "wip2", "state": {"type": "started"}},
            ]}}})
        if "issueUpdate" in body["query"]:
            return _resp({"issueUpdate": {
                "success": True,
                "issue": {"id": body["variables"]["id"], "identifier": "x", "cycle": {"id": "today"}},
            }})
        if "cycleUpdate" in body["query"]:
            return _resp({"cycleUpdate": {
                "success": True,
                "cycle": {
                    "id": "stale", "number": 1,
                    "startsAt": "2026-05-08T16:00:00.000Z",
                    "endsAt": "2026-05-09T16:00:00.000Z",
                    "completedAt": "2026-05-09T16:30:00.000Z",
                },
            }})
        raise AssertionError(f"unexpected query: {body['query'][:80]}")

    respx.post(linear.DEFAULT_URL).mock(side_effect=handler)

    summary = cm.rollover_open_cycles(api_key, [today, stale], today,
                                      carry_states=["started"], now=now, dry_run=False)

    assert summary == {"stale": ["AGI-100", "AGI-101"]}
    # Order: query issues, move each, then close.
    op_kinds = []
    for c in calls:
        q = c["query"]
        if "CycleIssues" in q:
            op_kinds.append("query")
        elif "issueUpdate" in q:
            op_kinds.append("move")
        elif "cycleUpdate" in q:
            op_kinds.append("close")
    assert op_kinds == ["query", "move", "move", "close"]


def test_dry_run_rollover_makes_no_calls(api_key: str) -> None:
    now = datetime(2026, 5, 9, 16, 30, tzinfo=UTC)
    today = _cycle("today",
                   datetime(2026, 5, 9, 16, 0, tzinfo=UTC),
                   datetime(2026, 5, 10, 16, 0, tzinfo=UTC))
    stale = _cycle("stale",
                   datetime(2026, 5, 8, 16, 0, tzinfo=UTC),
                   datetime(2026, 5, 9, 16, 0, tzinfo=UTC))

    with respx.mock(assert_all_called=False) as router:
        # No mocks registered = any HTTP call would explode. We expect zero.
        summary = cm.rollover_open_cycles(api_key, [today, stale], today,
                                          carry_states=[], now=now, dry_run=True)
        assert summary == {"stale": []}
        assert router.calls.call_count == 0


# ─── New coverage: idempotency / drift / negative paths / auto-assign ─────────


def _populated_roadmap(anchor: datetime, days_ahead: int) -> list[cm.Cycle]:
    """Build a fully-populated roadmap (today + days_ahead future cycles).

    Starts at AWST midnight relative to `anchor`, with monotonically increasing
    +1ms drift per day to mirror the production drift workaround.
    """
    cycles: list[cm.Cycle] = []
    for offset in range(0, days_ahead + 1):
        drift = offset  # 0, 1, 2, … ms
        starts, ends = cm.daily_window(anchor, offset, drift_ms=drift)
        cycles.append(
            cm.Cycle(
                id=f"c-{offset}",
                number=offset,
                name=f"Day +{offset}",
                starts_at=starts,
                ends_at=ends,
                completed_at=None,
            )
        )
    return cycles


def test_ensure_roadmap_is_idempotent_when_already_populated(api_key: str) -> None:
    """Two consecutive ensure_roadmap calls on a populated roadmap → zero cycleCreate."""
    now = datetime(2026, 5, 8, 1, 0, tzinfo=UTC)
    cycles = _populated_roadmap(now, days_ahead=3)

    with respx.mock(assert_all_called=False) as router:
        # No routes registered → any HTTP call (cycleCreate or otherwise) explodes.
        first_today, first_created = cm.ensure_roadmap(
            api_key, "team-uuid", now, days_ahead=3, cycles=cycles, dry_run=False
        )
        second_today, second_created = cm.ensure_roadmap(
            api_key, "team-uuid", now, days_ahead=3, cycles=cycles, dry_run=False
        )

    assert first_created == []
    assert second_created == []
    assert first_today is not None and first_today.id == "c-0"
    assert second_today is not None and second_today.id == "c-0"
    assert router.calls.call_count == 0


@respx.mock
def test_ensure_roadmap_drift_accumulates_monotonically_when_creating_from_empty(
    api_key: str,
) -> None:
    """Empty roadmap + days_ahead=3 → 4 cycleCreate mutations, drift 0,1,2,3 ms."""
    import json as _json

    now = datetime(2026, 5, 8, 1, 0, tzinfo=UTC)  # AWST midnight = 2026-05-07 16:00 UTC
    create_calls: list[dict] = []
    counter = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        body = _json.loads(request.content)
        assert "cycleCreate" in body["query"], f"unexpected query: {body['query'][:80]}"
        create_calls.append(body)
        counter["n"] += 1
        idx = counter["n"] - 1
        return _resp({"cycleCreate": {
            "success": True,
            "cycle": {
                "id": f"new-{idx}",
                "number": 100 + idx,
                "name": f"Day +{idx}",
                "startsAt": body["variables"]["input"]["startsAt"],
                "endsAt": body["variables"]["input"]["endsAt"],
                "completedAt": None,
            },
        }})

    respx.post(linear.DEFAULT_URL).mock(side_effect=handler)

    today, created = cm.ensure_roadmap(
        api_key, "team-uuid", now, days_ahead=3, cycles=[], dry_run=False
    )

    assert today is not None
    assert len(created) == 4
    assert len(create_calls) == 4

    # AWST midnight for `now` = 2026-05-07 16:00 UTC. Each offset adds 24h; drift adds N ms.
    awst_midnight = datetime(2026, 5, 7, 16, 0, tzinfo=UTC)
    expected_drifts = [0, 1, 2, 3]
    for offset, expected_drift_ms in enumerate(expected_drifts):
        starts_str = create_calls[offset]["variables"]["input"]["startsAt"]
        starts_dt = cm.parse_dt(starts_str)
        base = awst_midnight + timedelta(days=offset)
        actual_drift_ms = round((starts_dt - base).total_seconds() * 1000)
        assert actual_drift_ms == expected_drift_ms, (
            f"offset {offset}: drift={actual_drift_ms}ms, expected {expected_drift_ms}ms"
        )


@pytest.mark.parametrize(
    "mutation_name,call,response",
    [
        (
            "cycleCreate",
            lambda api_key: cm.create_cycle(
                api_key, "team-uuid", "Day X",
                datetime(2026, 5, 8, 16, 0, tzinfo=UTC),
                datetime(2026, 5, 9, 16, 0, tzinfo=UTC),
            ),
            {"cycleCreate": {"success": False, "cycle": None}},
        ),
        (
            "cycleUpdate",
            lambda api_key: cm.close_cycle(
                api_key, "c-old",
                datetime(2026, 5, 8, 16, 0, tzinfo=UTC),
            ),
            {"cycleUpdate": {"success": False, "cycle": None}},
        ),
        (
            "issueUpdate",
            lambda api_key: cm.move_issue_to_cycle(api_key, "i-1", "c-today"),
            {"issueUpdate": {"success": False, "issue": None}},
        ),
    ],
    ids=["create", "update", "issueUpdate"],
)
@respx.mock
def test_mutation_success_false_raises_linear_error(
    api_key: str, mutation_name: str, call, response: dict,
) -> None:
    respx.post(linear.DEFAULT_URL).mock(return_value=_resp(response))
    with pytest.raises(linear.LinearError):
        call(api_key)


@respx.mock
def test_auto_assign_planned_emits_one_issue_update_per_unassigned(api_key: str) -> None:
    """Two unassigned issues → two issueUpdate mutations with cycleId=today."""
    import json as _json

    today = _cycle("c-today",
                   datetime(2026, 5, 8, 16, 0, tzinfo=UTC),
                   datetime(2026, 5, 9, 16, 0, tzinfo=UTC))
    calls: list[dict] = []

    def handler(request: httpx.Request) -> httpx.Response:
        body = _json.loads(request.content)
        calls.append(body)
        if "UnassignedIssues" in body["query"]:
            return _resp({"issues": {"nodes": [
                {"id": "i-1", "identifier": "AGI-200", "title": "a", "state": {"type": "unstarted"}},
                {"id": "i-2", "identifier": "AGI-201", "title": "b", "state": {"type": "started"}},
            ]}})
        if "issueUpdate" in body["query"]:
            return _resp({"issueUpdate": {
                "success": True,
                "issue": {
                    "id": body["variables"]["id"],
                    "identifier": "x",
                    "cycle": {"id": "c-today"},
                },
            }})
        raise AssertionError(f"unexpected query: {body['query'][:80]}")

    respx.post(linear.DEFAULT_URL).mock(side_effect=handler)

    moved = cm.auto_assign_planned(
        api_key, "team-uuid", today,
        states=["started", "unstarted"], dry_run=False,
    )

    assert moved == ["AGI-200", "AGI-201"]

    # Filter the issueUpdate calls and verify each carries cycleId=today + the right issue id.
    updates = [c for c in calls if "issueUpdate" in c["query"]]
    assert len(updates) == 2
    assert {u["variables"]["id"] for u in updates} == {"i-1", "i-2"}
    for u in updates:
        assert u["variables"]["input"] == {"cycleId": "c-today"}


def test_auto_assign_planned_dry_run_emits_no_mutations(api_key: str) -> None:
    """dry_run=True → list query is issued but no issueUpdate mutation fires."""
    import json as _json

    today = _cycle("c-today",
                   datetime(2026, 5, 8, 16, 0, tzinfo=UTC),
                   datetime(2026, 5, 9, 16, 0, tzinfo=UTC))

    calls: list[dict] = []

    def handler(request: httpx.Request) -> httpx.Response:
        body = _json.loads(request.content)
        calls.append(body)
        if "UnassignedIssues" in body["query"]:
            return _resp({"issues": {"nodes": [
                {"id": "i-1", "identifier": "AGI-200", "title": "a", "state": {"type": "started"}},
            ]}})
        raise AssertionError(f"unexpected query in dry-run: {body['query'][:80]}")

    with respx.mock(assert_all_called=False) as router:
        router.post(linear.DEFAULT_URL).mock(side_effect=handler)
        moved = cm.auto_assign_planned(
            api_key, "team-uuid", today,
            states=["started"], dry_run=True,
        )

    assert moved == ["AGI-200"]
    # Exactly one HTTP call: the list query. Zero mutations.
    assert len(calls) == 1
    assert "UnassignedIssues" in calls[0]["query"]
    assert not any("issueUpdate" in c["query"] for c in calls)
