"""HTTP client for APS REST APIs.

Single chokepoint for every request:
- picks the right token (2LO vs 3LO) per the `flow` argument.
- retries once on 401 by clearing the cached token and re-fetching.
- detects "Custom Integration not provisioned" 403s and raises a typed error
  so the caller can prompt the right fix.
- paginates uniformly (limit/offset and `pagination.nextUrl` both supported).
- logs every 4xx with the diagnostic header, masked tokens, and response body.

Resources (issues, RFIs, etc.) live in `aps_acc.resources` and call into this
client. They never construct HTTP requests directly.
"""

from __future__ import annotations

import logging
from typing import Any, Iterator, Literal

import requests

from aps_acc.auth import AuthManager, TokenStore
from aps_acc.config import Settings
from aps_acc.exceptions import APSHTTPError, APSProvisioningError
from aps_acc.logging_setup import mask_token

log = logging.getLogger(__name__)

API_BASE = "https://developer.api.autodesk.com"

Flow = Literal["2lo", "3lo"]


class APSClient:
    """Thin authenticated HTTP wrapper around APS REST endpoints."""

    def __init__(
        self,
        settings: Settings,
        *,
        write_enabled: bool = False,
        session: requests.Session | None = None,
    ) -> None:
        self.settings = settings
        self.write_enabled = write_enabled
        self.session = session or requests.Session()
        self.auth = AuthManager(
            client_id=settings.client_id,
            client_secret=settings.client_secret,
            redirect_uri=settings.redirect_uri,
            token_store=TokenStore(
                path=settings.token_store_path,
                inline=settings.token_store_inline,
            ),
            session=self.session,
        )

    # ------------------------------------------------------------------
    # Convenience constructors
    # ------------------------------------------------------------------

    @classmethod
    def from_env(cls, *, write_enabled: bool = False) -> APSClient:
        return cls(Settings.from_env(), write_enabled=write_enabled)

    # ------------------------------------------------------------------
    # Resource accessors (lazy imports to avoid circulars)
    # ------------------------------------------------------------------

    @property
    def admin(self):  # type: ignore[no-untyped-def]
        from aps_acc.resources.admin import AdminResource

        return AdminResource(self)

    @property
    def issues(self):  # type: ignore[no-untyped-def]
        from aps_acc.resources.issues import IssuesResource

        return IssuesResource(self)

    @property
    def rfis(self):  # type: ignore[no-untyped-def]
        from aps_acc.resources.rfis import RFIsResource

        return RFIsResource(self)

    @property
    def submittals(self):  # type: ignore[no-untyped-def]
        from aps_acc.resources.submittals import SubmittalsResource

        return SubmittalsResource(self)

    # ------------------------------------------------------------------
    # Core request method
    # ------------------------------------------------------------------

    def request(
        self,
        method: str,
        path: str,
        *,
        flow: Flow,
        scopes: list[str],
        params: dict[str, Any] | None = None,
        json: Any = None,
        headers: dict[str, str] | None = None,
        _retried: bool = False,
    ) -> requests.Response:
        """Issue a single authenticated request.

        Args:
            method: HTTP verb.
            path: API path starting with "/" (e.g. "/construction/admin/v1/...").
            flow: Which OAuth flow's token to use.
            scopes: Scopes to request when minting/refreshing.
            params: Query string.
            json: JSON body.
            headers: Extra headers.
            _retried: Internal — set when this is the retry attempt.
        """
        if method.upper() in {"POST", "PATCH", "PUT", "DELETE"} and not self.write_enabled:
            raise RuntimeError(
                f"Refusing {method} {path}: APSClient was constructed with "
                "write_enabled=False. Pass write_enabled=True to mutate."
            )

        token = self._token_for(flow, scopes)
        url = f"{API_BASE}{path}"
        full_headers = {
            "Authorization": f"Bearer {token}",
            "Accept": "application/json",
        }
        if headers:
            full_headers.update(headers)

        log.debug(
            "%s %s flow=%s token=%s scopes=%s",
            method,
            path,
            flow,
            mask_token(token),
            " ".join(scopes),
        )

        resp = self.session.request(
            method,
            url,
            params=params,
            json=json,
            headers=full_headers,
            timeout=60,
        )

        # 401 — token may have expired mid-flight. Clear and retry once.
        if resp.status_code == 401 and not _retried:
            log.info("Got 401 on %s %s; clearing token cache and retrying once.", method, path)
            self._invalidate(flow, scopes)
            return self.request(
                method,
                path,
                flow=flow,
                scopes=scopes,
                params=params,
                json=json,
                headers=headers,
                _retried=True,
            )

        if 400 <= resp.status_code < 600:
            self._raise_for_status(resp, method, url, flow)

        return resp

    # ------------------------------------------------------------------
    # Pagination helpers
    # ------------------------------------------------------------------

    def paginate(
        self,
        path: str,
        *,
        flow: Flow,
        scopes: list[str],
        params: dict[str, Any] | None = None,
        page_size: int = 200,
        results_key: str = "results",
    ) -> Iterator[dict[str, Any]]:
        """Iterate over all results of a paginated GET.

        Handles two pagination shapes used across APS:
        - `pagination.nextUrl` (vertical APIs return absolute URLs).
        - `limit` / `offset` with `pagination.totalResults` (Admin API).
        """
        params = dict(params or {})
        params.setdefault("limit", page_size)
        offset = int(params.get("offset", 0))

        while True:
            params["offset"] = offset
            resp = self.request("GET", path, flow=flow, scopes=scopes, params=params)
            payload = resp.json()
            batch = payload.get(results_key, [])
            for item in batch:
                yield item

            pagination = payload.get("pagination", {}) or {}
            next_url = pagination.get("nextUrl")
            total = pagination.get("totalResults")

            if next_url:
                # Switch to following nextUrl absolutely.
                yield from self._follow_next_url(next_url, flow=flow, scopes=scopes, results_key=results_key)
                return

            offset += len(batch)
            # Stop when we ran short or hit the known total.
            if not batch or len(batch) < params["limit"]:
                return
            if total is not None and offset >= int(total):
                return

    def _follow_next_url(
        self,
        url: str,
        *,
        flow: Flow,
        scopes: list[str],
        results_key: str,
    ) -> Iterator[dict[str, Any]]:
        while url:
            # nextUrl is absolute; strip the API_BASE prefix to reuse `request`.
            if url.startswith(API_BASE):
                path_with_query = url[len(API_BASE):]
            else:
                path_with_query = url
            # Split path and query for the standard request method.
            if "?" in path_with_query:
                path, query = path_with_query.split("?", 1)
                params = dict(p.split("=", 1) for p in query.split("&") if "=" in p)
            else:
                path, params = path_with_query, {}
            resp = self.request("GET", path, flow=flow, scopes=scopes, params=params)
            payload = resp.json()
            for item in payload.get(results_key, []):
                yield item
            url = (payload.get("pagination") or {}).get("nextUrl") or ""

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    def _token_for(self, flow: Flow, scopes: list[str]) -> str:
        if flow == "2lo":
            return self.auth.get_two_legged(scopes)
        if flow == "3lo":
            return self.auth.get_three_legged(scopes)
        raise ValueError(f"Unknown flow: {flow}")

    def _invalidate(self, flow: Flow, scopes: list[str]) -> None:
        if flow == "2lo":
            self.auth._two_legged_cache.pop(frozenset(scopes), None)
        # 3LO will refresh on next call automatically.

    def _raise_for_status(
        self, resp: requests.Response, method: str, url: str, flow: Flow
    ) -> None:
        body = resp.text
        diagnostic = resp.headers.get("x-ads-diagnostic")
        # Try to surface the structured error the API gave us.
        try:
            doc = resp.json()
            detail = doc.get("detail") or doc.get("title") or doc.get("errorMessage") or ""
        except ValueError:
            detail = body[:200]

        log.error(
            "HTTP %s on %s %s (flow=%s) detail=%r diagnostic=%s",
            resp.status_code,
            method,
            url,
            flow,
            detail,
            diagnostic,
        )

        # Detect the classic "Custom Integration not provisioned" 403.
        if (
            resp.status_code == 403
            and flow == "2lo"
            and ("does not have access" in body.lower() or "not provisioned" in body.lower())
        ):
            raise APSProvisioningError(
                "ACC Custom Integration is not provisioned for this Client ID. "
                "Have your ACC Account Admin go to Account Admin -> Custom "
                "Integrations -> Add custom integration and paste your Client ID."
            )

        raise APSHTTPError(
            detail or f"HTTP {resp.status_code}",
            status=resp.status_code,
            method=method,
            url=url,
            body=body,
            diagnostic=diagnostic,
        )
