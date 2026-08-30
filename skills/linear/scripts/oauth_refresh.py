#!/usr/bin/env python3
"""Refresh a Linear OAuth access token without re-running the consent dance.

Linear access tokens expire after ~24h (despite the docs claiming 30 days for
`actor=app`). The auth-code response includes a `refresh_token` that can be
exchanged for a new access_token + refresh_token pair via the standard OAuth
refresh-grant flow. Run this script (manually or from cron) to keep
`LINEAR_API_KEY` valid indefinitely without browser interaction.

Required env (or pass via flags) — same shape `oauth_dance.py --write-env`
leaves you with:

    LINEAR_OAUTH_CLIENT_ID
    LINEAR_OAUTH_CLIENT_SECRET
    LINEAR_OAUTH_REFRESH_TOKEN

Usage:

    python scripts/oauth_refresh.py
    python scripts/oauth_refresh.py --env-file .env
    python scripts/oauth_refresh.py --no-write       # print only
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path
from typing import Any

import httpx
from dotenv import load_dotenv, set_key

TOKEN_URL = "https://api.linear.app/oauth/token"


def refresh_access_token(
    *,
    client_id: str,
    client_secret: str,
    refresh_token: str,
    timeout: float = 30.0,
) -> dict[str, Any]:
    """POST grant_type=refresh_token. Returns the parsed JSON body.

    Raises httpx.HTTPStatusError on a non-2xx so the caller can surface it.
    """
    response = httpx.post(
        TOKEN_URL,
        data={
            "client_id": client_id,
            "client_secret": client_secret,
            "refresh_token": refresh_token,
            "grant_type": "refresh_token",
        },
        timeout=timeout,
    )
    response.raise_for_status()
    return response.json()


def _format_duration(seconds: float) -> str:
    if seconds < 3600:
        return f"~{seconds / 60:.0f} min"
    if seconds < 86400:
        return f"~{seconds / 3600:.1f} hours"
    if seconds < 86400 * 60:
        return f"~{seconds / 86400:.1f} days"
    return f"~{seconds / (365 * 86400):.1f} years"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--env-file",
        default=".env",
        help="Path to the .env file to read from and update (default: .env)",
    )
    parser.add_argument(
        "--no-write",
        action="store_true",
        help="Print the new tokens instead of updating the .env file",
    )
    parser.add_argument(
        "--client-id",
        help="Override $LINEAR_OAUTH_CLIENT_ID",
    )
    parser.add_argument(
        "--client-secret",
        help="Override $LINEAR_OAUTH_CLIENT_SECRET",
    )
    parser.add_argument(
        "--refresh-token",
        help="Override $LINEAR_OAUTH_REFRESH_TOKEN",
    )
    args = parser.parse_args(argv)

    env_path = Path(args.env_file)
    if env_path.exists():
        load_dotenv(env_path, override=True)

    client_id = args.client_id or os.environ.get("LINEAR_OAUTH_CLIENT_ID")
    client_secret = args.client_secret or os.environ.get("LINEAR_OAUTH_CLIENT_SECRET")
    refresh_token = args.refresh_token or os.environ.get("LINEAR_OAUTH_REFRESH_TOKEN")

    missing = [
        name
        for name, value in (
            ("LINEAR_OAUTH_CLIENT_ID", client_id),
            ("LINEAR_OAUTH_CLIENT_SECRET", client_secret),
            ("LINEAR_OAUTH_REFRESH_TOKEN", refresh_token),
        )
        if not value
    ]
    if missing:
        print(
            f"error: missing required env vars: {', '.join(missing)}. "
            f"Run scripts/oauth_dance.py --write-env first to populate them.",
            file=sys.stderr,
        )
        return 2

    try:
        # type: ignore[arg-type] — narrowed by the missing-check above
        token = refresh_access_token(
            client_id=client_id,  # type: ignore[arg-type]
            client_secret=client_secret,  # type: ignore[arg-type]
            refresh_token=refresh_token,  # type: ignore[arg-type]
        )
    except httpx.HTTPStatusError as exc:
        body = exc.response.text[:500]
        print(
            f"error: refresh failed (HTTP {exc.response.status_code}): {body}",
            file=sys.stderr,
        )
        print(
            "If the refresh_token has been revoked or expired, you'll need "
            "to re-run scripts/oauth_dance.py to bootstrap a new pair.",
            file=sys.stderr,
        )
        return 1
    except httpx.HTTPError as exc:
        print(f"error: refresh failed: {exc}", file=sys.stderr)
        return 1

    new_access = token.get("access_token")
    new_refresh = token.get("refresh_token")
    expires_in = token.get("expires_in")

    if not new_access:
        print(f"error: refresh response had no access_token: {token}", file=sys.stderr)
        return 1

    if args.no_write:
        print(f"LINEAR_API_KEY={new_access}")
        if new_refresh:
            print(f"LINEAR_OAUTH_REFRESH_TOKEN={new_refresh}")
    else:
        env_path.touch(exist_ok=True)
        set_key(str(env_path), "LINEAR_API_KEY", new_access, quote_mode="never")
        if new_refresh:
            set_key(
                str(env_path),
                "LINEAR_OAUTH_REFRESH_TOKEN",
                new_refresh,
                quote_mode="never",
            )
        print(f"Wrote refreshed token(s) to {env_path.resolve()}", file=sys.stderr)

    if expires_in:
        print(
            f"  new access_token valid for {expires_in}s ({_format_duration(expires_in)})",
            file=sys.stderr,
        )
    print(
        f"  refresh_token rotated: {'yes' if new_refresh else 'no — keep old one'}",
        file=sys.stderr,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
