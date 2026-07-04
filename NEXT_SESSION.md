# NEXT_SESSION.md — session handoff & resume guide

> **For the next Claude Code session (and for Jason).** This file captures the complete
> working state as of **2026-07-04** so a fresh session can resume in minutes. Read this,
> then `AGENTS.md` (runbooks + operational rules), then `PLAN.md` (roadmap). Do not
> re-derive or re-create any infrastructure listed here — it exists and works.
>
> **Doc map** (read in this order): `NEXT_SESSION.md` (this file — state + resume) →
> `AGENTS.md` (runbooks, operational rules, eval harness) → `PLAN.md` (roadmap) →
> for corporate rollout: `docs/CORPORATE_BOOTSTRAP.md` (8-phase ordered setup) +
> `docs/REPO_ONBOARDING_E2E.md` (migrate a repo + coding-agent test) +
> `evals/README.md` (Llama-vs-Claude model comparison).
>
> **The app is a full ADO client AND a coding agent now** — the copilot proposes code
> changes across all repos that Apply into real PRs (validate pipeline = CI, human
> merges). This is the roadshow story: *the AI writes code; it cannot merge code.*

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
| App-state store | `workspace.ado_companion_app` — tables `settings`, `audit_log`, `ai_sessions`, `saved_reports`, metric view `work_items_metrics` (all app-created on first use; schema + grants exist) |
| Copilot eval experiment | `/Shared/ado-companion-evals`, id `1855387441328379` (one run per endpoint; llama baseline + coding task logged) |
| ADO org / project / main repo | `jpaladini85` / `home` / `ado` |
| Other repos in `home` | `ado_`, `ado_buddy`, `home`, and **`streamlit-chess`** (id `ca9000f4-b595-4b19-a023-98e2bcff33e4`, default branch `main`, imported 2026-07-03 from github.com/jpaladini/streamlit-chess as the coding-agent E2E target — Streamlit+DuckDB, no CI yet) |
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

## 5. Current state (as of 2026-07-04 handoff)

**PR ledger: #6–#33 all merged & deployed; #35 open (small UI fixes, awaiting Jason's
merge).** The 2026-07-03/04 marathon session shipped #21–#35. App last deployed
`2026-07-04T01:06:03Z`, RUNNING. **167 pytest passing.** Every item below is LIVE unless
marked "(PR #35, awaiting merge)".

### 5a. What shipped THIS session (2026-07-03/04) — the big additions

- **4E Report builder** (PR #21): UC **metric view** `work_items_metrics` (YAML versioned
  in `src/app/reportbuilder.py`, app-creates it lazily via the warehouse → app SP owns it,
  so CREATE OR REPLACE works on version bumps; if another principal owns it, `_ensure`
  probes and uses it read-only). Builder UI on Reports: dims × measures × chart
  (auto/bar/line/area/table) + **filter chips** per category dimension (values queried
  from the view itself). Per-user saved reports in `saved_reports`. Endpoints
  `GET /reports/builder/meta`, `POST /reports/builder/run`, `GET/PUT/DELETE /reports/saved`.
  Batch plane (Delta) — the curated widgets stay near-live OData. Lead-time measures use a
  SQL business-days closed form (epoch-Monday) tested equal to `business_days_between`.
