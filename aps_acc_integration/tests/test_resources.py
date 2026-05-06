"""Smoke tests for resource modules — confirm they hit the right endpoints
with the right flow."""

from __future__ import annotations

import responses

from aps_acc.auth import AUTH_BASE
from aps_acc.client import API_BASE

TOKEN_URL = f"{AUTH_BASE}/token"


@responses.activate
def test_list_issues_uses_3lo(client, fresh_3lo_token):  # type: ignore[no-untyped-def]
    project_id = "abc-123"
    responses.add(
        responses.GET,
        f"{API_BASE}/construction/issues/v1/projects/{project_id}/issues",
        json={"results": [{"id": "i1"}], "pagination": {"totalResults": 1}},
        status=200,
    )
    issues = list(client.issues.list_issues(project_id))
    assert issues == [{"id": "i1"}]
    # Token endpoint should NOT have been called — we used the stored 3LO token.
    token_calls = [c for c in responses.calls if c.request.url.startswith(TOKEN_URL)]
    assert token_calls == []


@responses.activate
def test_list_rfis_endpoint_path(client, fresh_3lo_token):  # type: ignore[no-untyped-def]
    project_id = "abc-123"
    responses.add(
        responses.GET,
        f"{API_BASE}/construction/rfis/v2/projects/{project_id}/rfis",
        json={"results": [], "pagination": {"totalResults": 0}},
        status=200,
    )
    list(client.rfis.list_rfis(project_id))
    assert any(
        f"/construction/rfis/v2/projects/{project_id}/rfis" in c.request.url
        for c in responses.calls
    )


@responses.activate
def test_list_submittals_endpoint_path(client, fresh_3lo_token):  # type: ignore[no-untyped-def]
    project_id = "abc-123"
    responses.add(
        responses.GET,
        f"{API_BASE}/construction/submittals/v2/projects/{project_id}/items",
        json={"results": [], "pagination": {"totalResults": 0}},
        status=200,
    )
    list(client.submittals.list_items(project_id))
    assert any(
        f"/construction/submittals/v2/projects/{project_id}/items" in c.request.url
        for c in responses.calls
    )
