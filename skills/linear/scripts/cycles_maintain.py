#!/usr/bin/env python3
"""Maintain a rolling daily-cycle roadmap on a Linear team.

Idempotent. Run on a daily schedule (at or after AWST midnight = 16:00 UTC).

What it does, on each invocation:
  1. Compute today's AWST cycle window (16:00 UTC the day before → next 16:00 UTC).
  2. Ensure today + N forward daily cycles exist (default N=14). Missing cycles
     are created with cycleCreate.
  3. Roll over any non-completed cycle whose endsAt < now and that isn't today's:
     move issues whose state.type matches `--carry` to today's cycle, then close
     the old cycle (cycleUpdate completedAt=now).
  4. (Optional --auto-assign) Assign issues with cycle=null and matching states
     to today's cycle.

Linear quirks honoured:
  - cycleUpdate validates new_startsAt > previous_startsAt + 24h STRICTLY (equal
    is rejected). Daily cycles are staggered by +1 ms per day so we can adjust
    them later without hitting the validator.
  - Adjacent cycle updates run sequentially, never in parallel: the validator
    races on concurrent writes.
  - cycleArchive is one-way (no cycleUnarchive); we close (completedAt) instead.

Usage:
  python scripts/cycles_maintain.py --team AGI
  python scripts/cycles_maintain.py --team AGI --days-ahead 14 --dry-run
  python scripts/cycles_maintain.py --team AGI --auto-assign
"""

from __future__ import annotations

import argparse
import os
import sys
from dataclasses import dataclass
from datetime import UTC, datetime, time, timedelta, timezone
from pathlib import Path
from typing import Any

from dotenv import load_dotenv

sys.path.insert(0, str(Path(__file__).resolve().parent))
from linear import LinearError, post_graphql  # noqa: E402

AWST = timezone(timedelta(hours=8))
DEFAULT_DAYS_AHEAD = 14


@dataclass
class Cycle:
    id: str
    number: int
    name: str | None
    starts_at: datetime
    ends_at: datetime
    completed_at: datetime | None

    @classmethod
    def from_node(cls, n: dict[str, Any]) -> Cycle:
        return cls(
            id=n["id"],
            number=n["number"],
            name=n.get("name"),
            starts_at=parse_dt(n["startsAt"]),
            ends_at=parse_dt(n["endsAt"]),
            completed_at=parse_dt(n["completedAt"]) if n.get("completedAt") else None,
        )


def parse_dt(s: str) -> datetime:
    """Linear timestamps are ISO-8601 UTC with a trailing Z."""
    return datetime.fromisoformat(s.replace("Z", "+00:00"))


def fmt_dt(d: datetime) -> str:
    """Render a UTC datetime as ISO with millisecond precision and Z suffix."""
    if d.tzinfo is None:
        d = d.replace(tzinfo=UTC)
    d = d.astimezone(UTC)
    return d.strftime("%Y-%m-%dT%H:%M:%S.") + f"{d.microsecond // 1000:03d}Z"


def awst_midnight_utc(d: datetime) -> datetime:
    """UTC instant of AWST 00:00 on the AWST date `d` falls in.

    AWST has no DST so this is always 16:00 UTC of the previous calendar day.
    """
    awst = d.astimezone(AWST)
    midnight_awst = datetime.combine(awst.date(), time(0, 0), tzinfo=AWST)
    return midnight_awst.astimezone(UTC)


def daily_window(anchor: datetime, day_offset: int, drift_ms: int) -> tuple[datetime, datetime]:
    """Return (startsAt, endsAt) UTC for a daily cycle on (anchor's AWST date + day_offset).

    drift_ms is added to startsAt so consecutive cycles satisfy Linear's
    `new_startsAt > previous_startsAt + 24h` strict-inequality rule.
    """
    base = awst_midnight_utc(anchor) + timedelta(days=day_offset)
    starts = base + timedelta(milliseconds=drift_ms)
    if drift_ms == 0:
        ends = base + timedelta(days=1)
    else:
        # End just before the next cycle's start (which carries drift_ms+1).
        ends = base + timedelta(days=1) + timedelta(milliseconds=drift_ms - 1)
    return starts, ends


