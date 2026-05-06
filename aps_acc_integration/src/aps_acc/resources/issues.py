"""ACC Issues API.

3-legged authentication ONLY. The user behind the 3LO token must be a member
of the project; if not, the API will return an empty list (not an error),
which is a common silent failure mode.

Reference:
  https://aps.autodesk.com/en/docs/acc/v1/reference/http/issues-GET/
  https://aps.autodesk.com/blog/acc-issues-api-available-preview
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Iterator

if TYPE_CHECKING:
    from aps_acc.client import APSClient

# `data:read` lets us GET; `data:write` is needed for create/update.
READ_SCOPES = ["data:read"]
WRITE_SCOPES = ["data:read", "data:write"]


class IssuesResource:
    def __init__(self, client: APSClient) -> None:
        self.client = client

    def list_issues(
        self,
        project_id: str,
        *,
        status: str | None = None,
        assigned_to: str | None = None,
        page_size: int = 100,
        extra_filters: dict[str, Any] | None = None,
    ) -> Iterator[dict[str, Any]]:
        """Yield every issue for a project."""
        path = f"/construction/issues/v1/projects/{project_id}/issues"
        params: dict[str, Any] = {}
        if status:
            params["filter[status]"] = status
        if assigned_to:
            params["filter[assignedTo]"] = assigned_to
        if extra_filters:
            params.update(extra_filters)
        yield from self.client.paginate(
            path, flow="3lo", scopes=READ_SCOPES, params=params, page_size=page_size
        )

    def get_issue(self, project_id: str, issue_id: str) -> dict[str, Any]:
        path = f"/construction/issues/v1/projects/{project_id}/issues/{issue_id}"
        return self.client.request("GET", path, flow="3lo", scopes=READ_SCOPES).json()

    def get_attribute_mappings(self, project_id: str) -> dict[str, Any]:
        """Lightweight call useful as a 3LO health probe."""
        path = f"/construction/issues/v1/projects/{project_id}/issue-attribute-mappings"
        return self.client.request("GET", path, flow="3lo", scopes=READ_SCOPES).json()
