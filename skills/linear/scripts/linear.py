#!/usr/bin/env python3
"""Thin GraphQL CLI for the Linear API.

Subcommands:
    query <document> [--variables JSON|@file]
    mutation <document> [--variables JSON|@file]
    introspect <typeName>

`<document>` is either an inline GraphQL string or a path to a .graphql file.
Reads LINEAR_API_KEY from the environment (loaded from .env if present).
Prints rate-limit / complexity headers to stderr after every call.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any

import httpx
from dotenv import load_dotenv

DEFAULT_URL = "https://api.linear.app/graphql"
RATE_LIMIT_HEADERS = (
    "x-ratelimit-requests-limit",
    "x-ratelimit-requests-remaining",
    "x-ratelimit-requests-reset",
    "x-complexity",
)


class LinearError(RuntimeError):
    """Raised when Linear returns an error or an unexpected response."""


def load_document(arg: str) -> str:
    """Return GraphQL text. If `arg` is a path that exists, read it; else treat as literal.

    Inline GraphQL strings can exceed the OS path-component limit (255 bytes on macOS),
    which makes `Path.is_file()` raise OSError. Treat that as "not a file."
    """
    try:
        candidate = Path(arg)
        if candidate.is_file():
            return candidate.read_text(encoding="utf-8")
    except OSError:
        pass
    return arg


def load_variables(raw: str | None) -> dict[str, Any]:
    if raw is None:
        return {}
    if raw.startswith("@"):
        return json.loads(Path(raw[1:]).read_text(encoding="utf-8"))
    return json.loads(raw)


def auth_header(api_key: str) -> str:
    """Build the Authorization header value for Linear.

    Personal API keys (prefix `lin_api_`) are sent **raw** — Linear's docs
    explicitly say no `Bearer` prefix for them. Everything else (OAuth user
    tokens, OAuth `actor=app` tokens, JWT-shaped access tokens) goes through
    `Bearer`. A pre-formed `Bearer …` string is passed through untouched.
    """
    if api_key.startswith("Bearer "):
        return api_key
    if api_key.startswith("lin_api_"):
        return api_key
    return f"Bearer {api_key}"


def log_rate_limits(headers: httpx.Headers) -> None:
    parts = []
    for h in RATE_LIMIT_HEADERS:
        if h in headers:
            parts.append(f"{h}={headers[h]}")
    if parts:
        print("[linear] " + " ".join(parts), file=sys.stderr)


def post_graphql(
    document: str,
    variables: dict[str, Any],
    api_key: str,
    url: str = DEFAULT_URL,
    timeout: float = 30.0,
) -> dict[str, Any]:
    """POST a GraphQL operation. Returns the parsed JSON. Raises on transport / GraphQL errors."""
    payload = {"query": document, "variables": variables}
    headers = {
        "Content-Type": "application/json",
        "Authorization": auth_header(api_key),
    }
    try:
        response = httpx.post(url, json=payload, headers=headers, timeout=timeout)
    except httpx.HTTPError as exc:
        raise LinearError(f"transport error: {exc}") from exc

    log_rate_limits(response.headers)

    if response.status_code == 429:
        retry_after = response.headers.get("retry-after", "?")
        raise LinearError(f"rate limited (429); retry-after={retry_after}s")

    try:
        body = response.json()
    except json.JSONDecodeError as exc:
        raise LinearError(
            f"non-JSON response (HTTP {response.status_code}): {response.text[:200]}"
        ) from exc

    if response.status_code >= 400:
        raise LinearError(f"HTTP {response.status_code}: {json.dumps(body, indent=2)}")

    if "errors" in body and body["errors"]:
        raise LinearError(f"GraphQL errors: {json.dumps(body['errors'], indent=2)}")

    return body


INTROSPECT_TYPE_QUERY = """
query IntrospectType($name: String!) {
  __type(name: $name) {
    name
    kind
    description
    fields(includeDeprecated: false) {
      name
      description
      type { name kind ofType { name kind ofType { name kind ofType { name kind } } } }
      args { name description type { name kind ofType { name kind } } }
    }
    inputFields {
      name
      description
      type { name kind ofType { name kind ofType { name kind } } }
    }
    enumValues(includeDeprecated: false) { name description }
  }
}
"""


def cmd_query(args: argparse.Namespace, api_key: str, url: str) -> int:
    document = load_document(args.document)
    variables = load_variables(args.variables)
    body = post_graphql(document, variables, api_key, url)
    json.dump(body.get("data", body), sys.stdout, indent=2, sort_keys=False)
    sys.stdout.write("\n")
    return 0


def cmd_mutation(args: argparse.Namespace, api_key: str, url: str) -> int:
    return cmd_query(args, api_key, url)  # transport identical; method name is a label only


def cmd_introspect(args: argparse.Namespace, api_key: str, url: str) -> int:
    body = post_graphql(INTROSPECT_TYPE_QUERY, {"name": args.type_name}, api_key, url)
    type_info = body.get("data", {}).get("__type")
    if type_info is None:
        raise LinearError(f"type not found: {args.type_name}")
    json.dump(type_info, sys.stdout, indent=2, sort_keys=False)
    sys.stdout.write("\n")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="linear",
        description="Thin GraphQL CLI for the Linear API.",
    )
    parser.add_argument(
        "--url",
        default=os.environ.get("LINEAR_API_URL", DEFAULT_URL),
        help="GraphQL endpoint (default: %(default)s)",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    q = sub.add_parser("query", help="Run a GraphQL query")
    q.add_argument("document", help="GraphQL string or path to .graphql file")
    q.add_argument("--variables", help='JSON string of variables, or "@path/to/file.json"')
    q.set_defaults(func=cmd_query)

    m = sub.add_parser("mutation", help="Run a GraphQL mutation")
    m.add_argument("document", help="GraphQL string or path to .graphql file")
    m.add_argument("--variables", help='JSON string of variables, or "@path/to/file.json"')
    m.set_defaults(func=cmd_mutation)

    i = sub.add_parser("introspect", help="Fetch schema info for a single type")
    i.add_argument("type_name", help="GraphQL type name, e.g. Issue, IssueCreateInput")
    i.set_defaults(func=cmd_introspect)

    return parser


def main(argv: list[str] | None = None) -> int:
    # `override=True` so the project's .env wins over any shell-env LINEAR_API_KEY
    # that might be lingering from a previous setup. Without this, a personal key
    # exported in your shell will shadow a bot token in .env.
    load_dotenv(override=True)
    parser = build_parser()
    args = parser.parse_args(argv)

    api_key = os.environ.get("LINEAR_API_KEY")
    if not api_key:
        print(
            "error: LINEAR_API_KEY not set. Copy .env.example to .env and add your key.",
            file=sys.stderr,
        )
        return 2

    try:
        return args.func(args, api_key, args.url)
    except LinearError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
