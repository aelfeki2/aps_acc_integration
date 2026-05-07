"""Diagnostic probes that explain failures in plain English.

Designed for the situation we hit on day one: 2-legged token authenticated
fine, but every Issues call returned 401/403. Without these probes, the
caller has to read the APS docs, decode JWTs by hand, and ask their account
admin three different questions.

Each probe returns a (passed, status, message, hint) tuple so it can drive
both CLI output and structured tests.
"""

from __future__ import annotations

import base64
import json
import logging
import time
from dataclasses import dataclass
from typing import Any

from aps_acc.client import APSClient
from aps_acc.exceptions import APSAuthError, APSError, APSHTTPError, APSProvisioningError

log = logging.getLogger(__name__)


@dataclass
class ProbeResult:
    name: str
    passed: bool
    status: int | None
    message: str
    hint: str = ""

    def render(self) -> str:
        icon = "PASS" if self.passed else "FAIL"
        line = f"[{icon}] {self.name}"
        if self.status is not None:
            line += f"  (HTTP {self.status})"
        line += f"\n       {self.message}"
        if self.hint and not self.passed:
            line += f"\n       -> {self.hint}"
        return line


def _jwt_payload(token: str) -> dict[str, Any]:
    """Decode the middle segment of a JWT without verifying signature."""
    try:
        parts = token.split(".")
        if len(parts) < 2:
            return {}
        payload = parts[1]
        padding = "=" * (-len(payload) % 4)
        decoded = base64.urlsafe_b64decode(payload + padding)
        return json.loads(decoded)
    except (ValueError, json.JSONDecodeError):
        return {}


