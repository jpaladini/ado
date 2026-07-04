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
| `copilot_endpoint` | FMAPI chat endpoint name for the AI copilot (e.g. `databricks-llama-4-maverick`; enterprise: `databricks-claude-sonnet-5`) | app, runtime — no redeploy |
| `mlflow_experiment_id` | MLflow experiment id for copilot turn tracing (optional) | app, runtime — no redeploy |

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
- AI Copilot tab → ask a historical question ("How did open items trend this month?")
  → the trace/tool chips show `query_analytics_history` and the answer cites batch data.
  (The Genie chat UI was folded into the copilot on 2026-07-02; there is no separate
  Genie chat on the Analytics tab anymore. The `/api/genie/ask` endpoint still works.)
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

## AI Copilot activation (Phase 4D — tool-calling agent + MLflow tracing)

The AI tab is a **tool-calling agent** over a Databricks FMAPI serving endpoint. It is
not Genie: it acts on the *operational* plane (live ADO REST) through the same client
the REST routes use. Genie remains the batch/historical analytics surface.

### Design contract (implement/modify against these invariants)
- **Propose-then-apply.** Read tools execute immediately inside the agent loop. Write
  tools (`create_work_item`, `update_work_item`, `add_work_item_comment`) are NEVER
  executed server-side by the loop — each call is returned to the UI as a *proposal*
  `{id, tool, args}`; the UI's Apply button calls the ordinary REST route, so audit
  logging, permissions, and code paths are byte-identical to a human click. Keep this
  invariant when adding tools: new write capabilities = new proposal types + an Apply
  mapping in the UI, never direct execution in the loop.
- **Write proposals are verified before they surface.** `update_work_item` /
  `add_work_item_comment` proposals trigger a server-side `get_work_item` on the target
  id; a 404 rejects the proposal and the error is fed back to the model mid-loop so it
  self-corrects (models guess sequential IDs — a deleted probe item once caused exactly
  this). Rejections appear in the trace as `verify:{tool}` spans. Keep this check when
  adding write tools that reference existing entities.
- **Apply outcomes round-trip.** The UI appends a `[Proposal outcomes: …]` note
  (applied / dismissed / failed: <error> / not applied yet) to each assistant turn in
  the history it sends, and the system prompt tells the model to read it — so "try
  again" and "do the rest" work, and nothing already applied is re-proposed. Preserve
  this note format if you rework the frontend.
- **Wire protocol** is OpenAI-style chat completions with `tools`, POSTed to
  `{workspace}/serving-endpoints/{name}/invocations`. Auth: `WorkspaceClient().config
  .authenticate()` gives refreshed bearer headers for both SP (in-app) and PAT (dev).
- **Reasoning models** (e.g. gpt-oss) return `content` as a list of typed blocks, not a
  string — extract only `{"type": "text"}` blocks (`_content_text` in copilot.py).
- **Llama-family models sometimes emit tool calls as plain text** — e.g.
  `update_work_item(id=2, tags="triage")` plus a stray `assistant` template token —
  typically for the 2nd+ call of a multi-item request. The loop lifts these into real
  tool calls via `_parse_text_tool_calls` (regex fallback) so proposals aren't silently
  lost. Keep this fallback when changing the loop; prompt rules alone do not fix it.
- **Loop bounds**: MAX_TURNS=8 model calls per user message; tool results truncated to
  6000 chars before being fed back.
- **Endpoint + experiment are per-workspace config** read at runtime (no redeploy):
  env `COPILOT_ENDPOINT` / secret `ado/copilot_endpoint`; env `MLFLOW_EXPERIMENT_ID` /
  secret `ado/mlflow_experiment_id`.
- **MLflow tracing is optional and never fatal**: every turn logs a `copilot.turn` span
  with child `llm` spans (per model call: message count, finish_reason, token usage) and
  `tool:{name}` spans (args in, truncated result out). Any tracing failure downgrades to
  no-op — a chat turn must never break because tracing is misconfigured.
- **Genie is a copilot tool**: `query_analytics_history` calls the Genie space for
  BI/historical questions (batch Delta data). The system prompt requires the model to
  distinguish live tools from this batch tool and say which one an answer came from.
- Where things live: `src/app/copilot.py` (loop, tool registry, tracing),
  `/api/copilot/chat` in `src/app/api/routes.py`, audit action `copilot.chat` in
  `src/app/main.py`, UI `frontend/src/screens/Copilot.tsx` (proposal cards + Apply).

