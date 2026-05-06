"""Tests for the auth module."""

from __future__ import annotations

import json
import time

import pytest
import responses

from aps_acc.auth import AUTH_BASE, AuthManager, ThreeLeggedToken, TokenStore
from aps_acc.exceptions import APSAuthError, APSTokenStoreError


TOKEN_URL = f"{AUTH_BASE}/token"


@pytest.fixture
def auth_manager(settings):  # type: ignore[no-untyped-def]
    return AuthManager(
        client_id=settings.client_id,
        client_secret=settings.client_secret,
        redirect_uri=settings.redirect_uri,
        token_store=TokenStore(settings.token_store_path),
    )


# ---------------------------------------------------------------------------
# 2-legged
# ---------------------------------------------------------------------------


@responses.activate
def test_two_legged_caches_token(auth_manager):  # type: ignore[no-untyped-def]
    responses.add(
        responses.POST,
        TOKEN_URL,
        json={"access_token": "abc123", "expires_in": 3600, "token_type": "Bearer"},
        status=200,
    )
    t1 = auth_manager.get_two_legged(["data:read"])
    t2 = auth_manager.get_two_legged(["data:read"])
    assert t1 == t2 == "abc123"
    # Only one network call despite two calls to get_two_legged.
    assert len(responses.calls) == 1


@responses.activate
def test_two_legged_separate_cache_per_scope_set(auth_manager):  # type: ignore[no-untyped-def]
    responses.add(
        responses.POST,
        TOKEN_URL,
        json={"access_token": "scope-a", "expires_in": 3600},
        status=200,
    )
    responses.add(
        responses.POST,
        TOKEN_URL,
        json={"access_token": "scope-b", "expires_in": 3600},
        status=200,
    )
    t1 = auth_manager.get_two_legged(["data:read"])
    t2 = auth_manager.get_two_legged(["account:read"])
    assert t1 == "scope-a"
    assert t2 == "scope-b"
    assert len(responses.calls) == 2


@responses.activate
def test_two_legged_failure_raises(auth_manager):  # type: ignore[no-untyped-def]
    responses.add(
        responses.POST,
        TOKEN_URL,
        json={"developerMessage": "bad creds"},
        status=401,
    )
    with pytest.raises(APSAuthError, match="2-legged"):
        auth_manager.get_two_legged(["data:read"])


# ---------------------------------------------------------------------------
# 3-legged
# ---------------------------------------------------------------------------


def test_three_legged_without_login_raises(auth_manager):  # type: ignore[no-untyped-def]
    with pytest.raises(APSAuthError, match="login"):
        auth_manager.get_three_legged(["data:read"])


def test_three_legged_returns_fresh_token_from_store(auth_manager, fresh_3lo_token):  # type: ignore[no-untyped-def]
    token = auth_manager.get_three_legged(["data:read"])
    assert token == fresh_3lo_token.access_token


@responses.activate
def test_three_legged_refreshes_when_stale(auth_manager, settings):  # type: ignore[no-untyped-def]
    # Write a stale token.
    stale = ThreeLeggedToken(
        access_token="stale-access",
        refresh_token="old-refresh",
        expires_at=time.time() - 100,  # already expired
        scopes=frozenset({"data:read"}),
    )
    settings.token_store_path.parent.mkdir(parents=True, exist_ok=True)
    settings.token_store_path.write_text(json.dumps(stale.to_json()), encoding="utf-8")

    responses.add(
        responses.POST,
        TOKEN_URL,
        json={
            "access_token": "new-access",
            "refresh_token": "rotated-refresh",
            "expires_in": 3600,
            "scope": "data:read",
        },
        status=200,
    )

    token = auth_manager.get_three_legged(["data:read"])
    assert token == "new-access"

    # The rotated refresh token must be persisted.
    on_disk = json.loads(settings.token_store_path.read_text(encoding="utf-8"))
    assert on_disk["refresh_token"] == "rotated-refresh"
    assert on_disk["access_token"] == "new-access"


@responses.activate
def test_three_legged_refresh_failure_propagates(auth_manager, fresh_3lo_token, settings):  # type: ignore[no-untyped-def]
    # Make the saved token stale so refresh kicks in.
    stale = ThreeLeggedToken(
        access_token="stale",
        refresh_token="bad-refresh",
        expires_at=time.time() - 1,
        scopes=frozenset({"data:read"}),
    )
    settings.token_store_path.write_text(json.dumps(stale.to_json()), encoding="utf-8")

    responses.add(
        responses.POST,
        TOKEN_URL,
        json={"developerMessage": "refresh expired"},
        status=400,
    )
    with pytest.raises(APSAuthError, match="refresh"):
        auth_manager.get_three_legged(["data:read"])


# ---------------------------------------------------------------------------
# Token store
# ---------------------------------------------------------------------------


def test_token_store_inline_overrides_file(tmp_path):  # type: ignore[no-untyped-def]
    inline = json.dumps({
        "access_token": "inline-access",
        "refresh_token": "inline-refresh",
        "expires_at": time.time() + 3600,
        "scopes": ["data:read"],
    })
    store = TokenStore(tmp_path / "should-not-be-read.json", inline=inline)
    token = store.load()
    assert token is not None
    assert token.access_token == "inline-access"


def test_token_store_load_missing_returns_none(tmp_path):  # type: ignore[no-untyped-def]
    store = TokenStore(tmp_path / "nope.json")
    assert store.load() is None


def test_token_store_corrupt_raises(tmp_path):  # type: ignore[no-untyped-def]
    p = tmp_path / "corrupt.json"
    p.write_text("not json", encoding="utf-8")
    store = TokenStore(p)
    with pytest.raises(APSTokenStoreError):
        store.load()
