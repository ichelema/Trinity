#!/usr/bin/env python3
"""Create an issue from the command line, then read it back.

Usage:
    python scripts/examples/create_issue.py \\
        --team-key AGI \\
        --title "auth: 401 on token refresh" \\
        --description "Reproduces on Safari 17.x." \\
        --priority 2

Demonstrates the canonical write path:
    1. resolve a human-readable team key to a UUID,
    2. run the mutation with typed variables,
    3. read the result back.
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from dotenv import load_dotenv  # noqa: E402

from linear import post_graphql  # noqa: E402

RESOLVE_TEAM = """
query ResolveTeam($key: String!) {
  teams(filter: { key: { eq: $key } }) { nodes { id key } }
}
"""

CREATE_ISSUE = """
mutation Create($input: IssueCreateInput!) {
  issueCreate(input: $input) {
    success
    issue { id identifier title priority url state { name } }
  }
}
"""


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--team-key", required=True, help="Team key, e.g. AGI")
    parser.add_argument("--title", required=True)
    parser.add_argument("--description", default="")
    parser.add_argument(
        "--priority",
        type=int,
        choices=[0, 1, 2, 3, 4],
        default=0,
        help="0=none, 1=urgent, 2=high, 3=medium, 4=low",
    )
    args = parser.parse_args()

    load_dotenv(override=True)
    api_key = os.environ.get("LINEAR_API_KEY")
    if not api_key:
        print("LINEAR_API_KEY not set", file=sys.stderr)
        return 2

    teams = post_graphql(RESOLVE_TEAM, {"key": args.team_key}, api_key)["data"]["teams"]["nodes"]
    if not teams:
        print(f"team not found: {args.team_key}", file=sys.stderr)
        return 1
    team_id = teams[0]["id"]

    payload = {
        "input": {
            "teamId": team_id,
            "title": args.title,
            "description": args.description,
            "priority": args.priority,
        }
    }
    body = post_graphql(CREATE_ISSUE, payload, api_key)
    issue = body["data"]["issueCreate"]["issue"]
    print(f"created {issue['identifier']} (priority {issue['priority']})  {issue['url']}")
    print(f"  state: {issue['state']['name']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