### C0. Choose the serving endpoint
List candidates: `GET /api/2.0/serving-endpoints` — you want `task: llm/v1/chat` and
tool-calling support. Verified working choices:
- **Free Edition**: `databricks-llama-4-maverick` (default) or
  `databricks-meta-llama-3-3-70b-instruct`. The Claude endpoints
  (`databricks-claude-sonnet-5`, `databricks-claude-opus-4-8`) are visible but
  **Databricks-rate-limited to 0** on Free Edition — calls fail with
  `PERMISSION_DENIED: temporarily disabled due to a Databricks-set rate limit of 0`.
- **Enterprise**: prefer `databricks-claude-sonnet-5` (strongest tool use); any
  chat endpoint with function calling works. Smoke-test tool calling first:
  POST one message + one tool schema to `/serving-endpoints/<name>/invocations` and
  confirm the response's `finish_reason` is `tool_calls`.

### C1. HUMAN — set the endpoint secret
```python
WorkspaceClient().secrets.put_secret("ado", "copilot_endpoint", string_value="<endpoint-name>")
```
The app reads it at runtime — no redeploy. `GET /api/health` → `"copilot_configured": true`.

### C2. Create the MLflow experiment (agent-allowed) + HUMAN grant
```bash
curl -X POST "$DBX/api/2.0/mlflow/experiments/create" -H "Authorization: Bearer $TOKEN" \
  -d '{"name": "/Shared/ado-companion-copilot"}'        # returns experiment_id
```
Then (HUMAN) set the secret and grant the **app SP** permission to log traces:
```python
w = WorkspaceClient()
w.secrets.put_secret("ado", "mlflow_experiment_id", string_value="<experiment_id>")
w.api_client.do("PATCH", "/api/2.0/permissions/experiments/<experiment_id>",
  body={"access_control_list": [{"service_principal_name": "<app-sp-client-id>",
                                 "permission_level": "CAN_EDIT"}]})
```
Tracing is optional: skip C2 entirely and the copilot still works, just untraced.

### C3. HUMAN — endpoint access for the app SP (enterprise)
On Free Edition pay-per-token endpoints are workspace-queryable by default. In
enterprise workspaces confirm the app's service principal has **Can Query** on the
chosen serving endpoint (Serving → endpoint → Permissions).

### C4. Verify
- `GET <app-url>/api/health` → `"copilot_configured": true`
- AI tab → "What's open right now?" → answer with `read:` tool chips.
- Ask it to create/update something → a proposal card appears; **Apply** executes and
  the row lands in `workspace.ado_companion_app.audit_log` (action `workitem.*`), plus
  a `copilot.chat` row for the conversation turn itself.
- Experiment `/Shared/ado-companion-copilot` → Traces tab shows a `copilot.turn` trace
  per question with nested `llm` / `tool:*` spans.

Failure modes: `copilot_configured: false` → C1 missing; 502 "Model endpoint returned
403/404" → C3 missing or endpoint name wrong; traces absent but chat works → C2
missing/ungranted (by design, non-fatal).

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
11. **Search is two services with different availability.** Work-item search
   (`almsearch.dev.azure.com …/workitemsearchresults`) is built into ADO Services and
   just works (WIQL `CONTAINS` is the fallback). **Code search is a marketplace
   extension (`ms.vss-code-search`) this org does NOT have** — `…/codesearchresults`
   answers `count: 0, infoCode: 6` instead of erroring, which looks like "no matches".
   The BFF therefore greps the repos itself (`app/codesearch.py`: TTL-cached index of
   every text file on each repo's `dev`-or-default branch, minified/lockfile/binary
   skip-lists, capped). If the extension is ever installed, swap the module — the
   route contract stays. Note: this org's repos' *default* branch is a stale feature
   branch; the index prefers `dev`. Consider fixing the default branch in ADO.
12. **`connectionData` is UNVERSIONED.** `GET /_apis/connectionData` returns **400** if
   you send `api-version` — but the client stamps it on every request. This silently
   broke PR Approve (it resolves the reviewer id through connectionData) and the app
   footer's display name. `client.connection_data()` calls it WITHOUT the param. If you
   add another unversioned endpoint, do the same.
