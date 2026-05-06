"""ACC RFIs API.

3-legged authentication only. Same membership rules as Issues.

Reference:
  https://aps.autodesk.com/en/docs/acc/v1/reference/http/rfis/
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Iterator

if TYPE_CHECKING:
    from aps_acc.client import APSClient

READ_SCOPES = ["data:read"]


class RFIsResource:
    def __init__(self, client: APSClient) -> None:
        self.client = client

    def list_rfis(
        self,
        project_id: str,
        *,
        page_size: int = 100,
        extra_filters: dict[str, Any] | None = None,
    ) -> Iterator[dict[str, Any]]:
        path = f"/construction/rfis/v2/projects/{project_id}/rfis"
        params = dict(extra_filters or {})
        yield from self.client.paginate(
            path, flow="3lo", scopes=READ_SCOPES, params=params, page_size=page_size
        )

    def get_rfi(self, project_id: str, rfi_id: str) -> dict[str, Any]:
        path = f"/construction/rfis/v2/projects/{project_id}/rfis/{rfi_id}"
        return self.client.request("GET", path, flow="3lo", scopes=READ_SCOPES).json()
