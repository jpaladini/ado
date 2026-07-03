# NEXT_SESSION.md — session handoff & resume guide

> **For the next Claude Code session (and for Jason).** This file captures the complete
> working state as of **2026-07-03** so a fresh session can resume in minutes. Read this,
> then `AGENTS.md` (runbooks + operational rules), then `PLAN.md` (roadmap). Do not
> re-derive or re-create any infrastructure listed here — it exists and works.

---

## 1. What this project is (one paragraph)

**ADO Companion** — a web app on **Databricks Apps** (React/Vite SPA + FastAPI in one
process) that is a full companion to **Azure DevOps**: live CRUD over work items / PRs /
pipelines / code (ADO REST API), near-live dashboards (ADO Analytics OData, server-side
`$apply`), and **Genie natural-language analytics** over Delta tables refreshed by a
scheduled ingest job. All runtime AI is Databricks-native. Delivery is fully automated:
**GitHub → mirror Action → Azure DevOps Repos → human-merged PR into `dev` → Azure
Pipeline → `databricks bundle deploy` → live app.**

## 2. Session bootstrap (do this first)

1. Jason provides two tokens in chat (he has them ready; **never commit them**):
   - **Databricks PAT** (workspace `https://dbc-49fa4800-f5f0.cloud.databricks.com`)
   - **Azure DevOps PAT** (org `https://dev.azure.com/jpaladini85`, scopes: Code R/W, Build R/E, Work Items R/W)
2. Use them **inline in Bash env vars per command** — a sandbox classifier blocks writing
   them to files. Pattern used throughout the prior session:
   ```bash
   DBX="https://dbc-49fa4800-f5f0.cloud.databricks.com"; DTOK="<databricks-pat>"
   APAT="<ado-pat>"
   curl -s -H "Authorization: Bearer $DTOK" "$DBX/api/2.0/apps/ado-companion" | python3 -m json.tool
   curl -s -u ":$APAT" "https://dev.azure.com/jpaladini85/home/_apis/projects?api-version=7.1"
   ```
3. Git: the repo clones from GitHub (`jpaladini/ado`); work happens on **whatever branch
   the session was started with** (e.g. `claude/resume-next-session-pbbmrk` on 2026-07-02;
   earlier sessions used `claude/web-first-app-planning-xsz5l0`). The mirror Action pushes
   **any** non-protected branch to a same-named branch in ADO, so the PR-into-`dev` loop
   works from any session branch — just source the ADO PR from the branch you pushed.

## 3. Canonical identifiers (verified working)

| Thing | Value |
|---|---|
| Databricks workspace | `https://dbc-49fa4800-f5f0.cloud.databricks.com` (Free Edition; catalog is `workspace`) |
| App | `ado-companion` → `https://ado-companion-4201007868433203.aws.databricksapps.com` |
| App service principal | name `app-2spmvx ado-companion`, client id `b2302135-7ea2-4ec8-baad-b658574ad54a` |
| Pipeline/deploy SP | `dbx-svc-pcp` (`4157ee2f-308c-41bc-9f64-75c7154971e4`) — owns bundle resources |
| SQL warehouse | `Serverless Starter Warehouse`, id `93c5f9f3549e0e4a` |
| Ingest job | `ado-analytics-ingest` (dev name prefixed), job id `107551918974938`, daily 05:00 UTC UNPAUSED |
| Genie Space | `ADO Companion Analytics`, space id `01f175a49a6f18758e5c5007a99296eb` |
| Analytics tables | `workspace.ado_analytics.work_items`, `workspace.ado_analytics.work_item_daily` |
| Copilot endpoint (dev) | `databricks-llama-4-maverick` (Claude endpoints are rate-limited to 0 on Free Edition) |
| MLflow experiment | `/Shared/ado-companion-copilot`, id `3567576457281688` (copilot turn traces) |
| App-state store | `workspace.ado_companion_app` (`settings`, `audit_log`) — schema + grants exist |
| ADO org / project / repo | `jpaladini85` / `home` / `ado` |
| ADO deploy branch | `dev` (protected; **only Jason merges PRs into it** — agent merge is classifier-blocked by design) |
| GitHub repo | `jpaladini/ado`; mirror workflow `.github/workflows/mirror-to-ado.yml` |
| Secrets (scope `ado`) | `ado_org_url`, `ado_pat`, `ado_project`(=home), `genie_space_id`, `copilot_endpoint`, `mlflow_experiment_id` — all set |

## 4. The delivery loop (use it for every change)

**The pipeline flow, component by component (this is THE mechanism — nothing deploys any
other way):**

```
1. git push → GitHub repo jpaladini/ado, on the current session branch
2.   triggers GitHub Action: .github/workflows/mirror-to-ado.yml
3.     which force-pushes the same branch → Azure DevOps repo jpaladini85/home/_git/ado
4.       agent creates a PR (branch → dev) via the ADO REST API
5.         Jason merges the PR (human gate — protected branch)
6.           merge to dev triggers Azure Pipeline: azure-pipelines.yml
7.             pipeline: npm build → databricks bundle validate/deploy -t dev → bundle run
8.               Databricks App `ado-companion` (and bundle jobs) updated in the workspace
```

