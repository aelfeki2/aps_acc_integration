# Diagnostics Guide

`python -m aps_acc diagnose [--project-id UUID]` runs six probes. Each
probe prints PASS/FAIL, the HTTP status if relevant, and a hint when it
fails. Here's what each one means.

---

## Probe 1 — 2-legged token mint

**What it does**: calls the APS token endpoint with `client_credentials`
and your client ID/secret.

**Pass means**: APS recognized your client ID and secret. Note this only
proves the credentials are valid — it doesn't mean the account has
authorized you yet.

**Fail means**: `APS_CLIENT_ID` or `APS_CLIENT_SECRET` is wrong, or your
APS app has been deleted.

---

## Probe 2 — 2LO token introspection

**What it does**: decodes the access token (it's a JWT) without verifying
the signature, prints client ID, scopes, and expiry from the payload.

**Pass means**: the server gave you what it thinks you asked for. Compare
the scopes to what you expected — if you asked for `account:read` and the
token only has `data:read`, something is wrong on the APS app definition.

**Fail means**: APS issued an opaque (non-JWT) token, which would be
unusual but not fatal.

---

## Probe 3 — Custom Integration provisioning

**What it does**: makes an unauthenticated-against-account read against the
ACC Admin API (`GET /accounts/{accountId}/projects?limit=1`).

**Pass means**: ACC accepts your client ID for this account.

**Fail means**: 403 with body containing "does not have access" — the
**Custom Integration step has not been done**. This is the #1 silent
failure for new APS apps. Fix: have your ACC Account Admin go to
Account Admin -> Custom Integrations -> Add custom integration and paste
your Client ID.

---

## Probe 4 — 3-legged token availability

**What it does**: looks for a refresh token in `~/.aps_tokens.json` (or
inline env var). If the access token is fresh, passes. If stale, tries to
refresh silently.

**Pass means**: 3-legged calls will work.

**Fail means**:
- "No 3-legged token in the store" -> run `python -m aps_acc login`.
- "refresh failed" -> refresh token expired (rare, but happens after long
  inactivity). Re-run login.

---

## Probe 5 — 3LO endpoint round-trip (requires `--project-id`)

**What it does**: calls a lightweight Issues endpoint
(`/issue-attribute-mappings`) to confirm the 3LO token actually works
against the ACC Issues API, not just the auth server.

**Pass means**: Issues, RFIs, Submittals will all respond.

**Fail means**:
- 401 -> token expired between probe 4 and probe 5; re-run login.
- 403 -> user behind the 3LO token isn't a member of this project, OR
  doesn't have access to the Build / Issues module on this project.
  This is the second-most-common silent failure. Add the user to the
  project, or log in as someone who's already on it.
- 404 -> project ID is wrong, or APS changed an endpoint version. Check
  the docs.

---

## Probe 6 — 3LO user project membership (requires `--project-id`)

**What it does**: calls the Admin API (2-legged) to list project users and
prints the count.

**Pass means**: the call worked. You should manually confirm your login
email appears in the list — if it doesn't, your 3LO calls will all return
empty data.

**Fail means**: same as probe 3 — provisioning issue.

---

## When every probe fails

99% of the time the cause is one of these three, in order of likelihood:

1. **Custom Integration not provisioned** (probe 3 fails). See SETUP.md
   step 3.
2. **Wrong account ID** (`APS_ACCOUNT_ID` has `b.` prefix, or is from a
   different account).
3. **Wrong client ID/secret** (probe 1 fails).