- **Global search** (PR #22 + PR search follow-up): the header box searches **work items**
  (almsearch service, WIQL fallback) + **pull requests** (list active+completed, filter) +
  **code** (BFF grep index `app/codesearch.py` — the org has NO Code Search extension, the
  API returns count:0/infoCode:6 silently; see AGENTS rule 11). Each plane fails
  independently. Results deep-link into the WI drawer / PR drawer / Code viewer. Index is
  TTL-cached (300s), prefers `dev` branch, skips minified/lockfiles/binaries.
- **Copilot session history** (PR #23): `ai_sessions` table (opaque `state` JSON = turns +
  proposal outcomes), autosaved (debounced) after answered turns; restore/delete.
  **UI is now a compact History (N) dropdown + New button** (PR #35 — was a chip wall).
- **Reports exports** (PR #23/#24): `.xlsx` (5 sheets, openpyxl) + `.pdf` (A4, **fpdf2 —
  pure Python, chosen over weasyprint to avoid system-lib deploy risk**) via
  `GET /reports/export?format=`. Honors active filters.
- **Copilot table artifacts** (PR #24): Genie (`query_analytics_history`) results with
  columns+rows surface as reply `tables`; a download chip POSTs to
  `POST /api/export/table` → xlsx.
- **Model eval harness** (PR #24): `scripts/eval_copilot.py` + `evals/copilot_tasks.json`
  (7 tasks). Runs the REAL agent loop through `mlflow.genai.evaluate()`, scored by
  deterministic scorers (tool choice, proposal contract, **no-silent-writes invariant**,
  step budget, latency) + **LLM judge** (per-task guidelines). One run per endpoint in
  `/Shared/ado-companion-evals`. **This is the corporate model-comparison mechanism** —
  see `evals/README.md`.
- **Coding agent** (PR #30, hardened #32/#33): copilot tools `search_code` (cross-repo grep)
  and `create_code_pr` (write PROPOSAL: full-file edits, verified repo+branch, ≤8 files/150k
  chars). Apply → `POST /api/projects/{p}/repos/{rid}/code-pr` → pushes API creates
  `copilot/<slug>-<hex>` branch off base + opens a PR (audit `code.pr`). **Never lands on a
  protected branch directly.** Also `list_repos` is a copilot read tool now. Verified live
  end-to-end (llama searched→read→proposed; Apply made real PRs, then abandoned).
- **Copilot side panel** (PR #28): the copilot moved from its own tab into a **right panel**
  (Genie/Cortex style), toggled by a header **Copilot** button, available on every tab,
  stays mounted so chat survives closing. Left nav **collapses to a 58px icon rail**
  (localStorage). The dedicated AI tab is gone; Reports moved under Insights.
- **Working timeline** (PR #33): each answer carries `steps` (interleaved model *thinking* +
  every tool call with compacted args + result preview + error flag). UI: familiar chips
  collapsed, "show working (N steps)" expands the full plot; failures in red. Makes a
  claimed-but-never-made proposal visible at a glance.
- **PR approve + merge** (PR #27, #33): `connection_data()` no longer sends `api-version`
  (connectionData is unversioned → 400 broke Approve). `list_pull_requests` now returns
  `isApproved` (from ADO reviewer votes — ANY approver, ≥1 approve + nobody waiting/
  rejecting) + `mergeStatus`. **Merge button** in the PR row/drawer appears only when
  active + ADO-approved + no conflicts → `POST .../merge` completes the PR (ADO re-enforces
  branch policies server-side; 409 on conflicts; audit `pr.merge`). **The copilot has NO
  merge tool — merge is a human click, preserving "AI writes, human ships".**
- **PR description** in the PR drawer, rendered as markdown (PR #35 — was missing).
- **Docs shipped**: blog **Part 7** (`docs/blog/part-7-search-artifacts-eval-harness.md`,
  draft), `docs/CORPORATE_BOOTSTRAP.md` (8-phase setup pre-script — corporate uses a
  ONE-TIME repo import, NOT the GitHub mirror), `docs/REPO_ONBOARDING_E2E.md` (replay-verbatim
  repo migration + coding-agent test), `evals/README.md` (model comparison runbook),
  AGENTS.md rules 11 + eval-harness + corporate-bootstrap sections.

### 5b. Baseline capabilities (shipped earlier, all live)

The app is feature-complete through Phase 4C+4F:

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
- **Tests**: **167 pytest**, ~83% line coverage (routes/copilot ~79, store 84, insights 81,
  exports 100, codesearch 89). No CI coverage gate yet. Frontend has no automated tests
  (Playwright screenshots + live smokes per PR).

**Next up (nothing is blocking; pick by priority):**
1. **Corporate rollout** — the whole point now. Follow `docs/CORPORATE_BOOTSTRAP.md`
   (8 ordered phases w/ gates). Corporate uses a ONE-TIME repo import (not the mirror).
   Then run the model comparison (`evals/README.md`): put a Claude endpoint
   (**Sonnet 5 / Opus 4.8 / Fable 5** — whatever the corporate workspace serves) on
   `copilot_endpoint` and eval Llama-vs-Claude with a pinned judge. **Model quality is
   the #1 lever for the coding agent** (see §5c).
2. **Grow the eval suite** before/with the model swap — add harder coding tasks (multi-file
   edits, ambiguous asks). The one coding task (`coding_agent_ci_pipeline`) currently
   passes 1.0 on llama ONLY because of the python-call parser (see §5c); add tasks that
   separate the models.
3. **CI-feedback loop for the coding agent** (turns "writes a patch" into "gets it green"):
   a read tool for its PR's build status + failure logs, and extending `create_code_pr` to
   push follow-up commits to its own branch. Then: propose → PR → CI red → agent reads
   traceback → pushes fix → CI green → human merges. Small, high-value.
4. **Genie Code integration** (Databricks's own coding agent, launched 2026-03; UI-only,
   NO API). Two paths documented in chat: (a) sync the ADO repo into a Databricks **Git
   folder** so Genie Code works the real code with COMPUTE (it can run tests); (b) expose
   ADO Companion as an **MCP server** so Genie Code drives our governed tools (business-day
   metrics, audit). Bridge, don't replace — our panel agent for in-flow changes, Genie Code
   for heavy dev. A `.assistant/skills/ado-companion/SKILL.md` (package AGENTS.md) would
   teach any Genie Code session this codebase.
5. Small: CI coverage gate (optional); `db.py` DuckDB→warehouse port for streamlit-chess
   (ephemeral local file breaks on Apps — ideal coding-agent demo, do it PRE-demo);
   add a validate pipeline to streamlit-chess (agent already proposed one — abandoned PR).

### 5c. The model story (critical for corporate — this is the roadshow's technical spine)

The copilot plumbing is **model-agnostic**; the endpoint is a **secret** → swapping models
needs **no redeploy**. On the dev **llama** endpoint (Free Edition; Claude endpoints
rate-limited to 0 there):
- Read/search/explain/analytics: **rock solid**.
- Work-item write proposals: reliable.
- **Code-change proposals (`create_code_pr`): fragile on llama.** It repeatedly emitted the
  call as *python-style text* with unquoted GUIDs/branch names and a nested `edits` payload
  instead of a structured tool call. Two fixes landed: (1) a **quote/depth-aware
  python-call parser** (`_lift_python_style_calls` in `copilot.py`) that lifts exactly that
  shape into a real proposal — the eval task went `proposal_contract` **0.0 → 1.0**; (2)
  malformed-JSON tool args get **precise feedback** (re-send with `\n` escaping) instead of
  a misleading missing-fields error. Jason's exact failing paste is a regression test.
- **Conclusion**: whole-file faithfulness + traceback-reading is exactly where a frontier
  Claude model separates from llama. Corporate should run the eval comparison and expect the
  code-agent quality delta to be the headline. A stronger model also earns a bigger `edits`
  budget (whole-file rewrites eat output tokens).

**Blog**: Parts 1–7 drafted in `docs/blog/`, all `draft: true`, screenshot slots
marked (1 build+CI/CD · 2 OData · 3 copilot · 4 MLflow tracing · 5 in-place AI ·
6 flow metrics/business days/Plot · 7 search/artifacts/eval harness). `WEBSITE_HANDOFF.md` = self-contained publishing
instructions for Jason's website agent (Astro + Tailwind site, minimalist B&W,
jpaladini.vercel.app, no blog section yet). Jason has the handoff files in chat too.

**Open-sourcing** remains a goal: keep AGENTS.md self-sufficient; never commit tokens;
**rotate both PATs before going public** (they appeared in session transcripts).

## 6. Architecture cheat sheet (where things live)

```
src/app/main.py            FastAPI app + pure-ASGI AuditMiddleware; _ACTIONS maps routes→
                           audit names (report.*, code.pr, pr.merge, copilot.session.*, …)
src/app/api/routes.py      all /api endpoints (BFF): search, reports/builder, reports/export,
                           export/table, copilot/sessions, code-pr, pullrequests/{id}/merge
src/app/ado/client.py      operational plane: live ADO REST. NOTE: connection_data() sends
                           NO api-version (connectionData is unversioned → 400). Has
                           push_branch_with_edits + create_pull_request (coding agent),
                           complete_pull_request (merge), search_work_items/pull_requests
src/app/ado/analytics.py   analytical plane: ADO Analytics OData ($apply); business_days_between
src/app/reportbuilder.py   4E: UC metric-view YAML (versioned here), build_query planner,
                           lazy _ensure (CREATE OR REPLACE, read-only fallback if owned elsewhere)
src/app/codesearch.py      BFF code-search grep index (TTL cache; org has no Code Search ext)
src/app/exports.py         reports_workbook (xlsx), reports_pdf (fpdf2), table_workbook
src/app/genie.py           Genie Conversation API client (space id from secret at runtime)
src/app/copilot.py         AI copilot: FMAPI tool-calling loop, propose-then-apply, write-target
                           verification, TEXT-FORM + PYTHON-STYLE call parsers (llama fallback),
                           search_code/create_code_pr coding tools, steps timeline, MLflow tracing
src/app/ai.py              single-shot AI: suggest_work_item, review_pr, explain_file
src/app/insights.py        table freshness (DESCRIBE DETAIL) + ingest run-now
src/app/store.py           Delta app-state store: settings, audit_log, ai_sessions,
                           saved_reports — parameterized SQL, graceful degradation, re-probe
src/app/identity.py        X-Forwarded-* header identity
jobs/ingest_ado_analytics.py  OData → Delta job (explicit schemas! all-NULL gotcha)
scripts/eval_copilot.py    model eval harness (mlflow.genai.evaluate + judges)
evals/copilot_tasks.json   7-task eval suite (incl. coding_agent_ci_pipeline)
frontend/src/screens/      Overview, WorkItems, PullRequests, Pipelines, Code, Copilot,
                           Reports, ReportBuilder (Copilot has panel variant; no AI tab)
frontend/src/components/   Shell (rail + right panel + search + Copilot toggle), SearchBox,
                           Drawer, AIButton, PlotFigure, CodeBlock, FreshnessBar, Toast, ui, icons
frontend/src/lib/          theme, tokens, text, highlight, markdown, plot
databricks.yml             Asset Bundle: app + secret resources + ingest job (dev/stg/prod)
azure-pipelines.yml        deploy on merge to dev/stg/prod (SP auth via pipeline variables)
azure-pipelines-validate.yml  PR validation: npm build + pytest + bundle validate (no deploy)
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
