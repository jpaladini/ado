# Databricks Setup — Step by Step

This is the complete runbook to stand up the ADO companion as a **Databricks App**.
There are two paths:

- **A. Automated** — run one script (`scripts/setup.sh`). Recommended.
- **B. Manual** — the same steps, by hand, if you want to see/own each one.

Both end with a running app and its URL. Everything is idempotent — safe to re-run.

---

## 0. Prerequisites (one time)

| Tool | Why | Install |
|---|---|---|
| **Databricks CLI** (v0.230+) | deploy the bundle + app | `curl -fsSL https://raw.githubusercontent.com/databricks/setup-cli/main/install.sh \| sh` |
| **Python 3.11+** | backend + setup script | system / pyenv |
| **Node 20+ & npm** | build the React frontend | nodejs.org / nvm |

You also need:
- A **Databricks workspace URL**, e.g. `https://dbc-xxxx.cloud.databricks.com` (your Free Edition workspace; later, your corporate one).
- An **Azure DevOps Personal Access Token (PAT)**. Create it at
  `https://dev.azure.com/<org>/_usersSettings/tokens` with scopes:
  **Work Items (R/W)**, **Code (R/W)**, **Build (R/Execute)**. Copy it now — it's shown once.

---

## A. Automated setup (recommended)

From the repo root:

```bash
DBX_HOST=https://<your-workspace>.cloud.databricks.com \
ADO_ORG_URL=https://dev.azure.com/<your-org> \
ADO_PAT=<your-pat> \
./scripts/setup.sh
```

Omit any of the three env vars and the script will prompt for them (the PAT prompt is hidden).
The script checks prerequisites, logs you in if needed, stores the PAT as a secret, writes the
org URL into `app.yaml`, builds the frontend, deploys, starts the app, and prints its URL.

To deploy to the **corporate** workspace later: `TARGET=prod DBX_HOST=https://<corp> ./scripts/setup.sh`.

That's it. The rest of this doc is the manual breakdown of what the script does.

---

## B. Manual setup (the same steps, by hand)

### 1. Authenticate the CLI to your workspace
```bash
databricks auth login --host https://<your-workspace>.cloud.databricks.com
databricks current-user me        # confirms who/where you are
```
The bundle reads the host from this profile — nothing is hardcoded in `databricks.yml`.

### 2. Store the ADO PAT as a secret
```bash
databricks secrets create-scope ado          # ignore "already exists" on re-run
databricks secrets put-secret ado ado_pat --string-value "<your-pat>"
```
`databricks.yml` already declares this secret as an app resource (`scope: ado`, `key: ado_pat`,
`permission: READ`), so the app's service principal is granted read access automatically on deploy.

### 3. Set your ADO org URL
Edit `src/app.yaml` and set the `ADO_ORG_URL` value:
```yaml
env:
  - name: ADO_ORG_URL
    value: "https://dev.azure.com/<your-org>"
```

### 4. Build the frontend
The React build output must exist before deploy (it's served by FastAPI):
```bash
cd frontend && npm ci && npm run build && cd ..   # writes to src/static/
```

### 5. Deploy and start the app
```bash
databricks bundle deploy -t dev
databricks bundle run ado_app -t dev
databricks apps get ado-companion       # prints the app URL + state
```

Open the URL — you should see your Azure DevOps projects.

---

## Troubleshooting

| Symptom | Cause / Fix |
|---|---|
| App shows **"not connected to Azure DevOps"** | `ADO_ORG_URL` still a placeholder, or PAT secret missing/expired. Re-run steps 2–3, redeploy. |
| `/api/projects` returns **401/403** | PAT lacks scopes or is expired. Regenerate with Work Items / Code / Build, update the secret. |
| App can't read the secret | The app's service principal needs READ on the scope. The bundle grants it; if you created the app outside the bundle, grant it in **App → Settings → Resources**. |
| App **won't start / 5xx** | Check logs: `databricks apps logs ado-companion`. Usually a missing dep — confirm `src/requirements.txt` and that `src/static/` was built. |
| Projects time out | **Network egress**: the app must reach `dev.azure.com`. Free Edition allows it; **corporate** workspaces often restrict outbound — confirm with your platform team. |
| App stopped after a day | **Free Edition caps apps at ~24h** per deploy. Re-run `databricks bundle run ado_app -t dev`. Paid/corporate has no cap. |

---

## Migrating to the corporate workspace

No code changes — just point at the other workspace:

```bash
databricks auth login --host https://<corporate-workspace>
databricks secrets create-scope ado
databricks secrets put-secret ado ado_pat --string-value "<corp-pat-or-oauth>"
# set ADO_ORG_URL in src/app.yaml to the corporate org
cd frontend && npm ci && npm run build && cd ..
databricks bundle deploy -t prod
databricks bundle run ado_app -t prod
```

> **Reminder:** Free Edition is **non-commercial use only**. Real/corporate use must run on the
> corporate (paid) workspace. See `PLAN.md` §7.
