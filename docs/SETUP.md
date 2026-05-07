# Setup Guide — APS app + ACC account provisioning

This is the part that bites everyone. The token endpoint will happily mint
you a valid access token even if your ACC account hasn't been told to trust
your app, and then every actual API call returns 403. Follow every step.

---

## 1. Create the APS application

1. Go to <https://aps.autodesk.com/myapps>.
2. Sign in with your Autodesk ID.
3. Click **Create App** -> **Traditional Web App**. (This type supports both
   2-legged and 3-legged flows; pure server-to-server can't do 3LO, which we
   need for Issues / RFIs / Submittals.)
4. **APIs**: enable at minimum:
   - Autodesk Construction Cloud API
   - Data Management API
5. **Callback URL**: set to `http://localhost:8080/api/auth/callback`.
   This MUST exactly match what we send during 3-legged login. You can add
   more callback URLs later (e.g. for Databricks behind a reverse proxy).
6. Save. Record the **Client ID** and **Client Secret**.

---

## 2. Find your ACC Account ID

You need the UUID of your ACC account (sometimes called Hub ID).

- **Easiest path**: open ACC in a browser, go to Account Admin. The URL
  contains the account UUID.
- Or run `python -m aps_acc projects --output projects.json` after step 4
  below — if provisioning is good, the response includes the account ID.

The same UUID is used two ways:
- `b.<UUID>` for Data Management API calls (Hub ID format)
- `<UUID>` (no prefix) for ACC Admin API calls

`APSClient` handles the prefixing — you store the bare UUID in `.env`.

---

## 3. Provision the Custom Integration in ACC (CRITICAL)

This is the step that's most often missed. Without it, 2-legged tokens
authenticate but every Admin call returns
`{"status": 403, "detail": "...does not have access"}`.

**You need an ACC Account Admin to do this** — if that's not you, send them
the steps below.

1. Log into ACC: <https://acc.autodesk.com>.
2. Top-left product switcher -> **Account Admin**.
3. If you have multiple accounts, pick the one that owns your projects.
4. Left sidebar -> **Custom Integrations**.
5. Click **+ Add custom integration**.
6. Paste the **Client ID** from step 1.
7. **App name**: anything memorable.
8. **Description**: paste the Client ID here too. The UI doesn't show the
   Client ID after creation, and if you have multiple integrations you'll
   need this to tell them apart.
9. Save.

The integration's status should show **Active**. The Client ID is now
trusted by this ACC account.

---

## 4. Configure the project locally

```bash
cp .env.example .env
```

Fill in `APS_CLIENT_ID`, `APS_CLIENT_SECRET`, `APS_ACCOUNT_ID`, and confirm
`APS_REDIRECT_URI` matches what you registered on the APS app.

Install:
```bash
python -m venv .venv
.venv\Scripts\activate
pip install -e ".[dev]"
```

---

## 5. Run diagnostics

```bash
python -m aps_acc diagnose
```

You want to see all 2-legged probes pass. The 3-legged probes will say
"skipped — pass --project-id". That's expected at this stage.

If the **Custom Integration provisioning** probe fails, go back to step 3.

---

## 6. Log in for 3-legged access

Required for Issues, RFIs, and Submittals. One-time per refresh-token
lifetime (which APS keeps long, on the order of weeks).

```bash
python -m aps_acc login
```

This:
1. Opens your default browser to the APS authorize URL.
2. You log in with your Autodesk account.
3. APS redirects to `localhost:8080/api/auth/callback?code=...`.
4. A one-shot HTTP server in the CLI captures the code, exchanges it for
   tokens, and saves them to `~/.aps_tokens.json` (mode `0600`).

**Important**: the user you log in as must be a **member of the projects**
you want to query. The 3-legged token impersonates them — if they're not on
the project, every Issues/RFI/Submittals call returns an empty list (not an
error). Diagnostics probe 6 catches this.

---

## 7. Re-run diagnostics with a project

```bash
python -m aps_acc diagnose --project-id <PROJECT_UUID>
```

All six probes should pass.

---

## 8. Pull data

```bash
python -m aps_acc projects --output output/projects.json
python -m aps_acc issues --project-id <PROJECT_UUID> --output output/issues.csv
python -m aps_acc pull-all --project-id <PROJECT_UUID> --output-dir output/
```

That's it.