Auth notes: the mirror Action authenticates with GitHub secrets `ADO_REPO_URL`/`ADO_PAT`;
the pipeline authenticates to Databricks with pipeline variables `DATABRICKS_HOST` /
`DATABRICKS_CLIENT_ID` / `DATABRICKS_CLIENT_SECRET` (service principal `dbx-svc-pcp`).

Working recipe around that flow:

```
edit code → build frontend if changed (cd frontend && npm run build; output is COMMITTED in src/static)
→ pytest (cd src && pytest)  → git commit + push (GitHub)
→ mirror lands branch in ADO (~seconds; poll refs API until your sha appears)
→ create PR via ADO API (allowed) → Jason merges (his click, always)
→ pipeline builds+deploys (~3.5 min; poll builds API BY BUILD ID, not $top=1 — race!)
→ verify via Databricks API (app deployment time/state) and feature-specific checks
```

PR creation recipe (works):
```bash
curl -s -u ":$APAT" -X POST "https://dev.azure.com/jpaladini85/home/_apis/git/repositories/ado/pullrequests?api-version=7.1" \
  -H "Content-Type: application/json" -d '{"sourceRefName":"refs/heads/claude/web-first-app-planning-xsz5l0","targetRefName":"refs/heads/dev","title":"...","description":"..."}'
```

