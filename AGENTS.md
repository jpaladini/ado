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
- ❌ Do not deploy to `stg` or `prod` manually. Those flow through PR + Azure Pipelines
  (`docs/CICD.md`). Agents/bootstrap target **`dev` only**.

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
2. **Unity Catalog GRANTs and Genie Space sharing** (see Genie activation below) — RBAC
   changes are always the human's call.

---

## Genie activation (Phase 3 — NL analytics)

Do this **after** the app deploys. Each step is idempotent. Steps marked **HUMAN** must be
reported back, not attempted.

### G1. Run the ingest job
The bundle deploys a job `ado-analytics-ingest` (dev mode prefixes the name). Trigger it with
explicit params — `workspace` is the Free Edition catalog; corporate workspaces may use another:
```bash
databricks jobs list -p "$ENV" | grep ado-analytics-ingest   # note the job id
databricks jobs run-now <job-id> -p "$ENV" \
  --python-params '["--catalog","workspace","--schema","ado_analytics","--project","<ADO project name>"]'
```
Wait for `TERMINATED SUCCESS`. Creates `workspace.ado_analytics.work_items` and
`…work_item_daily`. Then **unpause** the job's daily schedule.

### G2. HUMAN — grants
The schema is owned by the deploy principal; both the asking users and the **app's service
principal** need read access (Genie executes SQL as the caller). The app SP's client id is in
`databricks apps get ado-companion` (`service_principal_client_id`). Human runs in the SQL editor:
```sql
GRANT USE SCHEMA ON SCHEMA workspace.ado_analytics TO `<user or app-SP-client-id>`;
GRANT SELECT     ON SCHEMA workspace.ado_analytics TO `<user or app-SP-client-id>`;
```

### G3. Create the Genie Space (API — works, with three quirks)
`POST /api/2.0/genie/spaces` with `title`, `description`, `warehouse_id`, and a
`serialized_space` JSON **string**:
```json
{"version": 2,
 "config": {"sample_questions": [{"id": "<32-hex uuid, no hyphens>", "question": ["..."]}]},
 "data_sources": {"tables": [{"identifier": "workspace.ado_analytics.work_item_daily"},
                              {"identifier": "workspace.ado_analytics.work_items"}]},
 "instructions": {"text_instructions": [{"id": "<32-hex uuid>", "content": ["line 1\n", "line 2\n"]}]}}
```
Quirks (each is a 400 otherwise): **tables must be sorted by identifier**; every
sample-question/instruction **id must be a lowercase 32-hex UUID without hyphens**
(`uuid4().hex`); `serialized_space` is a JSON-encoded *string*, not an object.
Include instructions defining "open" = `state_category NOT IN ('Completed','Removed')`.
The response's `space_id` is what the app needs.

### G4. Store the Space ID (secret; agent may be blocked — then HUMAN)
```bash
databricks secrets put-secret ado genie_space_id --string-value "<space_id>" -p "$ENV"
```
The app reads it at runtime — **no redeploy**.

### G5. HUMAN — share the Space with the app
Genie UI → the space → **Share** → add the app's service principal (`app-… ado-companion`) →
**Can Run** (it also needs access to the space's SQL warehouse).

### G6. Verify
- `GET <app-url>/api/health` → `"genie_configured": true`
- Analytics tab → ask "How many open work items are there by state?" → answer + table.
- Direct API check: `w.genie.start_conversation_and_wait(space_id, question)` should return
  `COMPLETED` with a text/query attachment.

Failure modes: `INSUFFICIENT_PERMISSIONS … USE SCHEMA` → G2 missing for whoever asked;
`genie_configured: false` → G4 missing; app's /api/genie/ask fails but direct API works → G5
missing.
