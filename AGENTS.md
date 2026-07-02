# AGENTS.md — the complete agent runbook

Written for **any autonomous coding agent** — Databricks Genie Code, Claude Code, or a
human at a terminal. No specific AI vendor is required to build, deploy, or operate this
project; **all runtime AI is Databricks-native** (Genie + Foundation Model APIs). Steps
are deterministic and idempotent: run them in order; re-running is safe. Human context
lives in `README.md` / `PLAN.md`; manual setup in `SETUP_DATABRICKS.md`; CI/CD in
`docs/CICD.md`; Genie details in `docs/GENIE.md`. **Prefer this file when acting as an agent.**

## What this repo is
A Databricks App: **React (Vite) SPA + FastAPI (Python) backend** that calls the Azure
DevOps REST API (operational plane) and Databricks Genie over ingested Delta tables
(analytical plane). The built frontend is committed under `src/static/`, so **no Node
build is required to deploy**. The app source is `src/` (deployed); `frontend/` is source only.

## Secrets reference (scope `ado`, one per workspace)
All per-environment config is secrets — the code is identical across dev/stg/prod.

| Key | Value | Read by |
|---|---|---|
| `ado_org_url` | `https://dev.azure.com/<org>` | app (runtime env via bundle resource) |
| `ado_pat` | Azure DevOps PAT — Work Items R/W, Code R/W, Build R+Execute | app (runtime env via bundle resource) |
| `ado_project` | ADO project name (e.g. `home`) | ingest job (fallback when `--project` is empty) — **required before the daily schedule runs** |
| `genie_space_id` | Genie Space ID (32-hex) | app, looked up at runtime — no redeploy needed |

The app's service principal holds scope-level READ (granted by the bundle's secret
resources). Creating/updating secret *values* is typically a **HUMAN** step (agents are
often sandbox-blocked from secret writes): easiest is a workspace notebook —
`WorkspaceClient().secrets.put_secret("ado", "<key>", string_value="<value>")`.

## Runtime AI policy
The product calls **only Databricks-hosted AI**: Genie (Conversation API) today; any
future LLM routing uses a **Foundation Model APIs serving endpoint whose name is config**
(e.g. `databricks-meta-llama-3-3-70b-instruct`, `databricks-llama-4-maverick`, or the
Databricks-served Claude endpoints — an org policy choice). Do **not** introduce direct
external AI-vendor calls (Anthropic/OpenAI/etc. APIs) into the app. Coding agents that
help build this repo are dev-time tools only and never appear in the runtime path.

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

### G0. HUMAN — set the `ado_project` secret first
The job's **daily schedule** runs with an empty `--project` and falls back to the
`ado/ado_project` secret. If that secret is missing, every scheduled run fails with a
clear SystemExit. Set it before (or right after) the first deploy that includes the job.

### G1. Run the ingest job
The bundle deploys a job `ado-analytics-ingest` (dev mode prefixes the name). Trigger it with
explicit params — `workspace` is the Free Edition catalog; corporate workspaces may use another:
```bash
databricks jobs list -p "$ENV" | grep ado-analytics-ingest   # note the job id
databricks jobs run-now <job-id> -p "$ENV" \
  --python-params '["--catalog","workspace","--schema","ado_analytics","--project","<ADO project name>"]'
```
Wait for `TERMINATED SUCCESS`. Creates `workspace.ado_analytics.work_items` and
`…work_item_daily`. The schedule ships **UNPAUSED** (daily 05:00 UTC) — G0 must be done.

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

### G6. HUMAN — grants for the freshness stamp + Refresh button (optional)
The Analytics tab shows *"Data as of <date>"* and a **Refresh now** button. Both degrade
gracefully (they hide) unless the **app's service principal** gets:
- **Can use** on the SQL warehouse (SQL Warehouses → Permissions) — powers the freshness query.
- **Can Manage Run** on the `ado-analytics-ingest` job (job → Permissions) — powers Refresh.

### G7. Verify
- `GET <app-url>/api/health` → `"genie_configured": true`
- Analytics tab → ask "How many open work items are there by state?" → answer + table.
- Direct API check: `w.genie.start_conversation_and_wait(space_id, question)` should return
  `COMPLETED` with a text/query attachment.
