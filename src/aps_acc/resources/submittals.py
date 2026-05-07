"""ACC Submittals API.

3-legged authentication only. Each item's `permittedActions` array reflects
what the authenticated user is allowed to do, derived from the 3LO token.

Reference:
  https://aps.autodesk.com/en/docs/acc/v1/reference/http/submittals/
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Iterator

if TYPE_CHECKING:
    from aps_acc.client import APSClient

READ_SCOPES = ["data:read"]


class SubmittalsResource:
    def __init__(self, client: APSClient) -> None:
        self.client = client

    def list_items(
        self,
        project_id: str,
        *,
        page_size: int = 100,
        extra_filters: dict[str, Any] | None = None,
    ) -> Iterator[dict[str, Any]]:
        path = f"/construction/submittals/v2/projects/{project_id}/items"
        params = dict(extra_filters or {})
        yield from self.client.paginate(
            path, flow="3lo", scopes=READ_SCOPES, params=params, page_size=page_size
        )

    def get_item(self, project_id: str, item_id: str) -> dict[str, Any]:
        path = f"/construction/submittals/v2/projects/{project_id}/items/{item_id}"
        return self.client.request("GET", path, flow="3lo", scopes=READ_SCOPES).json()
