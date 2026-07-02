# NEXT_SESSION.md — session handoff & resume guide

> **For the next Claude Code session (and for Jason).** This file captures the complete
> working state as of **2026-07-02** so a fresh session can resume in minutes. Read this,
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
| Secrets (scope `ado`) | `ado_org_url`, `ado_pat`, `ado_project`(=home), `genie_space_id` — all set |

## 4. The delivery loop (use it for every change)

**The pipeline flow, component by component (this is THE mechanism — nothing deploys any
other way):**

```
1. git push → GitHub repo jpaladini/ado, branch claude/web-first-app-planning-xsz5l0
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

## 5. Current state (as of handoff)

**Deployed & verified working in the live app:**
- Phases 0–3 complete: CRUD tabs, Overview with live OData aggregates + range control,
  Genie Analytics tab (real answers over real data), freshness stamp with exact
  last-update time + **Refresh now** button (job-permission granted, tested by Jason).
- Phase 4A (identity/settings/audit): **merged & deployed** (PRs #6, #7). Store schema +
  grants exist; tables auto-created; settings popover works.

**Merged 2026-07-02:** PR #8 (whoami store probe). Jason should still confirm the popover
says activity log **on** and a state change lands a row in
`workspace.ado_companion_app.audit_log`.

- **PR #9 (Phase 4B — work items full CRUD)** and **PR #10 (Genie empty-table fix:
  rows now fetched from statement result chunks)** — both merged & deployed 2026-07-02.

- **PR #11 (4D copilot)**, **PR #12 (copilot hardening + Genie-as-tool)**,
  **PR #13 (blog parts 3+4)** — merged & deployed 2026-07-02. Copilot secrets set,
  traces flowing to experiment 3567576457281688.

**In flight — PR #14** (branch `claude/resume-next-session-pbbmrk`) carries THREE
things (Jason's merges lagged the session, so commits stacked on the open PR):
1. **AI work-item enrichment**: "Draft with AI" (create drawer) / "Improve with AI"
   (edit drawer) via POST /api/ai/suggest-workitem (`src/app/ai.py`, ai.suggest audit).
2. **4F code browser + AI PR review**: Code tab 3-pane (branch picker, lazy tree,
   highlight.js viewer); PR detail drawer (files/diffs/threads/comments, diffs via
   stdlib difflib server-side); copilot PR tools (read: list_pr_files,
   get_pr_file_diff, list_pr_threads, get_file windowed; write proposals:
   comment_on_pr, comment_on_pr_file w/ PR-target verification). Live-smoked:
   "review the open PR" → real diff reads → file-anchored comment proposal.
3. **Blog website handoff brief** (docs/blog/WEBSITE_HANDOFF.md).

**Next up: 4C → 4E** (full detail in PLAN.md §5a):
- **4C — Reports** *(START HERE next)*: Analytics tab → report widgets w/ assignee/type/date filters (OData).
- **4D — AI tab**: move Genie chat to dedicated tab + per-user session history (store).
- **4E — Report builder**: visual OData query builder + saved reports (store).
- **4F — Code browser**: branch picker, file tree, file viewer w/ highlighting.

**Also pending / notable:**
- Model for the future FMAPI copilot (Phase 5): Jason leaning `databricks-claude-sonnet-5`
  (Databricks-served) vs `llama-4-maverick`; endpoint name will be config.
- Blog drafts live in `docs/blog/` — Parts 1 & 2 (build + OData), **Part 3 (the AI
  copilot: decisions, propose-then-apply, Genie-as-tool) and Part 4 (MLflow tracing:
  span design, the two day-one diagnoses) drafted 2026-07-02**. All `draft: true`;
  screenshot slots marked inline. Jason's site is Astro + Tailwind, minimalist B&W
  (github.com/jpaladini/jpaladini → jpaladini.vercel.app), no blog section yet.
- Open-sourcing is a stated goal: keep `AGENTS.md` self-sufficient and vendor-neutral;
  never commit tokens; rotate the PATs before going public (they appeared in a session
  transcript).

## 6. Architecture cheat sheet (where things live)

```
src/app/main.py            FastAPI app + pure-ASGI AuditMiddleware (logs mutations)
src/app/api/routes.py      all /api endpoints (BFF)
src/app/ado/client.py      operational plane: live ADO REST (httpx, PAT basic auth)
src/app/ado/analytics.py   analytical plane: ADO Analytics OData ($apply, snapshots)
src/app/genie.py           Genie Conversation API client (space id from secret at runtime)
src/app/copilot.py         AI copilot: FMAPI tool-calling agent loop, propose-then-apply,
                           MLflow turn tracing (endpoint/experiment from secrets at runtime)
src/app/insights.py        table freshness (DESCRIBE DETAIL) + ingest run-now
src/app/store.py           Delta app-state store (settings, audit) — parameterized SQL,
                           batched audit writes, graceful degradation, 120s re-probe
src/app/identity.py        X-Forwarded-* header identity
jobs/ingest_ado_analytics.py  OData → Delta job (explicit schemas! all-NULL gotcha)
frontend/src/screens/      Overview, WorkItems, PullRequests, Pipelines, Code, Analytics
frontend/src/components/   Shell (nav/topbar), UserFooter (settings popover), Toast, ui, icons
frontend/src/lib/          theme (CSS-var dark mode), tokens (chip class maps)
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
