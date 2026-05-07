"""Tests for APSClient — retry-on-401, pagination, write gating."""

from __future__ import annotations

import pytest
import responses

from aps_acc.auth import AUTH_BASE
from aps_acc.client import API_BASE
from aps_acc.exceptions import APSHTTPError, APSProvisioningError

TOKEN_URL = f"{AUTH_BASE}/token"


@responses.activate
def test_request_retries_once_on_401(client):  # type: ignore[no-untyped-def]
    responses.add(
        responses.POST,
        TOKEN_URL,
        json={"access_token": "first", "expires_in": 3600},
        status=200,
    )
    responses.add(
        responses.POST,
        TOKEN_URL,
        json={"access_token": "second", "expires_in": 3600},
        status=200,
    )
    # First call: 401. Second call: 200.
    responses.add(
        responses.GET,
        f"{API_BASE}/construction/admin/v1/accounts/{client.settings.account_id}/projects",
        json={"results": []},
        status=401,
    )
    responses.add(
        responses.GET,
        f"{API_BASE}/construction/admin/v1/accounts/{client.settings.account_id}/projects",
        json={"results": [], "pagination": {"totalResults": 0}},
        status=200,
    )

    items = list(client.admin.list_projects())
    assert items == []
    # 2 token mints + 2 GETs = 4 calls.
    assert len(responses.calls) == 4


@responses.activate
def test_provisioning_403_raises_typed_error(client):  # type: ignore[no-untyped-def]
    responses.add(
        responses.POST,
        TOKEN_URL,
        json={"access_token": "tok", "expires_in": 3600},
        status=200,
    )
    responses.add(
        responses.GET,
        f"{API_BASE}/construction/admin/v1/accounts/{client.settings.account_id}/projects",
        json={"detail": "The 2-legged access token does not have access"},
        status=403,
    )
    with pytest.raises(APSProvisioningError, match="Custom Integration"):
        list(client.admin.list_projects())


@responses.activate
def test_pagination_terminates_on_short_page(client):  # type: ignore[no-untyped-def]
    responses.add(
        responses.POST,
        TOKEN_URL,
        json={"access_token": "tok", "expires_in": 3600},
        status=200,
    )
    # Page 1: full page (200). Page 2: short (50). Should stop after page 2.
    responses.add(
        responses.GET,
        f"{API_BASE}/construction/admin/v1/accounts/{client.settings.account_id}/projects",
        json={
            "results": [{"id": f"p{i}"} for i in range(200)],
            "pagination": {"totalResults": 250, "limit": 200, "offset": 0},
        },
        status=200,
    )
    responses.add(
        responses.GET,
        f"{API_BASE}/construction/admin/v1/accounts/{client.settings.account_id}/projects",
        json={
            "results": [{"id": f"p{i}"} for i in range(200, 250)],
            "pagination": {"totalResults": 250, "limit": 200, "offset": 200},
        },
        status=200,
    )

    projects = list(client.admin.list_projects())
    assert len(projects) == 250


@responses.activate
def test_pagination_terminates_when_total_reached(client):  # type: ignore[no-untyped-def]
    responses.add(
        responses.POST, TOKEN_URL, json={"access_token": "tok", "expires_in": 3600}
    )
    responses.add(
        responses.GET,
        f"{API_BASE}/construction/admin/v1/accounts/{client.settings.account_id}/projects",
        json={
            "results": [{"id": "p1"}, {"id": "p2"}],
            "pagination": {"totalResults": 2, "limit": 200, "offset": 0},
        },
        status=200,
    )
    projects = list(client.admin.list_projects())
    assert len(projects) == 2


def test_write_gate_blocks_mutations(client):  # type: ignore[no-untyped-def]
    with pytest.raises(RuntimeError, match="write_enabled"):
        client.request(
            "POST",
            "/construction/issues/v1/projects/abc/issues",
            flow="3lo",
            scopes=["data:write"],
            json={"title": "test"},
        )


def test_other_4xx_raises_generic(client):  # type: ignore[no-untyped-def]
    """Confirm non-provisioning 4xx still raises APSHTTPError."""

    @responses.activate
    def run():  # type: ignore[no-untyped-def]
        responses.add(
            responses.POST, TOKEN_URL, json={"access_token": "tok", "expires_in": 3600}
        )
        responses.add(
            responses.GET,
            f"{API_BASE}/construction/admin/v1/projects/abc",
            json={"detail": "not found"},
            status=404,
        )
        with pytest.raises(APSHTTPError) as exc_info:
            client.admin.get_project("abc")
        assert exc_info.value.status == 404

    run()
