#!/usr/bin/env python3
"""Mint a Linear `client_credentials` access token — bot identity, no user.

This is the **recommended** auth flow when you (the developer) want your
own OAuth app to talk to Linear as itself. There is no user, no browser,
no refresh dance — the app authenticates with its own `client_id` +
`client_secret` and gets back a token that represents the app.

Compared to the auth-code OAuth dance (`scripts/oauth_dance.py`):

    - No browser interaction. Cron-runnable.
    - Token represents the app (e.g. "ClaudeBot") not you.
    - Lifetime ~30 days vs ~24h for user-scoped auth-code tokens.
    - Higher rate limit (5,000 req/hr observed vs 2,500 personal key).
    - No refresh_token — re-run this script to mint a fresh token at
      any time. There's no consent state to preserve.

Setup prerequisite: in Linear's OAuth app **Edit application** screen,
toggle on **Client credentials** (the docs link points at OAuth's
client_credentials grant). Save. Then run this.

Required env (or pass via flags):

    LINEAR_OAUTH_CLIENT_ID
    LINEAR_OAUTH_CLIENT_SECRET

Usage:

    python scripts/client_credentials_token.py
    python scripts/client_credentials_token.py --no-write    # print only
    python scripts/client_credentials_token.py --scope read  # narrower scope
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
DEFAULT_SCOPES = ("read", "write")


def mint_app_token(
    *,
    client_id: str,
    client_secret: str,
    scopes: tuple[str, ...] | list[str] = DEFAULT_SCOPES,
    timeout: float = 30.0,
) -> dict[str, Any]:
    """POST grant_type=client_credentials. Returns the parsed JSON body.

    Raises httpx.HTTPStatusError on a non-2xx so the caller can surface it.
    """
    response = httpx.post(
        TOKEN_URL,
        data={
            "client_id": client_id,
            "client_secret": client_secret,
            "grant_type": "client_credentials",
            "scope": ",".join(scopes),
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
        help="Path to read client_id/client_secret from and write token to (default: .env)",
    )
    parser.add_argument(
        "--no-write",
        action="store_true",
        help="Print the new token instead of updating the .env file",
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
        "--scope",
        nargs="+",
        default=list(DEFAULT_SCOPES),
        help="Scopes to request (default: read write)",
    )
    args = parser.parse_args(argv)

    env_path = Path(args.env_file)
    if env_path.exists():
        load_dotenv(env_path, override=True)

    client_id = args.client_id or os.environ.get("LINEAR_OAUTH_CLIENT_ID")
    client_secret = args.client_secret or os.environ.get("LINEAR_OAUTH_CLIENT_SECRET")

    missing = [
        name
        for name, value in (
            ("LINEAR_OAUTH_CLIENT_ID", client_id),
            ("LINEAR_OAUTH_CLIENT_SECRET", client_secret),
        )
        if not value
    ]
    if missing:
        print(
            f"error: missing required env vars: {', '.join(missing)}. "
            f"See references/auth.md for the OAuth-app setup steps.",
            file=sys.stderr,
        )
        return 2

    try:
        token = mint_app_token(
            client_id=client_id,  # type: ignore[arg-type]
            client_secret=client_secret,  # type: ignore[arg-type]
            scopes=tuple(args.scope),
        )
    except httpx.HTTPStatusError as exc:
        body = exc.response.text[:500]
        print(
            f"error: client_credentials request failed (HTTP {exc.response.status_code}): {body}",
            file=sys.stderr,
        )
        if exc.response.status_code == 400:
            print(
                "If the response mentions 'unsupported_grant_type', toggle the "
                "Client credentials switch ON in your OAuth app's Edit page in "
                "Linear, then retry.",
                file=sys.stderr,
            )
        return 1
    except httpx.HTTPError as exc:
        print(f"error: request failed: {exc}", file=sys.stderr)
        return 1

    access_token = token.get("access_token")
    expires_in = token.get("expires_in")
    scope = token.get("scope")

    if not access_token:
        print(f"error: response had no access_token: {token}", file=sys.stderr)
        return 1

    if args.no_write:
        print(f"LINEAR_API_KEY={access_token}")
    else:
        env_path.touch(exist_ok=True)
        set_key(str(env_path), "LINEAR_API_KEY", access_token, quote_mode="never")
        print(f"Wrote token to {env_path.resolve()}", file=sys.stderr)

    if scope:
        print(f"  scope:      {scope}", file=sys.stderr)
    if expires_in:
        print(
            f"  expires_in: {expires_in}s ({_format_duration(expires_in)})",
            file=sys.stderr,
        )
    print("  re-mint:    rerun this script any time to get a fresh token.", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
