#!/usr/bin/env python3
"""Run Linear's OAuth `actor=app` install flow and print the access token.

Why this exists: a personal API key acts as a specific user. Every action an
agent runs gets attributed to that user in Linear's UI and audit log. With
`actor=app`, the same actions are attributed to the registered app — the bot
gets its own identity. See `references/auth.md` for the setup steps and the
trade-offs.

How it works:

    1. Spin up a one-shot HTTP server on 127.0.0.1:<port>/callback.
    2. Open the browser to Linear's authorize URL with actor=app.
    3. User clicks accept; Linear redirects back to the local server.
    4. Server captures the auth code, exchanges it for a token, prints it.

Required env (or pass via flags):

    LINEAR_OAUTH_CLIENT_ID       — public, from Linear's OAuth app settings
    LINEAR_OAUTH_CLIENT_SECRET   — secret, from same screen
    LINEAR_OAUTH_REDIRECT_URI    — must match what's registered, default
                                   http://localhost:8765/callback

Usage:

    python scripts/oauth_dance.py
    python scripts/oauth_dance.py --scopes read write issues:create
    python scripts/oauth_dance.py --port 9000
    python scripts/oauth_dance.py --no-actor-app   # user-scoped token

The token is printed in a copy-paste-ready form for `.env`:

    LINEAR_API_KEY=lin_oauth_…
"""

from __future__ import annotations

import argparse
import http.server
import os
import secrets
import sys
import threading
import webbrowser
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlencode, urlparse

import httpx
from dotenv import load_dotenv, set_key

AUTHORIZE_URL = "https://linear.app/oauth/authorize"
TOKEN_URL = "https://api.linear.app/oauth/token"

DEFAULT_REDIRECT_URI = "http://localhost:8765/callback"
DEFAULT_SCOPES = ("read", "write")

_SUCCESS_PAGE = """<!doctype html>
<html><head><meta charset="utf-8"><title>Linear OAuth complete</title>
<style>body{font:16px/1.4 system-ui;max-width:32rem;margin:4rem auto;color:#222}
h1{font-weight:600}code{background:#f4f4f5;padding:.15em .35em;border-radius:.2rem}</style>
</head><body>
<h1>Authorisation complete</h1>
<p>You can close this tab and return to your terminal — the access token has been captured.</p>
</body></html>
""".encode()

_ERROR_PAGE = (
    "<!doctype html>"
    "<html><head><meta charset=\"utf-8\"><title>Linear OAuth error</title></head>"
    "<body><h1>Authorisation failed</h1><p>Check the terminal for details.</p></body></html>"
).encode()


@dataclass
class _Capture:
    """Shared state between the HTTP handler thread and the main flow."""

    code: str | None = None
    state: str | None = None
    error: str | None = None
    received: threading.Event = field(default_factory=threading.Event)


def _make_handler(capture: _Capture, expected_path: str):
    class Handler(http.server.BaseHTTPRequestHandler):
        def do_GET(self) -> None:  # noqa: N802 — stdlib API
            parsed = urlparse(self.path)
            if parsed.path != expected_path:
                self.send_response(404)
                self.end_headers()
                return

            qs = {k: v[0] for k, v in parse_qs(parsed.query).items() if v}

            if "error" in qs:
                capture.error = qs.get("error_description") or qs["error"]
                page, status = _ERROR_PAGE, 400
            else:
                capture.code = qs.get("code")
                capture.state = qs.get("state")
                page, status = _SUCCESS_PAGE, 200

            self.send_response(status)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(page)))
            self.end_headers()
            self.wfile.write(page)
            capture.received.set()

        def log_message(self, *_args: Any, **_kwargs: Any) -> None:
            # Suppress the default access log — keep the terminal clean for the
            # one line we actually want the user to see.
            return

    return Handler


def build_authorize_url(
    *,
    client_id: str,
    redirect_uri: str,
    scopes: tuple[str, ...] | list[str],
    state: str,
    actor_app: bool = True,
) -> str:
    """Compose the authorize URL. Pure function — easy to unit-test."""
    params = {
        "client_id": client_id,
        "redirect_uri": redirect_uri,
        "response_type": "code",
        "scope": ",".join(scopes),
        "state": state,
        "prompt": "consent",
    }
    if actor_app:
        params["actor"] = "app"
    return f"{AUTHORIZE_URL}?{urlencode(params)}"


def exchange_code_for_token(
    *,
    client_id: str,
    client_secret: str,
    redirect_uri: str,
    code: str,
    timeout: float = 30.0,
) -> dict[str, Any]:
    """POST to Linear's token endpoint. Returns the parsed JSON body.

    Raises httpx.HTTPStatusError on a non-2xx so the caller can decide how to
    surface it.
    """
    response = httpx.post(
        TOKEN_URL,
        data={
            "client_id": client_id,
            "client_secret": client_secret,
            "redirect_uri": redirect_uri,
            "code": code,
            "grant_type": "authorization_code",
        },
        timeout=timeout,
    )
    response.raise_for_status()
    return response.json()