**Sandbox classifier hard-blocks (hand these to Jason instead, usually as a notebook cell
or SQL — he's fast with them):** secret writes, any RBAC/GRANT/permissions API call,
completing/merging PRs, broad destructive ops. Everything else (job run-now, PR create,
API reads, Genie space creation) is allowed.

## 5. Current state (as of 2026-07-03 handoff)

**Everything below is merged & deployed** (PR ledger: #6–#19, all completed; the
2026-07-02/03 session shipped #9–#19). The app is feature-complete through Phase 4C+4F:

- **Tabs**: Overview (live OData aggregates) · Work Items (full CRUD, drawers, AI
  draft/improve buttons) · Pull Requests (detail drawer: files, difflib diffs, threads,
  comments, in-place AI review w/ validated line anchors) · Pipelines · Code (3-pane
  browser: branch picker, lazy tree, highlight.js viewer, collapsible rails, markdown
  Preview, plain-language Explain) · **AI Copilot** (tool-calling agent) · **Reports**
  (Observable Plot flow analytics) · settings/audit footer.
- **AI copilot (4D + hardening)**: FMAPI agent loop, propose-then-apply (write tools
  NEVER execute — proposal cards Apply through normal REST routes), write-target
  verification (guessed work-item/PR ids rejected mid-loop), llama text-form tool-call
  fallback parser, outcome notes round-tripped in history, Genie as the
  `query_analytics_history` tool, `get_flow_metrics` tool (business days).
- **In-place AI (the "buttons over chat" layer)**: suggest-workitem, review-pr (server
  validates every suggested line against real right-side hunk lines — clamp/drop),
  explain-file. All: audit actions (`ai.suggest/review/explain`) + MLflow spans with
  token usage. Buttons gated on `copilot_configured`.
- **Reports (4C)**: one `/api/projects/{p}/reports` round trip; filters
  range/types/assignees; KPI strip, created-vs-completed, CFD, cycle-time scatter w/
  p50/p85 bands, aging WIP (red above p85), workload, needs-attention. **All durations
  are 5-day-workweek business days** (`business_days_between` — retired Jason's custom
  Power BI semantic model; holidays = future setting). Charts: **Observable Plot**
  (ISC, lazy chunk, no external calls, themed on CSS tokens → dark mode free) via
  `PlotFigure` (re-renders on resize + theme flip).
- **Observability**: every model call traced to experiment 3567576457281688 with token
  usage; every AI/mutating action in `workspace.ado_companion_app.audit_log`.
- **Tests**: 88 pytest (19 new for the report builder), ~72% line coverage (client 92%, ai 83%; routes 56% — offered
  TestClient+CI-gate PR, not yet requested). Frontend has no automated tests
  (Playwright screenshots + live smokes per PR instead).

**Next up (agreed order):**
1. ~~4E report builder~~ **SHIPPED 2026-07-03**: metric view
   `workspace.ado_companion_app.work_items_metrics` (YAML in
   `src/app/reportbuilder.py`, app-created lazily via the warehouse so the app SP
   owns it and CREATE OR REPLACE works on version bumps); builder UI on Reports
   (dims × measures × chart: auto/bar/line/area/table); per-user saved reports in
   `ado_companion_app.saved_reports`; endpoints `GET /api/reports/builder/meta`,
   `POST /api/reports/builder/run`, `GET/PUT/DELETE /api/reports/saved`; audit
   actions `report.run/save/delete`. Lead-time measures use a SQL business-days
   closed form (epoch-Monday method) tested equal to `business_days_between`.
   Deferred: builder filter UI (backend already accepts parameterized filters).
2. Copilot session history (store table `ai_sessions` was designed for it in 4A).
3. Artifacts: PDF/Excel exports from copilot + Reports (openpyxl/weasyprint).
4. Small: PR/work-item row-click affordance chevrons (promised, unshipped);
   route-tests + coverage gate; model eval harness before swapping
   `copilot_endpoint` to `databricks-claude-sonnet-5` in corporate.

**Blog**: Parts 1–6 drafted in `docs/blog/`, all `draft: true`, screenshot slots
marked (1 build+CI/CD · 2 OData · 3 copilot · 4 MLflow tracing · 5 in-place AI ·
6 flow metrics/business days/Plot). `WEBSITE_HANDOFF.md` = self-contained publishing
instructions for Jason's website agent (Astro + Tailwind site, minimalist B&W,
jpaladini.vercel.app, no blog section yet). Jason has the handoff files in chat too.

**Open-sourcing** remains a goal: keep AGENTS.md self-sufficient; never commit tokens;
**rotate both PATs before going public** (they appeared in session transcripts).

## 6. Architecture cheat sheet (where things live)

```
src/app/main.py            FastAPI app + pure-ASGI AuditMiddleware (logs mutations)
src/app/api/routes.py      all /api endpoints (BFF)
src/app/ado/client.py      operational plane: live ADO REST (httpx, PAT basic auth)
src/app/ado/analytics.py   analytical plane: ADO Analytics OData ($apply, snapshots)
src/app/genie.py           Genie Conversation API client (space id from secret at runtime)
src/app/copilot.py         AI copilot: FMAPI tool-calling agent loop, propose-then-apply,
                           write-target verification, text-form call fallback, MLflow tracing
src/app/ai.py              single-shot AI: suggest_work_item, review_pr (line validation),
                           explain_file — shares copilot's endpoint/tracing plumbing
src/app/insights.py        table freshness (DESCRIBE DETAIL) + ingest run-now
src/app/store.py           Delta app-state store (settings, audit) — parameterized SQL,
                           batched audit writes, graceful degradation, 120s re-probe
src/app/identity.py        X-Forwarded-* header identity
jobs/ingest_ado_analytics.py  OData → Delta job (explicit schemas! all-NULL gotcha)
frontend/src/screens/      Overview, WorkItems, PullRequests, Pipelines, Code, Copilot, Reports
frontend/src/components/   Shell, Drawer(+Field/Select), AIButton, PlotFigure, CodeBlock,
                           FreshnessBar, UserFooter, Toast, ui, icons
frontend/src/lib/          theme, tokens, text (html<->text), highlight (lazy hljs),
                           markdown (safe mini-renderer), plot (lazy Observable Plot + palette)
databricks.yml             Asset Bundle: app + secret resources + ingest job (dev/stg/prod targets)
azure-pipelines.yml        deploy on merge to dev/stg/prod (SP auth via pipeline variables)
```

Design invariants: two data planes (operational never depends on analytical);
env-specifics only in secrets; graceful degradation everywhere; every feature lands
via the PR loop; design tokens + IBM Plex for all UI (see tailwind.config.js).

## 7. Verification one-liners (run any time to re-establish state)

```bash
# app + deployment
curl -s -H "Authorization: Bearer $DTOK" "$DBX/api/2.0/apps/ado-companion" | python3 -c "import sys,json;d=json.load(sys.stdin);print((d.get('app_status') or {}).get('state'), (d.get('active_deployment') or {}).get('create_time'))"
# latest pipeline build
curl -s -u ":$APAT" 'https://dev.azure.com/jpaladini85/home/_apis/build/builds?$top=1&api-version=7.1' | python3 -c "import sys,json;b=json.load(sys.stdin)['value'][0];print(b['buildNumber'],b['status'],b.get('result'))"
# store / audit sanity (SQL via warehouse)
# SELECT * FROM workspace.ado_companion_app.audit_log ORDER BY ts DESC LIMIT 5
# genie sanity (python, needs databricks-sdk + env DATABRICKS_HOST/TOKEN)
# w.genie.start_conversation_and_wait("01f175a49a6f18758e5c5007a99296eb", "how many open work items by state?")
```

## 8. Working agreements with Jason

- **All changes through the trunk** — no manual deploys, no out-of-band edits.
- Jason merges every PR into `dev`; agent creates PRs and watches builds.
- Human-only actions (secrets/RBAC/merges/Genie sharing): give Jason a **ready-to-paste
  notebook cell or SQL** — he executes fast.
- **Do not revoke his PATs**; he reuses them across sessions.
- Verify with screenshots (Playwright, headless shell at
  `/opt/pw-browsers/chromium_headless_shell-1194/chrome-linux/headless_shell`, mock the
  /api routes — see prior pattern) and live API checks; report honestly what's mocked
  vs real.
- Keep `AGENTS.md` updated with every new operational lesson — open-source readiness.
