"""Mock-based unit tests for scripts/linear.py and scripts/oauth_dance.py.

These never hit Linear. They use respx to intercept httpx calls.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import httpx
import pytest
import respx

# Make `scripts/linear.py` importable as `linear`.
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import client_credentials_token  # noqa: E402
import linear  # noqa: E402
import oauth_dance  # noqa: E402
import oauth_refresh  # noqa: E402


@pytest.fixture
def api_key() -> str:
    return "lin_api_test_key"


@respx.mock
def test_post_graphql_happy_path(api_key: str, capsys: pytest.CaptureFixture[str]) -> None:
    route = respx.post(linear.DEFAULT_URL).mock(
        return_value=httpx.Response(
            200,
            json={"data": {"viewer": {"id": "u_1", "name": "Andy"}}},
            headers={
                "x-ratelimit-requests-remaining": "4998",
                "x-complexity": "3",
            },
        )
    )

    body = linear.post_graphql("query { viewer { id name } }", {}, api_key)

    assert route.called
    assert body == {"data": {"viewer": {"id": "u_1", "name": "Andy"}}}
    err = capsys.readouterr().err
    assert "x-ratelimit-requests-remaining=4998" in err
    assert "x-complexity=3" in err


@respx.mock
def test_post_graphql_raises_on_429(api_key: str) -> None:
    respx.post(linear.DEFAULT_URL).mock(
        return_value=httpx.Response(429, json={}, headers={"retry-after": "12"})
    )
    with pytest.raises(linear.LinearError, match="rate limited"):
        linear.post_graphql("query { __typename }", {}, api_key)


@respx.mock
def test_post_graphql_raises_on_graphql_errors(api_key: str) -> None:
    respx.post(linear.DEFAULT_URL).mock(
        return_value=httpx.Response(
            200,
            json={"errors": [{"message": "bad field"}], "data": None},
        )
    )
    with pytest.raises(linear.LinearError, match="GraphQL errors"):
        linear.post_graphql("query { nope }", {}, api_key)


@respx.mock
def test_post_graphql_sends_authorization_header(api_key: str) -> None:
    captured: dict[str, str] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["auth"] = request.headers.get("authorization", "")
        captured["body"] = request.content.decode()
        return httpx.Response(200, json={"data": {"ok": True}})

    respx.post(linear.DEFAULT_URL).mock(side_effect=handler)
    linear.post_graphql("query Q { ok }", {"x": 1}, api_key)

    assert captured["auth"] == api_key  # personal key sent raw, no "Bearer"
    sent = json.loads(captured["body"])
    assert sent["query"] == "query Q { ok }"
    assert sent["variables"] == {"x": 1}


def test_load_document_reads_file(tmp_path: Path) -> None:
    f = tmp_path / "q.graphql"
    f.write_text("query X { __typename }")
    assert linear.load_document(str(f)) == "query X { __typename }"


def test_load_document_passthrough_for_inline_string() -> None:
    assert linear.load_document("query { __typename }") == "query { __typename }"


def test_load_document_handles_oversized_inline_string() -> None:
    # macOS path components cap at 255 bytes; a long inline GraphQL string used to
    # crash Path.is_file() with OSError. Should now be treated as a literal.
    long_query = "query Q { " + "a" * 400 + " }"
    assert linear.load_document(long_query) == long_query


def test_load_variables_inline() -> None:
    assert linear.load_variables('{"a": 1}') == {"a": 1}


def test_load_variables_from_file(tmp_path: Path) -> None:
    f = tmp_path / "v.json"
    f.write_text('{"a": 2}')
    assert linear.load_variables(f"@{f}") == {"a": 2}


def test_load_variables_none() -> None:
    assert linear.load_variables(None) == {}


def test_auth_header_personal_key_is_raw() -> None:
    assert linear.auth_header("lin_api_abc") == "lin_api_abc"


def test_auth_header_oauth_uses_bearer() -> None:
    assert linear.auth_header("lin_oauth_xyz") == "Bearer lin_oauth_xyz"


def test_auth_header_already_bearer_passthrough() -> None:
    assert linear.auth_header("Bearer foo") == "Bearer foo"


def test_auth_header_jwt_shaped_token_uses_bearer() -> None:
    # actor=app tokens can come back as raw JWTs without a recognisable prefix.
    assert linear.auth_header("eyJhbGciOi.payload.sig") == "Bearer eyJhbGciOi.payload.sig"


def test_auth_header_unknown_prefix_defaults_to_bearer() -> None:
    # Safer default: anything that isn't a personal key gets Bearer.
    assert linear.auth_header("oauth2_abc123") == "Bearer oauth2_abc123"


# ----- oauth_dance ---------------------------------------------------------


def test_build_authorize_url_includes_actor_app_by_default() -> None:
    url = oauth_dance.build_authorize_url(
        client_id="cid_123",
        redirect_uri="http://localhost:8765/callback",
        scopes=("read", "write"),
        state="abcdef",
    )
    parsed = urlparse(url)
    qs = parse_qs(parsed.query)
    assert parsed.scheme == "https"
    assert parsed.netloc == "linear.app"
    assert parsed.path == "/oauth/authorize"
    assert qs["client_id"] == ["cid_123"]
    assert qs["redirect_uri"] == ["http://localhost:8765/callback"]
    assert qs["response_type"] == ["code"]
    assert qs["scope"] == ["read,write"]  # comma-separated, no URL re-encoding surprises
    assert qs["state"] == ["abcdef"]
    assert qs["actor"] == ["app"]
    assert qs["prompt"] == ["consent"]


def test_build_authorize_url_omits_actor_when_disabled() -> None:
    url = oauth_dance.build_authorize_url(
        client_id="cid_123",
        redirect_uri="http://localhost:8765/callback",
        scopes=("read",),
        state="x",
        actor_app=False,
    )
    qs = parse_qs(urlparse(url).query)
    assert "actor" not in qs


@respx.mock
def test_exchange_code_for_token_posts_correct_body() -> None:
    captured: dict[str, str] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["body"] = request.content.decode()
        captured["content_type"] = request.headers.get("content-type", "")
        return httpx.Response(
            200,
            json={
                "access_token": "lin_oauth_test",
                "token_type": "Bearer",
                "expires_in": 315705599,
                "scope": "read,write",
            },
        )

    respx.post(oauth_dance.TOKEN_URL).mock(side_effect=handler)

    body = oauth_dance.exchange_code_for_token(
        client_id="cid",
        client_secret="csec",
        redirect_uri="http://localhost:8765/callback",
        code="auth_code_xyz",
    )

    assert body["access_token"] == "lin_oauth_test"
    sent = parse_qs(captured["body"])
    assert sent["client_id"] == ["cid"]
    assert sent["client_secret"] == ["csec"]
    assert sent["redirect_uri"] == ["http://localhost:8765/callback"]
    assert sent["code"] == ["auth_code_xyz"]
    assert sent["grant_type"] == ["authorization_code"]
    assert "x-www-form-urlencoded" in captured["content_type"]


@respx.mock
def test_exchange_code_for_token_raises_on_4xx() -> None:
    respx.post(oauth_dance.TOKEN_URL).mock(
        return_value=httpx.Response(400, json={"error": "invalid_grant"}),
    )
    with pytest.raises(httpx.HTTPStatusError):
        oauth_dance.exchange_code_for_token(
            client_id="cid",
            client_secret="csec",
            redirect_uri="http://localhost:8765/callback",
            code="bad",
        )


def test_run_dance_rejects_non_localhost_redirect() -> None:
    with pytest.raises(ValueError, match="localhost / 127.0.0.1"):
        oauth_dance.run_dance(
            client_id="cid",
            client_secret="csec",
            redirect_uri="https://evil.example.com/callback",
            scopes=("read",),
            actor_app=True,
            timeout=1.0,
        )


# ----- oauth_refresh -------------------------------------------------------


@respx.mock
def test_refresh_access_token_posts_correct_body() -> None:
    captured: dict[str, str] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["body"] = request.content.decode()
        return httpx.Response(
            200,
            json={
                "access_token": "lin_oauth_new",
                "refresh_token": "rt_new",
                "token_type": "Bearer",
                "expires_in": 86399,
                "scope": "read,write",
            },
        )

    respx.post(oauth_refresh.TOKEN_URL).mock(side_effect=handler)

    body = oauth_refresh.refresh_access_token(
        client_id="cid",
        client_secret="csec",
        refresh_token="rt_old",
    )

    assert body["access_token"] == "lin_oauth_new"
    assert body["refresh_token"] == "rt_new"
    sent = parse_qs(captured["body"])
    assert sent["client_id"] == ["cid"]
    assert sent["client_secret"] == ["csec"]
    assert sent["refresh_token"] == ["rt_old"]
    assert sent["grant_type"] == ["refresh_token"]


@respx.mock
def test_refresh_access_token_raises_on_4xx() -> None:
    respx.post(oauth_refresh.TOKEN_URL).mock(
        return_value=httpx.Response(400, json={"error": "invalid_grant"}),
    )
    with pytest.raises(httpx.HTTPStatusError):
        oauth_refresh.refresh_access_token(
            client_id="cid",
            client_secret="csec",
            refresh_token="revoked",
        )


# ----- client_credentials_token -------------------------------------------


@respx.mock
def test_mint_app_token_posts_correct_body() -> None:
    captured: dict[str, str] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["body"] = request.content.decode()
        return httpx.Response(
            200,
            json={
                "access_token": "lin_oauth_app_xyz",
                "expires_in": 2591999,  # ~30 days
                "scope": "read,write",
                "token_type": "Bearer",
            },
        )

    respx.post(client_credentials_token.TOKEN_URL).mock(side_effect=handler)

    body = client_credentials_token.mint_app_token(
        client_id="cid",
        client_secret="csec",
        scopes=("read", "write"),
    )

    assert body["access_token"] == "lin_oauth_app_xyz"
    assert body["expires_in"] == 2591999
    sent = parse_qs(captured["body"])
    assert sent["client_id"] == ["cid"]
    assert sent["client_secret"] == ["csec"]
    assert sent["grant_type"] == ["client_credentials"]
    assert sent["scope"] == ["read,write"]
    # Importantly: no refresh_token field, no code field — distinct from auth-code grant.
    assert "code" not in sent
    assert "refresh_token" not in sent


@respx.mock
def test_mint_app_token_raises_on_unsupported_grant_type() -> None:
    # Surfaces the "you forgot to toggle Client credentials in Linear's UI" case.
    respx.post(client_credentials_token.TOKEN_URL).mock(
        return_value=httpx.Response(
            400,
            json={"error": "unsupported_grant_type"},
        ),
    )
    with pytest.raises(httpx.HTTPStatusError):
        client_credentials_token.mint_app_token(
            client_id="cid",
            client_secret="csec",
        )
