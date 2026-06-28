# AGENTS.md — runbook for an AI coding agent (e.g. Genie Code)

This file is written for an **autonomous coding agent** to deploy this repo as a
Databricks App. It is deterministic and idempotent: run the steps in order; re-running
is safe. Human-readable context is in `README.md` / `PLAN.md`; the full manual runbook
is `SETUP_DATABRICKS.md`. **Prefer this file when acting as an agent.**

## What this repo is
A Databricks App: **React (Vite) SPA + FastAPI (Python) backend** that calls the Azure
DevOps REST API. The built frontend is committed under `src/static/`, so **no Node build
is required to deploy**. The app source is `src/` (deployed); `frontend/` is source only.

## STEP 0 — Ask the human for inputs FIRST (do this before anything else)
Before running any command, **prompt the human for the values below and wait for their
reply.** Do not guess, infer from the environment, or proceed with placeholders. Ask with
exactly this checklist:

> I need three things before I can deploy:
> 1. **ADO_ORG_URL** — your Azure DevOps org URL, e.g. `https://dev.azure.com/<org>`
> 2. **ADO_PAT** — an Azure DevOps Personal Access Token with scopes **Work Items (R/W)**,
>    **Code (R/W)**, **Build (R/Execute)**. Create one at
>    `https://dev.azure.com/<org>/_usersSettings/tokens`. (I'll store it only as a
>    Databricks secret — never in a file or git.)
> 3. Which **environment** to deploy: `dev`, `stg`, or `prod` — and confirm the
>    **Databricks CLI is authenticated** to that workspace
>    (`databricks current-user me -p <env>` succeeds), or give me the workspace URL to log in.

Rules for handling these:
- **Both** `ADO_ORG_URL` and `ADO_PAT` are stored as **per-workspace secrets** (scope `ado`,
  keys `ado_org_url` / `ado_pat`). There are NO environment-specific values in any file.
- `ADO_PAT` is sensitive — never echo it back, write it to a file, or commit it.
- Config is **per workspace**: setting secrets in `dev` does not affect `stg`/`prod`.
- If any value is missing, **stop and re-ask.** Do not continue with the remaining steps.

## Do / Don't
- ✅ Put both `ADO_ORG_URL` and `ADO_PAT` only into the Databricks **secret scope** `ado`.
- ✅ Deploy with the target + profile for the chosen environment (`-t <env> -p <env>`).
- ❌ Do not put the PAT (or org URL) in `app.yaml`, code, or git — `app.yaml` reads them via `valueFrom`.
- ❌ Do not change `databricks.yml` resource wiring (the `ado_org_url` + `ado_pat` secret resources are required).
- ❌ Do not attempt to create the Genie Space — that is a human UI step (see end).

## Steps (only after Step 0 inputs are in hand)

Let `ENV` be the chosen environment (`dev` | `stg` | `prod`). Use `-t $ENV -p $ENV` on every
command below. (Run the whole sequence once per workspace you want to deploy to.)

### 1. Preflight — confirm CLI auth
```bash
databricks current-user me -p "$ENV"
```
If this fails, stop and tell the human to run `databricks auth login --host <workspace-url> --profile $ENV`.

### 2. Store config in the per-workspace secret scope
Both values are secrets; nothing is written to a file.
```bash
databricks secrets create-scope ado -p "$ENV" 2>/dev/null || echo "scope exists, reusing"
databricks secrets put-secret ado ado_org_url --string-value "<ADO_ORG_URL>" -p "$ENV"
databricks secrets put-secret ado ado_pat     --string-value "<ADO_PAT>"     -p "$ENV"
```

### 3. (Only if you changed anything under frontend/) rebuild the SPA
The committed build is current. Rebuild **only** if you edited `frontend/`:
```bash
cd frontend && npm ci && npm run build && cd ..   # requires Node; skip otherwise
```

### 4. Deploy and start the app
```bash
databricks bundle deploy -t "$ENV" -p "$ENV"
databricks bundle run ado_app -t "$ENV" -p "$ENV"
databricks apps get ado-companion -p "$ENV"        # note the printed URL
```

### 5. Verify
Fetch the app URL's health endpoint; expect `{"status":"ok","ado_configured":true}`:
```bash
curl -s "<app-url>/api/health"
```
- `ado_configured: false` → a secret is missing/wrong; redo step 2 and redeploy.
- `200` with projects visible at `<app-url>` → success.

## Done criteria
- `GET <app-url>/api/health` returns `ado_configured: true`.
- The app lists Azure DevOps projects and their work items / PRs / pipelines / code.

## Human-only steps (do NOT attempt; report these back)
1. **Provide the org URL + PAT** (asked in Step 0, stored as secrets in Step 2).
2. **Phase 3 / Genie** (analytics): a human creates a **Genie Space** in the Databricks UI
   over the ingested ADO tables. The app's NL-Q&A panel (when built) will call that Space's
   ID via the Genie Conversation API. Until that exists, the analytics tab is inert — the
   operational app above works regardless.