def diagnose(
    client: APSClient,
    *,
    project_id: str | None = None,
) -> list[ProbeResult]:
    """Run all probes and return results.

    If `project_id` is None, probes that need a project are skipped with a
    clear "skipped — no project_id provided" message.
    """
    results: list[ProbeResult] = []

    # -------- Probe 1: 2-legged token mint -------------------------------
    try:
        token = client.auth.get_two_legged(["account:read", "data:read"])
        results.append(
            ProbeResult(
                name="2-legged token mint",
                passed=True,
                status=200,
                message="Successfully obtained 2-legged access token.",
            )
        )
    except APSAuthError as exc:
        results.append(
            ProbeResult(
                name="2-legged token mint",
                passed=False,
                status=None,
                message=str(exc),
                hint="Check APS_CLIENT_ID and APS_CLIENT_SECRET in your .env.",
            )
        )
        return results  # No point continuing.

    # -------- Probe 2: token decode --------------------------------------
    payload = _jwt_payload(token)
    scopes_in_token = payload.get("scope") or payload.get("scp") or "<none>"
    if isinstance(scopes_in_token, list):
        scopes_in_token = " ".join(scopes_in_token)
    exp = payload.get("exp")
    exp_msg = (
        f"expires in {int(exp - time.time())}s" if isinstance(exp, (int, float)) else "no exp claim"
    )
    results.append(
        ProbeResult(
            name="2LO token introspection",
            passed=bool(payload),
            status=None,
            message=(
                f"client_id={payload.get('client_id', '?')}, "
                f"scopes='{scopes_in_token}', {exp_msg}"
            ),
            hint="Token did not decode as a JWT." if not payload else "",
        )
    )

    # -------- Probe 3: Custom Integration provisioning -------------------
    try:
        path = f"/construction/admin/v1/accounts/{client.settings.account_id}/projects"
        resp = client.request(
            "GET", path, flow="2lo", scopes=["account:read", "data:read"], params={"limit": 1}
        )
        results.append(
            ProbeResult(
                name="Custom Integration provisioning",
                passed=True,
                status=resp.status_code,
                message=(
                    f"ACC accepts this Client ID for account {client.settings.account_id}."
                ),
            )
        )
    except APSProvisioningError as exc:
        results.append(
            ProbeResult(
                name="Custom Integration provisioning",
                passed=False,
                status=403,
                message=str(exc),
                hint=(
                    "Have your ACC Account Admin go to ACC Account Admin -> "
                    "Custom Integrations -> Add custom integration, paste this "
                    f"Client ID ({client.settings.client_id[:8]}...), and save."
                ),
            )
        )
    except APSHTTPError as exc:
        results.append(
            ProbeResult(
                name="Custom Integration provisioning",
                passed=False,
                status=exc.status,
                message=str(exc),
                hint="Check that APS_ACCOUNT_ID is correct (no `b.` prefix).",
            )
        )

    # -------- Probe 4: 3-legged token availability -----------------------
    stored = client.auth.token_store.load()
    if stored is None:
        results.append(
            ProbeResult(
                name="3-legged token availability",
                passed=False,
                status=None,
                message="No 3-legged token in the store.",
                hint="Run `python -m aps_acc login` to authorize.",
            )
        )
    elif stored.is_fresh():
        results.append(
            ProbeResult(
                name="3-legged token availability",
                passed=True,
                status=None,
                message=f"Stored access token is fresh "
                f"(expires in {int(stored.expires_at - time.time())}s).",
            )
        )
    else:
        # Try a silent refresh.
        try:
            client.auth.get_three_legged(["data:read"])
            results.append(
                ProbeResult(
                    name="3-legged token availability",
                    passed=True,
                    status=200,
                    message="Stored access token was stale; refresh succeeded.",
                )
            )
        except APSAuthError as exc:
            results.append(
                ProbeResult(
                    name="3-legged token availability",
                    passed=False,
                    status=None,
                    message=str(exc),
                    hint="Refresh token may be expired. Re-run `python -m aps_acc login`.",
                )
            )

    # -------- Probe 5: 3LO endpoint round-trip ---------------------------
    if project_id is None:
        results.append(
            ProbeResult(
                name="3LO endpoint round-trip",
                passed=False,
                status=None,
                message="Skipped — pass --project-id to test a real 3LO call.",
                hint="Re-run with --project-id <UUID>.",
            )
        )
    else:
        try:
            client.issues.get_attribute_mappings(project_id)
            results.append(
                ProbeResult(
                    name="3LO endpoint round-trip",
                    passed=True,
                    status=200,
                    message="Issues attribute mappings fetched successfully.",
                )
            )
        except APSHTTPError as exc:
            hint = ""
            if exc.status == 401:
                hint = "Token expired or wrong flow. Re-run `python -m aps_acc login`."
            elif exc.status == 403:
                hint = (
                    "User behind your 3LO token isn't a member of this project, "
                    "or doesn't have access to the Issues module."
                )
            elif exc.status == 404:
                hint = "Project ID not found, or wrong endpoint version."
            results.append(
                ProbeResult(
                    name="3LO endpoint round-trip",
                    passed=False,
                    status=exc.status,
                    message=str(exc),
                    hint=hint,
                )
            )
        except APSError as exc:
            results.append(
                ProbeResult(
                    name="3LO endpoint round-trip",
                    passed=False,
                    status=None,
                    message=str(exc),
                )
            )

    # -------- Probe 6: 3LO user is a member of the project ---------------
    if project_id is None:
        results.append(
            ProbeResult(
                name="3LO user project membership",
                passed=False,
                status=None,
                message="Skipped — pass --project-id to verify membership.",
            )
        )
    else:
        try:
            users = list(client.admin.list_project_users(project_id, page_size=200))
            results.append(
                ProbeResult(
                    name="3LO user project membership",
                    passed=True,
                    status=200,
                    message=(
                        f"Project has {len(users)} members. Confirm your login email "
                        "appears in the list to ensure 3LO calls return data."
                    ),
                )
            )
        except APSHTTPError as exc:
            results.append(
                ProbeResult(
                    name="3LO user project membership",
                    passed=False,
                    status=exc.status,
                    message=str(exc),
                )
            )

    return results
