"""Shared pytest fixtures."""

from __future__ import annotations

import json
import time
from pathlib import Path

import pytest

from aps_acc.auth import AuthManager, ThreeLeggedToken, TokenStore
from aps_acc.client import APSClient
from aps_acc.config import Settings


@pytest.fixture
def settings(tmp_path: Path) -> Settings:
    return Settings(
        client_id="test-client-id",
        client_secret="test-client-secret",
        account_id="11111111-2222-3333-4444-555555555555",
        redirect_uri="http://localhost:8080/api/auth/callback",
        token_store_path=tmp_path / "tokens.json",
        token_store_inline=None,
        log_level="DEBUG",
        output_dir=tmp_path / "output",
    )


@pytest.fixture
def fresh_3lo_token(settings: Settings) -> ThreeLeggedToken:
    """A 3LO token already saved to disk with plenty of life left."""
    token = ThreeLeggedToken(
        access_token="3lo-access-token",
        refresh_token="3lo-refresh-token",
        expires_at=time.time() + 3600,
        scopes=frozenset({"data:read", "data:write"}),
    )
    settings.token_store_path.parent.mkdir(parents=True, exist_ok=True)
    settings.token_store_path.write_text(json.dumps(token.to_json()), encoding="utf-8")
    return token


@pytest.fixture
def client(settings: Settings) -> APSClient:
    return APSClient(settings, write_enabled=False)


@pytest.fixture
def write_client(settings: Settings) -> APSClient:
    return APSClient(settings, write_enabled=True)
