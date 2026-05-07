"""Tests for the diagnostic probes."""

from __future__ import annotations

import responses

from aps_acc.auth import AUTH_BASE
from aps_acc.client import API_BASE
from aps_acc.diagnostics import diagnose

TOKEN_URL = f"{AUTH_BASE}/token"


@responses.activate
def test_diagnose_detects_provisioning_failure(client):  # type: ignore[no-untyped-def]
    responses.add(
        responses.POST, TOKEN_URL, json={"access_token": "tok", "expires_in": 3600}
    )
    # Provisioning probe gets 403.
    responses.add(
        responses.GET,
        f"{API_BASE}/construction/admin/v1/accounts/{client.settings.account_id}/projects",
        json={"detail": "The 2-legged access token does not have access"},
        status=403,
    )

    results = diagnose(client)
    by_name = {r.name: r for r in results}

    assert by_name["2-legged token mint"].passed is True
    assert by_name["Custom Integration provisioning"].passed is False
    assert "Custom Integration" in by_name["Custom Integration provisioning"].message


@responses.activate
def test_diagnose_passes_when_everything_ok(client, fresh_3lo_token):  # type: ignore[no-untyped-def]
    responses.add(
        responses.POST, TOKEN_URL, json={"access_token": "tok", "expires_in": 3600}
    )
    responses.add(
        responses.GET,
        f"{API_BASE}/construction/admin/v1/accounts/{client.settings.account_id}/projects",
        json={"results": [], "pagination": {"totalResults": 0}},
        status=200,
    )
    results = diagnose(client)  # no project_id -> 3LO probes skip
    by_name = {r.name: r for r in results}
    assert by_name["2-legged token mint"].passed
    assert by_name["Custom Integration provisioning"].passed
    assert by_name["3-legged token availability"].passed
