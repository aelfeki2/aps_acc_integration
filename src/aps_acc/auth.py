"""OAuth2 token management for APS.

Handles BOTH flows in one module:
- 2-legged (`client_credentials`) — for ACC Admin API calls (projects, users).
- 3-legged (`authorization_code` / `refresh_token`) — for Issues, RFIs,
  Submittals (these accept 3LO only).

Tokens are cached in memory by scope-set. The 3LO refresh token is persisted
to disk (default `~/.aps_tokens.json`, mode 0600) so users only have to log
in interactively once. APS rotates refresh tokens on every use, so the store
is always rewritten after a refresh.

Databricks note: set APS_TOKEN_STORE_INLINE to a JSON string to bypass the
file-based store entirely.
"""

from __future__ import annotations

import http.server
import json
import logging
import os
import secrets
import socketserver
import stat
import threading
import time
import urllib.parse
import webbrowser
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable

import requests
from requests.auth import HTTPBasicAuth

from aps_acc.exceptions import APSAuthError, APSTokenStoreError
from aps_acc.logging_setup import mask_token

log = logging.getLogger(__name__)

AUTH_BASE = "https://developer.api.autodesk.com/authentication/v2"
TOKEN_URL = f"{AUTH_BASE}/token"
AUTHORIZE_URL = f"{AUTH_BASE}/authorize"

# Refresh tokens slightly before they expire to avoid edge-case 401s.
EXPIRY_SAFETY_SECONDS = 60


# ---------------------------------------------------------------------------
# Token data classes
# ---------------------------------------------------------------------------


@dataclass
class TwoLeggedToken:
    access_token: str
    expires_at: float  # epoch seconds
    scopes: frozenset[str]

    def is_fresh(self) -> bool:
        return time.time() < (self.expires_at - EXPIRY_SAFETY_SECONDS)


@dataclass
class ThreeLeggedToken:
    access_token: str
    refresh_token: str
    expires_at: float
    scopes: frozenset[str]

    def is_fresh(self) -> bool:
        return time.time() < (self.expires_at - EXPIRY_SAFETY_SECONDS)

    def to_json(self) -> dict[str, object]:
        return {
            "access_token": self.access_token,
            "refresh_token": self.refresh_token,
            "expires_at": self.expires_at,
            "scopes": sorted(self.scopes),
        }

    @classmethod
    def from_json(cls, data: dict[str, object]) -> ThreeLeggedToken:
        try:
            return cls(
                access_token=str(data["access_token"]),
                refresh_token=str(data["refresh_token"]),
                expires_at=float(data["expires_at"]),  # type: ignore[arg-type]
                scopes=frozenset(data.get("scopes", [])),  # type: ignore[arg-type]
            )
        except (KeyError, TypeError, ValueError) as exc:
            raise APSTokenStoreError(f"Token store JSON is malformed: {exc}") from exc


# ---------------------------------------------------------------------------
# Token store (file-based, with inline-env-var override for Databricks)
# ---------------------------------------------------------------------------


class TokenStore:
    """Persists 3-legged tokens to a JSON file with restrictive permissions.

    If `inline` is provided (the contents of APS_TOKEN_STORE_INLINE), the
    store reads from there and writes are no-ops. This is what you want in
    Databricks: set the env var from a secret, run jobs, never touch a file.
    """

    def __init__(self, path: Path, *, inline: str | None = None) -> None:
        self._path = path
        self._inline = inline

    def load(self) -> ThreeLeggedToken | None:
        if self._inline:
            try:
                return ThreeLeggedToken.from_json(json.loads(self._inline))
            except json.JSONDecodeError as exc:
                raise APSTokenStoreError(
                    "APS_TOKEN_STORE_INLINE is not valid JSON"
                ) from exc

        if not self._path.is_file():
            return None
        try:
            with self._path.open("r", encoding="utf-8") as f:
                return ThreeLeggedToken.from_json(json.load(f))
        except (OSError, json.JSONDecodeError) as exc:
            raise APSTokenStoreError(
                f"Could not read token store at {self._path}: {exc}"
            ) from exc

    def save(self, token: ThreeLeggedToken) -> None:
        if self._inline:
            log.debug("Inline token store is read-only; skipping save.")
            return

        self._path.parent.mkdir(parents=True, exist_ok=True)
        # Write atomically: temp file + rename.
        tmp = self._path.with_suffix(self._path.suffix + ".tmp")
        with tmp.open("w", encoding="utf-8") as f:
            json.dump(token.to_json(), f, indent=2)
        # chmod 0600 BEFORE rename so the live path is never world-readable.
        try:
            os.chmod(tmp, stat.S_IRUSR | stat.S_IWUSR)
        except OSError:
            # Windows doesn't support full POSIX modes; best-effort.
            log.debug("Could not chmod 0600 on Windows; relying on user ACLs.")
        tmp.replace(self._path)
        log.info("Saved 3LO tokens to %s", self._path)

    def clear(self) -> None:
        if self._inline:
            return
        if self._path.is_file():
            self._path.unlink()