# ─── GraphQL operations ────────────────────────────────────────────────────────

TEAM_QUERY = """
query Team($key: String!) {
  teams(filter: { key: { eq: $key } }) {
    nodes { id key name cyclesEnabled }
  }
}
"""

CYCLES_QUERY = """
query Cycles($teamId: String!) {
  team(id: $teamId) {
    cycles(first: 100) {
      nodes { id number name startsAt endsAt completedAt }
    }
  }
}
"""

CYCLE_ISSUES_QUERY = """
query CycleIssues($cycleId: String!, $stateTypes: [String!]) {
  cycle(id: $cycleId) {
    issues(first: 250, filter: { state: { type: { in: $stateTypes } } }) {
      nodes { id identifier title state { type } }
    }
  }
}
"""

UNASSIGNED_ISSUES_QUERY = """
query UnassignedIssues($teamId: ID!, $stateTypes: [String!]) {
  issues(first: 250, filter: {
    team: { id: { eq: $teamId } }
    cycle: { null: true }
    state: { type: { in: $stateTypes } }
  }) {
    nodes { id identifier title state { type } }
  }
}
"""

CYCLE_CREATE = """
mutation Create($input: CycleCreateInput!) {
  cycleCreate(input: $input) {
    success
    cycle { id number name startsAt endsAt completedAt }
  }
}
"""

CYCLE_UPDATE = """
mutation Update($id: String!, $input: CycleUpdateInput!) {
  cycleUpdate(id: $id, input: $input) {
    success
    cycle { id number startsAt endsAt completedAt }
  }
}
"""

ISSUE_UPDATE = """
mutation Move($id: String!, $input: IssueUpdateInput!) {
  issueUpdate(id: $id, input: $input) {
    success
    issue { id identifier cycle { id } }
  }
}
"""


# ─── Operations ────────────────────────────────────────────────────────────────


def find_team(api_key: str, key: str) -> dict[str, Any]:
    body = post_graphql(TEAM_QUERY, {"key": key}, api_key)
    nodes = body["data"]["teams"]["nodes"]
    if not nodes:
        raise LinearError(f"team not found: {key}")
    return nodes[0]


def list_team_cycles(api_key: str, team_id: str) -> list[Cycle]:
    body = post_graphql(CYCLES_QUERY, {"teamId": team_id}, api_key)
    nodes = body["data"]["team"]["cycles"]["nodes"]
    return [Cycle.from_node(n) for n in nodes]


def list_cycle_issues(api_key: str, cycle_id: str, state_types: list[str]) -> list[dict[str, Any]]:
    body = post_graphql(CYCLE_ISSUES_QUERY, {"cycleId": cycle_id, "stateTypes": state_types}, api_key)
    return body["data"]["cycle"]["issues"]["nodes"]


def list_unassigned_issues(api_key: str, team_id: str, state_types: list[str]) -> list[dict[str, Any]]:
    body = post_graphql(UNASSIGNED_ISSUES_QUERY, {"teamId": team_id, "stateTypes": state_types}, api_key)
    return body["data"]["issues"]["nodes"]


def create_cycle(api_key: str, team_id: str, name: str, starts: datetime, ends: datetime) -> Cycle:
    body = post_graphql(
        CYCLE_CREATE,
        {"input": {"teamId": team_id, "name": name, "startsAt": fmt_dt(starts), "endsAt": fmt_dt(ends)}},
        api_key,
    )
    payload = body["data"]["cycleCreate"]
    if not payload.get("success"):
        raise LinearError(f"cycleCreate returned success=false for {name}")
    return Cycle.from_node(payload["cycle"])


def close_cycle(api_key: str, cycle_id: str, when: datetime) -> None:
    body = post_graphql(
        CYCLE_UPDATE,
        {"id": cycle_id, "input": {"completedAt": fmt_dt(when)}},
        api_key,
    )
    if not body["data"]["cycleUpdate"].get("success"):
        raise LinearError(f"cycleUpdate(close) returned success=false for {cycle_id}")