13. **Llama emits tool calls as text, two ways.** (a) flat `update_work_item(id=2, ...)`
   and (b) **python-style with nested payloads and unquoted tokens** —
   `create_code_pr(repositoryId=<bare GUID>, baseBranch=main, edits=[{...}])` — instead
   of a structured tool_call. `copilot.py` has TWO fallback parsers: `_parse_text_tool_calls`
   (flat) and `_lift_python_style_calls` (quote/depth-aware, handles the nested case). This
   is the #1 coding-agent failure on llama and the strongest argument for a frontier model
   in corporate. Malformed tool-arg JSON gets PRECISE feedback (re-send with `\n` escaping),
   never a generic missing-fields error (that sent llama into apology spirals). The eval
   task `coding_agent_ci_pipeline` guards this end-to-end.
14. **Repo default-branch fix on import** (do it for every migrated repo). ADO's importer
   preserves the source's default branch (often a stale `claude/…` branch). Create the real
   trunk (`main`/`dev`) at the head, then PATCH the default — **GOTCHA: PATCH by repo NAME
   returns 400; use the repo GUID.** The Code tab + search index follow `dev`-then-default,
   so a bad default degrades both. Full steps in `docs/REPO_ONBOARDING_E2E.md`.
15. **fpdf2 over weasyprint for PDF.** weasyprint needs system cairo/pango — a pip install
   that fails at deploy time blocks EVERY future deploy, not just the PDF button. fpdf2 is
   pure Python. Choose libraries by their deploy-time failure mode, not just features.
16. **The copilot has NO merge tool, by design.** It proposes code (create_code_pr) → Apply
   opens a PR → a HUMAN clicks Merge in the UI. `complete_pull_request` is only reachable
   from the Merge button, which only shows when ADO reports the PR approved + conflict-free.
   This preserves "the AI writes code; it cannot merge code" — the roadshow's spine. Do not
   add a merge tool to the copilot.
17. **Genie Code is UI-only (no API).** Databricks's own coding agent (launched 2026-03)
   runs on workspace compute but can't be invoked programmatically from our app. Integration
   paths: Git folder sync (Genie Code works the repo with compute) and/or expose ADO
   Companion as an MCP server (Genie Code drives our governed tools). Our in-app copilot
   stays FMAPI+tools with a Claude endpoint in corporate.

## Model eval harness (compare copilot endpoints before swapping)

The corporate question "Llama or Claude for `copilot_endpoint`?" is answered by
`scripts/eval_copilot.py`: the SAME task suite (`evals/copilot_tasks.json`) runs
through the REAL agent loop (live read tools; writes stay proposals — nothing
mutates ADO), scored by deterministic checks (right tool called, proposal
contract honored, **no silent writes ever**, step budget) plus MLflow **LLM
judges** (per-task guidelines via `ExpectationsGuidelines`), one
`mlflow.genai.evaluate()` run per endpoint in `/Shared/ado-companion-evals`.

```bash
# env: ADO_ORG_URL, ADO_PAT, DATABRICKS_HOST, DATABRICKS_TOKEN; pip install pandas
python scripts/eval_copilot.py --endpoint databricks-llama-4-maverick \
  --judge-model databricks:/databricks-claude-sonnet-5
python scripts/eval_copilot.py --endpoint databricks-claude-sonnet-5 \
  --judge-model databricks:/databricks-claude-sonnet-5
```

Compare the runs side by side in the experiment's evaluation UI (each row links
its full trace). Rules learned bringing it up: **pin ONE judge model across both
runs** (strongest available; judging your own contestant inflates scores);
the script forces `mlflow.set_tracking_uri("databricks")` (local sqlite configs
otherwise hijack it); baseline 2026-07-03 (llama, self-judged): all scorers 1.0,
latency mean ~7s / p90 ~12s — the suite should grow harder tasks as regressions
appear. Keep tasks value-agnostic (no assertions on data that drifts).

**The full corporate runbook — ready-to-paste notebook cells, judge-pinning
rules, the deterministic-scorers-as-hard-gate decision rule, and the
secret-swap step — is `evals/README.md`.** Start there when asked to run the
Llama-vs-Claude comparison; it assumes no prior session context. (Genie is
NL-to-SQL and cannot run it — an agent session or notebook does.)

## Corporate bootstrap (first-time setup in a new workspace)

`docs/CORPORATE_BOOTSTRAP.md` is the **pre-script**: it sequences everything in
this file plus SETUP_DATABRICKS.md and docs/CICD.md into eight ordered phases
(inputs → mirror/pipelines → secrets → first deploy → store → analytics/Genie
→ copilot/tracing → model eval → sign-off), each with an AGENT/HUMAN marker and
a verification gate. When asked to "set everything up" in a new workspace,
start there and do not skip gates.