# ---------------------------------------------------------------------------
# Auth manager
# ---------------------------------------------------------------------------


@dataclass
class AuthManager:
    """Acquires and caches both 2LO and 3LO tokens."""

    client_id: str
    client_secret: str
    redirect_uri: str
    token_store: TokenStore
    session: requests.Session = field(default_factory=requests.Session)

    # Cache 2LO tokens keyed by scope frozenset.
    _two_legged_cache: dict[frozenset[str], TwoLeggedToken] = field(default_factory=dict)

    # ----- 2-legged ---------------------------------------------------------

    def get_two_legged(self, scopes: Iterable[str]) -> str:
        """Return a fresh 2-legged access token for the requested scopes."""
        scope_set = frozenset(scopes)
        cached = self._two_legged_cache.get(scope_set)
        if cached and cached.is_fresh():
            return cached.access_token

        log.info("Minting new 2LO token (scopes=%s)", " ".join(sorted(scope_set)))
        resp = self.session.post(
            TOKEN_URL,
            auth=HTTPBasicAuth(self.client_id, self.client_secret),
            data={
                "grant_type": "client_credentials",
                "scope": " ".join(sorted(scope_set)),
            },
            timeout=30,
        )
        if resp.status_code != 200:
            raise APSAuthError(
                f"2-legged token request failed: {resp.status_code} {resp.text}"
            )
        payload = resp.json()
        token = TwoLeggedToken(
            access_token=payload["access_token"],
            expires_at=time.time() + int(payload["expires_in"]),
            scopes=scope_set,
        )
        self._two_legged_cache[scope_set] = token
        log.debug("2LO token: %s (expires in %ds)", mask_token(token.access_token), payload["expires_in"])
        return token.access_token

    # ----- 3-legged ---------------------------------------------------------

    def get_three_legged(self, scopes: Iterable[str]) -> str:
        """Return a fresh 3-legged access token, refreshing if needed.

        Raises APSAuthError if no refresh token is available — the caller
        should run `interactive_login()` first (which the CLI does).
        """
        token = self.token_store.load()
        if token is None:
            raise APSAuthError(
                "No 3-legged token available. Run `python -m aps_acc login` first."
            )
        if token.is_fresh():
            return token.access_token

        log.info("Refreshing 3LO token")
        refreshed = self._refresh_three_legged(token.refresh_token, scopes)
        self.token_store.save(refreshed)
        return refreshed.access_token

    def _refresh_three_legged(
        self, refresh_token: str, scopes: Iterable[str]
    ) -> ThreeLeggedToken:
        resp = self.session.post(
            TOKEN_URL,
            auth=HTTPBasicAuth(self.client_id, self.client_secret),
            data={
                "grant_type": "refresh_token",
                "refresh_token": refresh_token,
                "scope": " ".join(sorted(set(scopes))),
            },
            timeout=30,
        )
        if resp.status_code != 200:
            raise APSAuthError(
                f"3-legged refresh failed: {resp.status_code} {resp.text}. "
                "Re-run `python -m aps_acc login` to re-authorize."
            )
        payload = resp.json()
        return ThreeLeggedToken(
            access_token=payload["access_token"],
            # APS rotates the refresh token; if it's not in the response, keep the old one.
            refresh_token=payload.get("refresh_token", refresh_token),
            expires_at=time.time() + int(payload["expires_in"]),
            scopes=frozenset(payload.get("scope", "").split()),
        )

    def interactive_login(self, scopes: Iterable[str]) -> ThreeLeggedToken:
        """Run the 3-legged authorization flow.

        Opens the user's browser to the APS authorize URL, spins up a one-shot
        local HTTP server on the redirect URI's port to capture the code, then
        exchanges the code for tokens and persists them.
        """
        scope_str = " ".join(sorted(set(scopes)))
        state = secrets.token_urlsafe(16)
        params = {
            "response_type": "code",
            "client_id": self.client_id,
            "redirect_uri": self.redirect_uri,
            "scope": scope_str,
            "state": state,
        }
        authorize_url = f"{AUTHORIZE_URL}?{urllib.parse.urlencode(params)}"

        parsed = urllib.parse.urlparse(self.redirect_uri)
        if parsed.hostname not in ("localhost", "127.0.0.1"):
            raise APSAuthError(
                f"Interactive login requires a localhost redirect URI; got {self.redirect_uri}"
            )
        port = parsed.port or 80
        path = parsed.path or "/"

        captured: dict[str, str] = {}

        class _Handler(http.server.BaseHTTPRequestHandler):
            def do_GET(self_inner) -> None:  # noqa: N802 (stdlib API)
                qs = urllib.parse.urlparse(self_inner.path)
                if qs.path != path:
                    self_inner.send_response(404)
                    self_inner.end_headers()
                    return
                params = urllib.parse.parse_qs(qs.query)
                if "code" in params:
                    captured["code"] = params["code"][0]
                    captured["state"] = params.get("state", [""])[0]
                    self_inner.send_response(200)
                    self_inner.send_header("Content-Type", "text/html")
                    self_inner.end_headers()
                    self_inner.wfile.write(
                        b"<html><body><h2>Login complete.</h2>"
                        b"<p>You can close this tab and return to the terminal.</p>"
                        b"</body></html>"
                    )
                else:
                    captured["error"] = params.get("error", ["unknown"])[0]
                    self_inner.send_response(400)
                    self_inner.end_headers()

            def log_message(self_inner, format: str, *args: object) -> None:  # noqa: A002
                # Silence stdlib's per-request stderr spam.
                return

        server = socketserver.TCPServer(("127.0.0.1", port), _Handler)
        server.timeout = 1
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()

        try:
            log.info("Opening browser for APS login...")
            print(f"\nIf the browser doesn't open, visit this URL manually:\n  {authorize_url}\n")
            webbrowser.open(authorize_url, new=2)

            # Wait up to 5 minutes for the user to complete login.
            deadline = time.time() + 300
            while time.time() < deadline and "code" not in captured and "error" not in captured:
                time.sleep(0.25)
        finally:
            server.shutdown()
            server.server_close()

        if "error" in captured:
            raise APSAuthError(f"Authorization denied: {captured['error']}")
        if "code" not in captured:
            raise APSAuthError("Timed out waiting for authorization callback (5 minutes).")
        if captured.get("state") != state:
            raise APSAuthError("OAuth state mismatch; possible CSRF. Aborting.")

        log.info("Authorization code received, exchanging for tokens.")
        token = self._exchange_code(captured["code"], scope_str)
        self.token_store.save(token)
        return token

    def _exchange_code(self, code: str, scope_str: str) -> ThreeLeggedToken:
        resp = self.session.post(
            TOKEN_URL,
            auth=HTTPBasicAuth(self.client_id, self.client_secret),
            data={
                "grant_type": "authorization_code",
                "code": code,
                "redirect_uri": self.redirect_uri,
            },
            timeout=30,
        )
        if resp.status_code != 200:
            raise APSAuthError(
                f"Authorization code exchange failed: {resp.status_code} {resp.text}"
            )
        payload = resp.json()
        return ThreeLeggedToken(
            access_token=payload["access_token"],
            refresh_token=payload["refresh_token"],
            expires_at=time.time() + int(payload["expires_in"]),
            scopes=frozenset(payload.get("scope", scope_str).split()),
        )
