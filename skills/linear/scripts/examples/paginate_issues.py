#!/usr/bin/env python3
"""Walk every issue in a team via cursor pagination.

Demonstrates the right way to exhaust a Connection field without setting
`first:` so high it trips complexity. See references/rate-limits.md and
references/schema-summary.md for the underlying pattern.

Usage:
    python scripts/examples/paginate_issues.py --team-key AGI
"""

from __future__ import annotations

import argparse
import os
import sys
from collections.abc import Iterator
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from dotenv import load_dotenv  # noqa: E402

from linear import post_graphql  # noqa: E402

PAGE_QUERY = """
query Page($key: String!, $after: String) {
  issues(
    first: 50
    after: $after
    filter: { team: { key: { eq: $key } } }
    orderBy: createdAt
  ) {
    nodes { identifier title state { name } }
    pageInfo { hasNextPage endCursor }
  }
}
"""


def iter_issues(team_key: str, api_key: str) -> Iterator[dict[str, Any]]:
    cursor: str | None = None
    while True:
        body = post_graphql(PAGE_QUERY, {"key": team_key, "after": cursor}, api_key)
        page = body["data"]["issues"]
        yield from page["nodes"]
        if not page["pageInfo"]["hasNextPage"]:
            return
        cursor = page["pageInfo"]["endCursor"]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--team-key", required=True)
    args = parser.parse_args()

    load_dotenv(override=True)
    api_key = os.environ.get("LINEAR_API_KEY")
    if not api_key:
        print("LINEAR_API_KEY not set", file=sys.stderr)
        return 2

    count = 0
    for issue in iter_issues(args.team_key, api_key):
        print(f"  {issue['identifier']:<10} [{issue['state']['name']:<12}] {issue['title']}")
        count += 1
    print(f"---\n{count} issues in team {args.team_key}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
