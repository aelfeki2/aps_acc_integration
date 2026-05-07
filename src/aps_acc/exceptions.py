"""Exception hierarchy for the APS client.

Using a typed hierarchy makes it easy for callers to handle specific failure
modes (e.g. "Custom Integration not provisioned" is very different from
"refresh token expired").
"""

from __future__ import annotations


class APSError(Exception):
    """Base class for all APS-related errors."""


class APSAuthError(APSError):
    """Authentication or token-acquisition failure."""


class APSTokenStoreError(APSError):
    """The 3-legged token store is missing, corrupt, or unreadable."""


class APSProvisioningError(APSError):
    """The APS app isn't provisioned for this ACC account.

    Raised when a 2-legged call returns 403 with a body indicating the client
    isn't authorized. The fix is for an ACC Account Admin to add the Client ID
    under Account Admin -> Custom Integrations.
    """


class APSHTTPError(APSError):
    """Non-2xx response from an APS endpoint."""

    def __init__(
        self,
        message: str,
        *,
        status: int,
        method: str,
        url: str,
        body: str | None = None,
        diagnostic: str | None = None,
    ) -> None:
        super().__init__(message)
        self.status = status
        self.method = method
        self.url = url
        self.body = body
        self.diagnostic = diagnostic

    def __str__(self) -> str:
        parts = [f"{self.method} {self.url} -> {self.status}: {self.args[0]}"]
        if self.diagnostic:
            parts.append(f"x-ads-diagnostic={self.diagnostic}")
        return " | ".join(parts)
