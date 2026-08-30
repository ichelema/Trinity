#!/usr/bin/env python3
"""Subscribe to Linear events by creating a webhook.

Demonstrates the canonical Phase 2 use case: agent provisions its own
webhook subscription so it can react to events instead of polling.

Usage:
    python scripts/examples/subscribe_webhook.py \\
        --url https://your-receiver.example.com/linear \\
        --label "triage agent" \\
        --resource-types Issue Comment \\
        --team-key AGI

Captures the webhook secret to stdout exactly once — Linear will not
return it again. Pipe it to your secret store immediately.
"""

from __future__ import annotations

import argparse
import json
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

CREATE_WEBHOOK = """
mutation Create($input: WebhookCreateInput!) {
  webhookCreate(input: $input) {
    success
    webhook {
      id label url enabled
      resourceTypes
      team { key }
      secret
    }
  }
}
"""


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url", required=True, help="HTTPS endpoint that will receive payloads")
    parser.add_argument("--label", required=True, help="Human-readable label")
    parser.add_argument(
        "--resource-types",
        nargs="+",
        required=True,
        help='Resource types to subscribe to, e.g. Issue Comment Project (case-sensitive, singular)',
    )
    parser.add_argument(
        "--team-key",
        help="Optional: scope to one team. Omit for workspace-wide on all public teams.",
    )
    parser.add_argument(
        "--enabled",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Provision in disabled state (default: enabled)",
    )
    args = parser.parse_args()

    load_dotenv(override=True)
    api_key = os.environ.get("LINEAR_API_KEY")
    if not api_key:
        print("LINEAR_API_KEY not set", file=sys.stderr)
        return 2

    payload: dict[str, object] = {
        "url": args.url,
        "label": args.label,
        "resourceTypes": args.resource_types,
        "enabled": args.enabled,
    }

    if args.team_key:
        teams = post_graphql(RESOLVE_TEAM, {"key": args.team_key}, api_key)["data"]["teams"][
            "nodes"
        ]
        if not teams:
            print(f"team not found: {args.team_key}", file=sys.stderr)
            return 1
        payload["teamId"] = teams[0]["id"]
    else:
        payload["allPublicTeams"] = True

    body = post_graphql(CREATE_WEBHOOK, {"input": payload}, api_key)
    result = body["data"]["webhookCreate"]
    if not result["success"]:
        print("webhookCreate returned success: false", file=sys.stderr)
        return 1

    webhook = result["webhook"]
    print(json.dumps(webhook, indent=2))
    print(
        "\n*** CAPTURE THE SECRET ABOVE — it will not be returned again. ***",
        file=sys.stderr,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
