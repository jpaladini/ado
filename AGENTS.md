# AGENTS.md — runbook for an AI coding agent (e.g. Genie Code)

This file is written for an **autonomous coding agent** to deploy this repo as a
Databricks App. It is deterministic and idempotent: run the steps in order; re-running
is safe. Human-readable context is in `README.md` / `PLAN.md`; the full manual runbook
is `SETUP_DATABRICKS.md`. **Prefer this file when acting as an agent.**

## What this repo is
A Databricks App: **React (Vite) SPA + FastAPI (Python) backend** that calls the Azure
DevOps REST API. The built frontend is committed under `src/static/`, so **no Node build
is required to deploy**. The app source is `src/` (deployed); `frontend/` is source only.

## Inputs you need (ask the human if not provided)
- `ADO_ORG_URL` — e.g. `https://dev.azure.com/<org>` (not secret).
- `ADO_PAT` — an Azure DevOps Personal Access Token with **Work Items (R/W)**,
  **Code (R/W)**, **Build (R/Execute)**. **Secret — never write it into any file or commit it.**
- A Databricks workspace the CLI is authenticated to.

## Do / Don't
- ✅ Set `ADO_ORG_URL` by editing `src/app.yaml` (plain value).
- ✅ Put the PAT only into a Databricks **secret** (`ado/ado_pat`).
- ❌ Do not put the PAT in `app.yaml`, code, or git.
- ❌ Do not change `databricks.yml` resource wiring (the `ado_pat` secret resource is required).
- ❌ Do not attempt to create the Genie Space — that is a human UI step (see end).

## Steps

### 0. Preflight — confirm CLI auth
```bash
databricks current-user me
```
If this fails, stop and tell the human to run `databricks auth login --host <workspace-url>`.

### 1. Set the ADO org URL in src/app.yaml
Replace the `ADO_ORG_URL` value (idempotent — works on any current value):
```bash
python3 - "<ADO_ORG_URL>" <<'PY'
import re, sys
p = "src/app.yaml"
s = open(p).read()
s = re.sub(r'(- name: ADO_ORG_URL\n\s*value: )"[^"]*"', r'\1"%s"' % sys.argv[1], s)
open(p, "w").write(s)
print("set ADO_ORG_URL ->", sys.argv[1])
PY
```

### 2. Store the PAT as a secret
```bash
databricks secrets create-scope ado 2>/dev/null || echo "scope exists, reusing"
databricks secrets put-secret ado ado_pat --string-value "<ADO_PAT>"
```

### 3. (Only if you changed anything under frontend/) rebuild the SPA
The committed build is current. Rebuild **only** if you edited `frontend/`:
```bash
cd frontend && npm ci && npm run build && cd ..   # requires Node; skip otherwise
```

### 4. Deploy and start the app
```bash
databricks bundle deploy -t dev
databricks bundle run ado_app -t dev
databricks apps get ado-companion        # note the printed URL
```

### 5. Verify
Fetch the app URL's health endpoint; expect `{"status":"ok","ado_configured":true}`:
```bash
curl -s "<app-url>/api/health"
```
- `ado_configured: false` → the secret or org URL is wrong; redo steps 1–2 and redeploy.
- `200` with projects visible at `<app-url>` → success.

## Done criteria
- `GET <app-url>/api/health` returns `ado_configured: true`.
- The app lists Azure DevOps projects and their work items / PRs / pipelines / code.

## Human-only steps (do NOT attempt; report these back)
1. **Provide the PAT value** for step 2.
2. **Phase 3 / Genie** (analytics): a human creates a **Genie Space** in the Databricks UI
   over the ingested ADO tables. The app's NL-Q&A panel (when built) will call that Space's
   ID via the Genie Conversation API. Until that exists, the analytics tab is inert — the
   operational app above works regardless.
