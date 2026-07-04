# Corporate bootstrap — the pre-script

> **Audience: the AI agent session doing first-time setup in a corporate
> workspace** (and Jason, who executes the HUMAN steps it hands him). This is
> the *orchestration* layer: it sequences the runbooks that already exist —
> `SETUP_DATABRICKS.md` (app), `docs/CICD.md` (pipelines), `AGENTS.md`
> (secrets, Genie, store, copilot, evals) — into one ordered script with a
> verification gate after every phase. **Do the phases in order; do not start
> a phase until the previous gate passes.** Where a step says HUMAN, produce
> the exact SQL/CLI/notebook cell and hand it over — do not attempt it
> (secret writes, grants, PR merges, and Space sharing are classifier-blocked
> for agents, by design).

## Phase 0 — Inputs (collect ALL of these before touching anything)

Ask the human for, and record in the session:

| # | Input | Example |
|---|---|---|
| 1 | Corporate Databricks workspace URL | `https://corp-workspace.cloud.databricks.com` |
| 2 | Databricks auth for the agent (PAT or CLI profile) | `dapi…` |
| 3 | Catalog to use (NOT `workspace` in corporate) | `main` or a domain catalog |
| 4 | ADO org URL + project + repo | `https://dev.azure.com/<org>` / `<project>` / `ado` |
| 5 | ADO PAT (scopes: Work Items R/W, Code R/W, Build R+E) | `…` |
| 6 | Serving endpoint names available (Llama and/or Claude) | `databricks-claude-sonnet-5` |
| 7 | SQL warehouse id the app may use | `abc123…` |
| 8 | Which branch = this environment (`dev`/`stg`/`prod`) | `stg` |
| 9 | The public GitHub repo URL/snapshot for the ONE-TIME import | `https://github.com/jpaladini/ado` |

Gate: every row filled. Also confirm **network egress**: from a notebook in the
corporate workspace, `import requests; requests.get("https://dev.azure.com")`
must succeed — the whole operational plane depends on it (PLAN §8 risk).

## Phase 1 — Repo import (ONE-TIME) + pipelines

> **Corporate has no GitHub and no mirror.** The GitHub → mirror-Action → ADO
> loop in `docs/CICD.md` is the **outside-development model only** (personal
> dev, and any future work done outside the corporate network — keep it, it's
> the path new features arrive on). In corporate the code arrives **once**,
> and from that moment every change originates inside the corporate network:
> feature branch in the corporate ADO repo → PR into the env branch →
> pipeline. Nothing flows in automatically afterwards; the two repos are
> expected to drift, and any future refresh from outside is a deliberate,
> human-reviewed re-import — never a sync job.