- `GET <app-url>/api/analytics/freshness` → `{"available": true, "asOf": "<date>"}` (after G6).

Failure modes: `INSUFFICIENT_PERMISSIONS … USE SCHEMA` → G2 missing for whoever asked;
`genie_configured: false` → G4 missing; app's /api/genie/ask fails but direct API works → G5
missing; scheduled ingest fails at startup → G0 missing; freshness bar hidden → G6 missing.

---

## App-state store activation (Phase 4A — settings, audit log)

The app persists per-user settings and an audit log in Delta
(`{store_catalog}.{store_schema}`, default `workspace.ado_companion_app`). The app
creates its **tables**, but the **schema + grants** are a HUMAN step (SQL editor):

```sql
CREATE SCHEMA IF NOT EXISTS workspace.ado_companion_app;
GRANT USE SCHEMA, CREATE TABLE, SELECT, MODIFY
  ON SCHEMA workspace.ado_companion_app TO `<app-sp-client-id>`;
```

Verify: `GET <app-url>/api/whoami` → `"store": {"available": true}`. Without the grant
the app still works — settings/audit just report unavailable (`activity log: off` in the
user popover). Identity comes from the `X-Forwarded-Email` /
`X-Forwarded-Preferred-Username` headers Databricks Apps injects; `/api/whoami.source`
shows which header matched (`none` means the platform isn't forwarding identity —
check the app's user authorization settings).

## Operational rules (learned in production bring-up — do not relearn these)

1. **One owner per Databricks resource.** The app must be created/updated only by the
   pipeline's deploy principal. A manual deploy by a human user makes the next pipeline
   deploy fail with `409 ALREADY_EXISTS` — fix by deleting the app and letting the
   pipeline recreate it. Never hand-deploy to stg/prod.
2. **Catalog differs by edition.** Free Edition's default Unity Catalog is `workspace`;
   corporate metastores usually use `main` or a domain catalog. The ingest job's
   `--catalog` param and the app's `ANALYTICS_CATALOG` env must match.
3. **Schema ownership ⇒ grants.** Tables created by the deploy principal are invisible
   to everyone else (including the app SP and Genie callers) until a human runs the
   USE SCHEMA / SELECT grants. Genie executes SQL **as the caller**, so grant every
   principal that will ask questions.
4. **Spark schema inference breaks on all-NULL columns** (fresh projects have no
   completed/assigned items). The ingest job uses explicit StructTypes — keep it that way
   when adding fields.
5. **CI watchers must key on a specific build id**, not "latest build" — polling `$top=1`
   right after a merge races the queue and can see the *previous* run's success.
6. **Mirror + PR flow:** agents push feature branches only; a mirror (if used) lands them
   in the canonical repo; a **human always completes the PR into dev/stg/prod** — agents
   must not merge past protected branches even when technically able.
7. **Secret values, RBAC grants, PR merges, and Genie Space sharing are HUMAN actions.**
   Sandboxed agents are (correctly) blocked from them; design flows so these are few,
   explicit, and listed for the human rather than attempted.
8. **Bundle-deployed resources can lock their UI.** Jobs/apps deployed by a bundle are
   marked as bundle-managed and the workspace UI may refuse edits (including the
   permissions dialog). Use the Permissions REST API / SDK instead — e.g. from a notebook:
   `w.api_client.do("PATCH", "/api/2.0/permissions/jobs/<id>", body={"access_control_list":
   [{"service_principal_name": "<app-sp-client-id>", "permission_level": "CAN_MANAGE_RUN"}]})`.
9. **Identity search uses the Identity Picker API** (`POST /_apis/IdentityPicker/Identities`,
   `api-version=7.1-preview.1` — the same endpoint the ADO web UI uses; org-level, not
   project-scoped). Its `options` must include **both** `MinResults` and `MaxResults` or
   the call 400s. Assigning a work item accepts the identity's mail/uniqueName as the
   `System.AssignedTo` value.
10. **The two data planes drift.** CRUD tabs are live (ADO REST), the Overview is
   near-live (ADO Analytics OData), Genie is batch (Delta, refreshed by the ingest
   schedule or the Refresh button). Surface freshness in the UI; never imply Genie
   answers are real-time.
