#!/usr/bin/env python3
"""Phase 0 smoke test: print the viewer's id/name/email and their first 5 assigned issues.

Run after the spike has a valid LINEAR_API_KEY in .env:

    python scripts/examples/list_my_issues.py
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

# Make `scripts.linear` importable when run as a script.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from dotenv import load_dotenv  # noqa: E402

from linear import post_graphql  # noqa: E402

QUERY = """
query Phase0Smoke {
  viewer {
    id
    name
    email
  }
  issues(first: 5, filter: { assignee: { isMe: { eq: true } } }) {
    nodes {
      identifier
      title
      state { name }
      team { key }
    }
  }
}
"""


def main() -> int:
    load_dotenv(override=True)
    api_key = os.environ.get("LINEAR_API_KEY")
    if not api_key:
        print("LINEAR_API_KEY not set", file=sys.stderr)
        return 2

    body = post_graphql(QUERY, {}, api_key)
    data = body["data"]
    viewer = data["viewer"]
    print(f"viewer: {viewer['name']} <{viewer['email']}>  id={viewer['id']}")
    print()
    print("first 5 of your assigned issues:")
    for issue in data["issues"]["nodes"]:
        team = issue["team"]["key"]
        state = issue["state"]["name"]
        print(f"  {issue['identifier']:<10} [{state:<12}] {team}: {issue['title']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