def move_issue_to_cycle(api_key: str, issue_id: str, cycle_id: str) -> None:
    body = post_graphql(
        ISSUE_UPDATE,
        {"id": issue_id, "input": {"cycleId": cycle_id}},
        api_key,
    )
    if not body["data"]["issueUpdate"].get("success"):
        raise LinearError(f"issueUpdate returned success=false for {issue_id}")


# ─── Roadmap maintenance ───────────────────────────────────────────────────────


def cycle_for_awst_date(cycles: list[Cycle], anchor: datetime, day_offset: int) -> Cycle | None:
    """Find a cycle whose startsAt is at AWST midnight of (anchor's AWST date + offset).

    Tolerant of the +1ms drift workaround: any cycle starting within a 5-minute
    window of the target AWST midnight is "the cycle for that day".
    """
    target = awst_midnight_utc(anchor) + timedelta(days=day_offset)
    tolerance = timedelta(minutes=5)
    for c in cycles:
        if abs(c.starts_at - target) <= tolerance:
            return c
    return None


def existing_drift_ms(cycle: Cycle, anchor: datetime, day_offset: int) -> int:
    """Drift of an existing cycle's startsAt relative to AWST midnight of its day."""
    target = awst_midnight_utc(anchor) + timedelta(days=day_offset)
    return round((cycle.starts_at - target).total_seconds() * 1000)


def ensure_roadmap(
    api_key: str,
    team_id: str,
    now: datetime,
    days_ahead: int,
    cycles: list[Cycle],
    dry_run: bool,
) -> tuple[Cycle | None, list[Cycle]]:
    """Ensure today + `days_ahead` daily cycles exist. Return (today, created)."""
    created: list[Cycle] = []

    today = cycle_for_awst_date(cycles, now, 0)
    if today is None:
        starts, ends = daily_window(now, 0, drift_ms=0)
        name = f"Day {starts.astimezone(AWST).date().isoformat()}"
        if dry_run:
            print(f"[dry-run] would create {name} starts={fmt_dt(starts)} ends={fmt_dt(ends)}")
        else:
            today = create_cycle(api_key, team_id, name, starts, ends)
            created.append(today)
            cycles = cycles + [today]

    drift_ms = 0
    if today is not None:
        drift_ms = max(drift_ms, existing_drift_ms(today, now, 0))

    for offset in range(1, days_ahead + 1):
        existing = cycle_for_awst_date(cycles, now, offset)
        if existing is not None:
            drift_ms = max(drift_ms, existing_drift_ms(existing, now, offset))
            continue
        drift_ms += 1
        starts, ends = daily_window(now, offset, drift_ms)
        name = f"Day {starts.astimezone(AWST).date().isoformat()}"
        if dry_run:
            print(f"[dry-run] would create {name} starts={fmt_dt(starts)} ends={fmt_dt(ends)}")
            continue
        new = create_cycle(api_key, team_id, name, starts, ends)
        created.append(new)
        cycles = cycles + [new]

    return today, created


def rollover_open_cycles(
    api_key: str,
    cycles: list[Cycle],
    today: Cycle,
    carry_states: list[str],
    now: datetime,
    dry_run: bool,
) -> dict[str, list[str]]:
    """Close any non-completed cycle whose endsAt < now and isn't today's.

    Issues whose state.type ∈ carry_states are reassigned to today's cycle first.
    Returns {old_cycle_id: [moved_issue_identifiers]}.
    """
    summary: dict[str, list[str]] = {}
    for c in sorted(cycles, key=lambda x: x.starts_at):
        if c.id == today.id:
            continue
        if c.completed_at is not None:
            continue
        if c.ends_at >= now:
            continue
        moved: list[str] = []
        if carry_states:
            for issue in list_cycle_issues(api_key, c.id, carry_states):
                if dry_run:
                    print(f"[dry-run] move {issue['identifier']} ({issue['state']['type']}) → today")
                else:
                    move_issue_to_cycle(api_key, issue["id"], today.id)
                moved.append(issue["identifier"])
        if dry_run:
            print(f"[dry-run] close cycle #{c.number} ({c.id}) at {fmt_dt(now)}")
        else:
            close_cycle(api_key, c.id, now)
        summary[c.id] = moved
    return summary


