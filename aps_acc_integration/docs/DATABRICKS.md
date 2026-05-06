# Migrating to Databricks

This codebase is designed to work unchanged on Databricks. The key
adjustment is **how you provide the 3-legged refresh token**, since
Databricks notebooks don't run a browser.

---

## The general approach

1. Do the one-time `python -m aps_acc login` on your laptop.
2. Open `~/.aps_tokens.json` and copy its entire contents.
3. Paste those contents into a Databricks **secret**.
4. In your Databricks job/notebook, set `APS_TOKEN_STORE_INLINE` from that
   secret. The client reads from the env var instead of the file.

After that, the same APSClient code runs identically.

---

## Step-by-step

### 1. On your laptop

```bash
python -m aps_acc login
type %USERPROFILE%\.aps_tokens.json     # Windows
# cat ~/.aps_tokens.json                # macOS/Linux
```

The output looks like:
```json
{
  "access_token": "...",
  "refresh_token": "...",
  "expires_at": 1234567890.0,
  "scopes": ["data:read", "data:write"]
}
```

### 2. Store as a Databricks secret

```bash
databricks secrets create-scope aps-acc
databricks secrets put-secret aps-acc tokens
# (paste the JSON contents when prompted)

# Repeat for client credentials
databricks secrets put-secret aps-acc client-id
databricks secrets put-secret aps-acc client-secret
databricks secrets put-secret aps-acc account-id
```

### 3. In your notebook / job

```python
import os
os.environ["APS_CLIENT_ID"] = dbutils.secrets.get("aps-acc", "client-id")
os.environ["APS_CLIENT_SECRET"] = dbutils.secrets.get("aps-acc", "client-secret")
os.environ["APS_ACCOUNT_ID"] = dbutils.secrets.get("aps-acc", "account-id")
os.environ["APS_TOKEN_STORE_INLINE"] = dbutils.secrets.get("aps-acc", "tokens")

from aps_acc import APSClient

client = APSClient.from_env()
projects = list(client.admin.list_projects())
issues = list(client.issues.list_issues(projects[0]["id"]))
```

### 4. Write to a Delta table instead of CSV

```python
import pandas as pd
from aps_acc.exporters import _flatten

flat = [_flatten(r) for r in issues]
df = pd.DataFrame(flat)
spark_df = spark.createDataFrame(df)
spark_df.write.mode("overwrite").saveAsTable("acc.issues")
```

---

## Refresh-token rotation

APS rotates refresh tokens on every refresh. On your laptop the new token
is written back to `~/.aps_tokens.json` automatically. On Databricks with
`APS_TOKEN_STORE_INLINE`, **the rotated token is NOT written anywhere** —
it lives only in the in-memory client for that job.

Two options:

**Option A — let it ride (simpler).** Refresh tokens in APS are long-lived.
A daily job that refreshes every run keeps the token alive. The secret
itself slowly drifts out of date, but the in-memory token always works.
Re-run `aps_acc login` on your laptop and update the secret every few
months as a precaution.

**Option B — write rotated tokens back to a secret.** If you're paranoid,
use `databricks secrets put-secret` from inside the job whenever the token
is refreshed. Requires the job's principal to have `WRITE` on the scope.
Most people don't bother.

---

## Why not run the Flask server on Databricks?

You technically can, but:
- Databricks job clusters aren't long-lived and don't have public ports.
- Interactive notebooks aren't a good place for a long-running web server.
- Everything we need from 3LO can be handled with a pre-captured refresh
  token, which is what `APS_TOKEN_STORE_INLINE` is for.

If you want a long-running service, host it on a small VM (or App Service,
or whatever your cloud uses) and have Databricks call into that — but at
that point you've gone past what this CLI tool is designed for.
