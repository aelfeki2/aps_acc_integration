"""ACC Admin API — projects and project users.

These endpoints accept 2-legged tokens, which means the integration runs
unattended (no user interaction). The Custom Integration must be provisioned
in ACC Account Admin or every call returns 403.

Reference:
  https://aps.autodesk.com/en/docs/acc/v1/reference/http/admin-accounts-accountidprojects-GET/
  https://aps.autodesk.com/en/docs/acc/v1/reference/http/admin-projectsprojectId-GET/
  https://aps.autodesk.com/en/docs/acc/v1/reference/http/admin-projectsprojectId-users-GET/
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Iterator

if TYPE_CHECKING:
    from aps_acc.client import APSClient

SCOPES = ["account:read", "data:read"]


class AdminResource:
    def __init__(self, client: APSClient) -> None:
        self.client = client

    def list_projects(
        self,
        *,
        status: str | None = "active",
        platform: str | None = "acc",
        page_size: int = 200,
    ) -> Iterator[dict[str, Any]]:
        """Yield every project in the configured account.

        Args:
            status: Filter by status (`active`, `archived`, `pending`, `suspended`).
            platform: `acc` to exclude legacy BIM 360 projects.
            page_size: Page size up to 200.
        """
        path = f"/construction/admin/v1/accounts/{self.client.settings.account_id}/projects"
        params: dict[str, Any] = {}
        if status:
            params["filter[status]"] = status
        if platform:
            params["filter[platform]"] = platform
        yield from self.client.paginate(
            path, flow="2lo", scopes=SCOPES, params=params, page_size=page_size
        )

    def get_project(self, project_id: str) -> dict[str, Any]:
        path = f"/construction/admin/v1/projects/{project_id}"
        return self.client.request("GET", path, flow="2lo", scopes=SCOPES).json()

    def list_project_users(
        self, project_id: str, *, page_size: int = 200
    ) -> Iterator[dict[str, Any]]:
        path = f"/construction/admin/v1/projects/{project_id}/users"
        yield from self.client.paginate(
            path, flow="2lo", scopes=SCOPES, page_size=page_size
        )
