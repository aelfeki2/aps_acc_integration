# aps_acc_integration

A Python integration that pulls **Projects, Project Users, Issues, RFIs, and
Submittals** from Autodesk Construction Cloud (ACC) via the Autodesk Platform
Services (APS) REST APIs.

Built around a single `APSClient` that supports both **2-legged**
(`client_credentials`) and **3-legged** (`authorization_code`) OAuth flows,
because not all ACC endpoints accept the same auth method:

| Endpoint family            | Token flow         |
|----------------------------|--------------------|
| ACC Admin (projects/users) | 2-legged           |
| ACC Issues                 | **3-legged only**  |
| ACC RFIs                   | **3-legged only**  |
| ACC Submittals             | **3-legged only**  |
| Data Management (folders)  | 2-legged or 3-legged |

If you try to call Issues/RFIs/Submittals with a 2-legged token, you will
authenticate successfully and then get `401`/`403` on every data call. This
client picks the right token automatically.

---

## Project layout

```
aps_acc_integration/
├── README.md
├── pyproject.toml
├── .env.example                # copy to .env and fill in
├── .gitignore
├── config/
│   └── logging.yaml
├── docs/
│   ├── SETUP.md                # full APS + ACC provisioning walkthrough
│   ├── DIAGNOSTICS.md          # what each diagnose() probe tells you
│   └── DATABRICKS.md           # how to migrate this to Databricks
├── src/
│   └── aps_acc/
│       ├── __init__.py
│       ├── __main__.py         # `python -m aps_acc ...`
│       ├── auth.py             # 2LO + 3LO token management
│       ├── client.py           # APSClient (HTTP plumbing, retries, paging)
│       ├── config.py           # settings loaded from env / .env
│       ├── diagnostics.py      # diagnose() probes
│       ├── exceptions.py
│       ├── exporters.py        # JSON + CSV writers
│       ├── logging_setup.py
│       ├── models.py           # light dataclasses for typed responses
│       └── resources/          # one module per API surface
│           ├── __init__.py
│           ├── admin.py        # projects, project users (2LO)
│           ├── issues.py       # issues (3LO)
│           ├── rfis.py         # RFIs (3LO)
│           └── submittals.py   # submittals (3LO)
├── tests/
│   ├── __init__.py
│   ├── conftest.py
│   ├── test_auth.py
│   ├── test_client.py
│   ├── test_diagnostics.py
│   ├── test_exporters.py
│   └── test_resources.py
└── output/                     # JSON/CSV output goes here (gitignored)
```

---

## Quick start

### 1. Install
```bash
git clone <this-repo>
cd aps_acc_integration
python -m venv .venv
.venv\Scripts\activate              # Windows
# source .venv/bin/activate         # macOS/Linux
pip install -e ".[dev]"
```

### 2. Configure
```bash
copy .env.example .env              # Windows
# cp .env.example .env              # macOS/Linux
```
Fill in `APS_CLIENT_ID`, `APS_CLIENT_SECRET`, `APS_ACCOUNT_ID`. See
`docs/SETUP.md` for where to find these and how to provision the
**Custom Integration** in ACC Account Admin (this is the step that's most
commonly missed and produces silent 403s).

### 3. Run diagnostics
```bash
python -m aps_acc diagnose
```
This runs six probes that tell you exactly what's wrong if anything is wrong.
See `docs/DIAGNOSTICS.md` for what each verdict means.

### 4. Log in (one-time, for Issues/RFIs/Submittals)
```bash
python -m aps_acc login
```
Opens your browser. After you authorize, the refresh token is saved to
`~/.aps_tokens.json` (mode `0600`). You won't need to log in again until the
refresh token expires.

### 5. Pull data
```bash
# All projects in the account (2-legged)
python -m aps_acc projects --output output/projects.json

# Issues for one project (3-legged)
python -m aps_acc issues --project-id <PROJECT_ID> --output output/issues.csv

# Same for RFIs and submittals
python -m aps_acc rfis --project-id <PROJECT_ID> --output output/rfis.csv
python -m aps_acc submittals --project-id <PROJECT_ID> --output output/submittals.csv

# Or pull everything for a project at once
python -m aps_acc pull-all --project-id <PROJECT_ID> --output-dir output/
```

CSV vs JSON is auto-detected from the filename extension.

---

## Architecture notes

- **Pure `requests`** — no APS SDK. Same pattern as my P6Client and DenodoClient.
- **`APSClient` is the only HTTP chokepoint.** All retries, 401-refresh,
  pagination, and logging happen there.
- **Resources are thin.** Each module under `src/aps_acc/resources/` just
  knows the URL pattern and which auth flow to request. The client does the work.
- **Tokens persist to a JSON file** (`~/.aps_tokens.json`, chmod `0600`).
  Refresh tokens rotate on every refresh in APS OAuth v2 — the store is
  always written back.
- **Write operations are gated** behind `write_enabled=True`. The CLI never
  enables this; callers must construct the client themselves to mutate.

See `docs/DATABRICKS.md` for migrating to Databricks (TL;DR: paste the
contents of `~/.aps_tokens.json` into a Databricks secret, set
`APS_TOKEN_STORE_INLINE` to read it from the env var instead of the file).

---

## Testing

```bash
pytest                              # run all tests
pytest --cov=aps_acc                # with coverage
pytest tests/test_client.py -v      # one file
```

Tests use the `responses` library to mock HTTP — no live API calls.

---

## License

Internal use. Not affiliated with Autodesk.