def run_dance(
    *,
    client_id: str,
    client_secret: str,
    redirect_uri: str,
    scopes: tuple[str, ...] | list[str],
    actor_app: bool,
    timeout: float,
) -> dict[str, Any]:
    """Execute the full OAuth dance and return the token-endpoint response."""
    parsed = urlparse(redirect_uri)
    if parsed.hostname not in ("localhost", "127.0.0.1"):
        raise ValueError(
            f"redirect_uri must be on localhost / 127.0.0.1 for this script "
            f"(got host={parsed.hostname!r}). For non-local flows, run the "
            f"dance on the host that Linear can reach."
        )
    port = parsed.port or 80
    callback_path = parsed.path or "/callback"

    capture = _Capture()
    server = http.server.HTTPServer(
        ("127.0.0.1", port),
        _make_handler(capture, callback_path),
    )
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()

    try:
        state = secrets.token_urlsafe(32)
        url = build_authorize_url(
            client_id=client_id,
            redirect_uri=redirect_uri,
            scopes=scopes,
            state=state,
            actor_app=actor_app,
        )
        print(f"\nOpening browser for Linear consent…\n  {url}\n", file=sys.stderr)
        webbrowser.open(url)

        if not capture.received.wait(timeout):
            raise TimeoutError(
                f"no callback received within {timeout:.0f}s — check that the "
                f"redirect URI registered in Linear matches {redirect_uri!r}"
            )

        if capture.error:
            raise RuntimeError(f"OAuth callback returned error: {capture.error}")
        if capture.state != state:
            raise RuntimeError(
                "state parameter mismatch — possible CSRF, aborting"
            )
        if not capture.code:
            raise RuntimeError("OAuth callback returned no code")

        return exchange_code_for_token(
            client_id=client_id,
            client_secret=client_secret,
            redirect_uri=redirect_uri,
            code=capture.code,
        )
    finally:
        server.shutdown()
        server.server_close()


def main(argv: list[str] | None = None) -> int:
    load_dotenv(override=True)
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--client-id",
        default=os.environ.get("LINEAR_OAUTH_CLIENT_ID"),
        help="OAuth client id (default: $LINEAR_OAUTH_CLIENT_ID)",
    )
    parser.add_argument(
        "--client-secret",
        default=os.environ.get("LINEAR_OAUTH_CLIENT_SECRET"),
        help="OAuth client secret (default: $LINEAR_OAUTH_CLIENT_SECRET)",
    )
    parser.add_argument(
        "--redirect-uri",
        default=os.environ.get("LINEAR_OAUTH_REDIRECT_URI", DEFAULT_REDIRECT_URI),
        help=f"Must match what's registered in Linear. Default: {DEFAULT_REDIRECT_URI}",
    )
    parser.add_argument(
        "--scopes",
        nargs="+",
        default=list(DEFAULT_SCOPES),
        help="OAuth scopes to request. Default: read write",
    )
    parser.add_argument(
        "--no-actor-app",
        action="store_true",
        help="Run the standard OAuth user flow instead of actor=app",
    )
    parser.add_argument(
        "--timeout",
        type=float,
        default=180.0,
        help="Seconds to wait for the user to complete consent (default: 180)",
    )
    parser.add_argument(
        "--write-env",
        metavar="PATH",
        nargs="?",
        const=".env",
        help="Persist LINEAR_API_KEY (access) + LINEAR_OAUTH_REFRESH_TOKEN to "
        "this file (default: .env). The file is updated in place; existing "
        "keys are overwritten.",
    )
    args = parser.parse_args(argv)

    if not args.client_id or not args.client_secret:
        print(
            "error: client id and secret required — set LINEAR_OAUTH_CLIENT_ID "
            "and LINEAR_OAUTH_CLIENT_SECRET in .env, or pass --client-id / "
            "--client-secret. See references/auth.md for setup steps.",
            file=sys.stderr,
        )
        return 2

    try:
        token = run_dance(
            client_id=args.client_id,
            client_secret=args.client_secret,
            redirect_uri=args.redirect_uri,
            scopes=args.scopes,
            actor_app=not args.no_actor_app,
            timeout=args.timeout,
        )
    except (RuntimeError, TimeoutError, ValueError, httpx.HTTPError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    access_token = token.get("access_token")
    refresh_token = token.get("refresh_token")
    if not access_token:
        print(f"error: token endpoint returned no access_token: {token}", file=sys.stderr)
        return 1

    expires_in = token.get("expires_in")
    scope = token.get("scope")
    keys = sorted(token.keys())

    if args.write_env:
        env_path = Path(args.write_env)
        env_path.touch(exist_ok=True)
        set_key(str(env_path), "LINEAR_API_KEY", access_token, quote_mode="never")
        if refresh_token:
            set_key(
                str(env_path),
                "LINEAR_OAUTH_REFRESH_TOKEN",
                refresh_token,
                quote_mode="never",
            )
        print(f"\nWrote token(s) to {env_path.resolve()}", file=sys.stderr)
    else:
        print(
            "\nAccess token received. Add this line to .env:\n",
            file=sys.stderr,
        )
        print(f"LINEAR_API_KEY={access_token}")  # stdout — easy to redirect
        if refresh_token:
            print(f"LINEAR_OAUTH_REFRESH_TOKEN={refresh_token}")
        print(file=sys.stderr)

    if scope:
        print(f"  scope:        {scope}", file=sys.stderr)
    if expires_in:
        print(f"  expires_in:   {expires_in}s ({_format_duration(expires_in)})", file=sys.stderr)
    print(f"  refresh_token returned: {'yes' if refresh_token else 'no'}", file=sys.stderr)
    print(f"  response keys: {', '.join(keys)}", file=sys.stderr)
    if refresh_token and not args.write_env:
        print(
            "\n  tip: rerun with --write-env to persist both tokens to .env "
            "automatically — required for `scripts/oauth_refresh.py` to work "
            "without re-prompting.",
            file=sys.stderr,
        )
    return 0


def _format_duration(seconds: float) -> str:
    """Render a token TTL in the most readable unit available."""
    if seconds < 3600:
        return f"~{seconds / 60:.0f} min"
    if seconds < 86400:
        return f"~{seconds / 3600:.1f} hours"
    if seconds < 86400 * 60:
        return f"~{seconds / 86400:.1f} days"
    return f"~{seconds / (365 * 86400):.1f} years"


if __name__ == "__main__":
    raise SystemExit(main())