1. HUMAN: **one-time import** — ADO Repos → *Import repository* with the
   GitHub URL (input #9); if egress policy blocks the importer, clone locally
   and `git push --mirror` from inside the network. After the import,
   `.github/workflows/mirror-to-ado.yml` is inert (Actions don't run in ADO)
   — leave it in the tree as documentation of the outside loop, or delete it
   in the first corporate PR; either is fine.
2. HUMAN: create the deploy **service principal** in the corporate workspace,
   then the ADO **variable group** `databricks-<env>` with `DATABRICKS_HOST`,
   `DATABRICKS_CLIENT_ID`, `DATABRICKS_CLIENT_SECRET` (docs/CICD.md §1–2 —
   these sections are ADO-native and apply unchanged).
3. HUMAN: register `azure-pipelines.yml` + `azure-pipelines-validate.yml` and
   protect the env branch (only humans complete PRs into it). Set the repo's
   **default branch** to the env branch — the dev org's default branch was a
   stale feature branch and code search/Code tab suffered for it.

Gate: the import shows the full history; a trivial feature-branch commit made
*inside* the corporate ADO repo raises a PR into the env branch and the
validate pipeline runs on it.

## Phase 2 — Secrets (AGENTS.md "Secrets reference"; HUMAN via notebook)

HUMAN runs (agent prepares the cell, values from Phase 0):

```python
from databricks.sdk import WorkspaceClient
w = WorkspaceClient()
w.secrets.create_scope("ado")   # skip if it exists
for k, v in {
    "ado_org_url": "<input 4>",
    "ado_pat": "<input 5>",
    "ado_project": "<project name>",
    # set later in their phases: genie_space_id, copilot_endpoint, mlflow_experiment_id
}.items():
    w.secrets.put_secret("ado", k, string_value=v)
```

Gate: `w.secrets.list_secrets("ado")` shows the three keys.

## Phase 3 — First deploy (the delivery loop, never manual)

1. AGENT: set the catalog for this env — `databricks.yml` target vars and the
   app's `ANALYTICS_CATALOG`/`STORE_CATALOG` env must say the Phase-0 catalog,
   NOT `workspace` (operational rule 2). Commit via branch → PR.
2. HUMAN: merge the PR into the env branch → pipeline deploys the bundle
   (app + ingest job). **Never** `bundle deploy` by hand — one owner per
   resource (operational rule 1).

Gate: `GET /api/2.0/apps/ado-companion` shows RUNNING with a fresh
`active_deployment.create_time`; the app URL loads; `/api/health` shows
`ado_configured: true`. Work Items / PRs / Code tabs show live data.

## Phase 4 — App-state store (AGENTS.md "App-state store activation")

HUMAN (SQL editor; catalog from Phase 0, app SP client id from the app page):

```sql
CREATE SCHEMA IF NOT EXISTS <catalog>.ado_companion_app;
GRANT USE SCHEMA, CREATE TABLE, SELECT, MODIFY
  ON SCHEMA <catalog>.ado_companion_app TO `<app-sp-client-id>`;
```

Gate: `GET <app-url>/api/whoami` → `"store": {"available": true}`. The app
creates its own tables (settings, audit_log, ai_sessions, saved_reports) and
the 4E metric view on first use — no further SQL needed.

## Phase 5 — Analytics + Genie (AGENTS.md G0–G7, in their order)

1. AGENT: run the ingest job once (G1) → `<catalog>.ado_analytics.work_items`
   + `work_item_daily` exist.
2. HUMAN: grants (G2) — USE SCHEMA + SELECT on `<catalog>.ado_analytics` to
   the app SP **and every human who will ask Genie questions** (Genie runs SQL
   as the caller — operational rule 3).
3. AGENT: create the Genie Space (G3); HUMAN: store `genie_space_id` secret
   (G4) and share the Space with the app SP (G5); optional freshness/refresh
   grants (G6).

Gate: G7 — the app's Insights freshness bar shows a date; a Genie question
answers in the copilot's `query_analytics_history` tool.

## Phase 6 — Copilot + tracing (AGENTS.md C0–C4)

1. HUMAN: set `copilot_endpoint` to the chosen serving endpoint (C1) — start
   with whichever is cheapest; Phase 7 decides the final one.
2. AGENT: create the MLflow experiment (C2); HUMAN: grant the app SP CAN_EDIT
   on it and set `mlflow_experiment_id`; HUMAN: endpoint access for the app SP
   if the workspace gates serving endpoints (C3).

Gate: C4 — a copilot question answers with tool chips; the turn appears as a
trace in the experiment; an AI action lands in the audit log.

## Phase 7 — Model comparison (evals/README.md — the whole point)

AGENT: follow `evals/README.md` end to end: run the suite once per candidate
endpoint with **one pinned judge**, compare the two runs in the evaluation UI,
apply the hard-gate rule. HUMAN: `put_secret("ado", "copilot_endpoint", …)`
with the winner. No redeploy.

Gate: two evaluation runs visible side by side; the winning endpoint answers
the copilot's next turn (check the trace's endpoint attribute).

## Phase 8 — Sign-off checklist

- [ ] All tabs live against corporate ADO; search returns work items, PRs, code
- [ ] Reports tab renders; builder runs a query (metric view auto-created)
- [ ] .xlsx and .pdf exports download
- [ ] Copilot: proposal → Apply → audit row; session restores after reload
- [ ] Ingest job scheduled (unpause it — G1 note) and freshness bar shows it
- [ ] Corporate uses its OWN PATs/SPs/secrets (dev credentials never travel here —
      promotion is a pure code merge); dev PATs are only an open-sourcing concern for
      the dev repo, not this environment
- [ ] `NEXT_SESSION.md` updated with corporate identifiers (new §3 table)

**Order matters and the gates are the script.** If a gate fails, stop and fix —
every downstream phase assumes it. Total human actions: ~8 notebook/SQL cells
and a handful of PR merges; everything else is the agent's.