def auto_assign_planned(
    api_key: str,
    team_id: str,
    today: Cycle,
    states: list[str],
    dry_run: bool,
) -> list[str]:
    """Assign issues with no cycle (matching `states`) to today. Returns moved identifiers."""
    moved: list[str] = []
    for issue in list_unassigned_issues(api_key, team_id, states):
        if dry_run:
            print(f"[dry-run] assign {issue['identifier']} ({issue['state']['type']}) → today")
        else:
            move_issue_to_cycle(api_key, issue["id"], today.id)
        moved.append(issue["identifier"])
    return moved


# ─── CLI ──────────────────────────────────────────────────────────────────────


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="cycles_maintain",
        description="Daily-cycle roadmap maintainer for a Linear team (AWST-aligned).",
    )
    p.add_argument("--team", required=True, help="Team key, e.g. AGI")
    p.add_argument("--days-ahead", type=int, default=DEFAULT_DAYS_AHEAD,
                   help=f"Future daily cycles to maintain (default: {DEFAULT_DAYS_AHEAD})")
    p.add_argument("--carry", default="started",
                   help="State types to carry forward on rollover (default: started). "
                        "Comma-separated. Empty string disables carry.")
    p.add_argument("--auto-assign", action="store_true",
                   help="Also assign cycle-less issues in --assign-states to today's cycle")
    p.add_argument("--assign-states", default="started,unstarted",
                   help="State types eligible for auto-assignment (default: started,unstarted)")
    p.add_argument("--dry-run", action="store_true",
                   help="Don't mutate; print what would happen")
    p.add_argument("--now",
                   help="Override 'now' as ISO-8601 UTC for testing (default: actual UTC now)")
    return p


def main(argv: list[str] | None = None) -> int:
    load_dotenv(override=True)
    args = build_parser().parse_args(argv)

    api_key = os.environ.get("LINEAR_API_KEY")
    if not api_key:
        print("error: LINEAR_API_KEY not set", file=sys.stderr)
        return 2

    now = parse_dt(args.now) if args.now else datetime.now(tz=UTC)

    try:
        team = find_team(api_key, args.team)
        team_id = team["id"]
        cycles = list_team_cycles(api_key, team_id)

        carry_states = [s.strip() for s in args.carry.split(",") if s.strip()]
        assign_states = [s.strip() for s in args.assign_states.split(",") if s.strip()]

        today, created = ensure_roadmap(api_key, team_id, now, args.days_ahead, cycles, args.dry_run)
        if today is None and not args.dry_run:
            raise LinearError("today's cycle could not be located after roadmap pass")

        cycles_after = cycles + created
        rollovers: dict[str, list[str]] = {}
        if today is not None:
            rollovers = rollover_open_cycles(api_key, cycles_after, today, carry_states, now, args.dry_run)

        moved_for_assign: list[str] = []
        if args.auto_assign and today is not None:
            moved_for_assign = auto_assign_planned(api_key, team_id, today, assign_states, args.dry_run)

        print(f"team: {args.team} (cyclesEnabled={team.get('cyclesEnabled')})")
        if today is not None:
            print(f"today's cycle: {today.id} ({fmt_dt(today.starts_at)} → {fmt_dt(today.ends_at)})")
        print(f"created: {len(created)} new cycle(s)")
        for c in created:
            print(f"  + #{c.number} {fmt_dt(c.starts_at)} → {fmt_dt(c.ends_at)}")
        print(f"rolled over: {len(rollovers)} stale cycle(s)")
        for old_id, issues in rollovers.items():
            print(f"  x {old_id}: moved {len(issues)} issue(s) — {', '.join(issues) if issues else '(none)'}")
        if args.auto_assign:
            print(f"auto-assigned: {len(moved_for_assign)} issue(s) → today")
        if args.dry_run:
            print("(dry-run — no mutations sent)")

        return 0
    except LinearError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
