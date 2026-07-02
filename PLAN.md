# ADO — Azure DevOps Companion on Databricks Apps

> Planning document. Architecture **locked** for the core stack; scope items in §6 still open.

## 1. What we're building

A **web Azure DevOps companion**, inspired by the unofficial mobile client
[PurpleSoftSrl/azure_devops_app](https://github.com/PurpleSoftSrl/azure_devops_app)
(Flutter; auth via Microsoft account or PAT; work items, PRs, pipelines, commits).

We reimagine it for the browser and go beyond the original:

1. **CRUD workflow** — not just viewing ADO data, but creating/editing work items,
   commenting, approving/abandoning PRs, queuing pipeline runs.
2. **Analytics** — DORA-style delivery dashboards plus **natural-language Q&A via
   Databricks Genie**, which the mobile app never had.

Hosting is **Databricks Apps** (a hard constraint — corporate allows Databricks only,
no Vercel/external PaaS). Dev runs on a personal **Free Edition** workspace; production
will run on the **corporate** workspace and repo.

## 2. The core architectural decision: two data planes

ADO functionality splits into two planes. Both are served by the **one FastAPI backend**
running inside the Databricks App. Keeping them separate is the central design choice.

| Plane | Source | Nature | Powers |
|---|---|---|---|
| **Operational** | Azure DevOps REST API (live, via `httpx`) | Low-latency, read **+ write** | Work items, PRs, pipelines, commits — the CRUD tool |
| **Analytical** | ADO data ingested to Delta in Unity Catalog | Batch, read-only, aggregate | Dashboards + Genie natural-language Q&A |

- The **operational plane** calls the live ADO REST API. No copy of ADO data is stored;
  we persist only app state (saved views, favorites, prefs).
- The **analytical plane** runs over ADO history in Delta. A scheduled Databricks **job**
  pulls the ADO [Analytics OData feed](https://learn.microsoft.com/en-us/azure/devops/report/)
  into Delta tables; a **Genie Space** points at them; the backend calls the
  [Genie Conversation API](https://docs.databricks.com/aws/en/genie/conversation-api)
  (not the iframe — that needs every viewer to hold Databricks access and can't be styled)
  and renders results in our own UI.

**Resilience:** the operational plane never depends on Databricks SQL/Genie, so the app
stays fully usable when the warehouse is quota-capped, asleep, or being migrated.

## 3. Stack (locked)

```
Databricks App
├─ React (Vite + TypeScript + Tailwind + shadcn/ui)   ← the UI
│    └─ TanStack Query → calls our FastAPI
└─ FastAPI (Python + Databricks SDK)                   ← one backend, two planes
   ├─ Operational → Azure DevOps REST API (httpx)      ← live CRUD
   └─ Analytical  → SQL warehouse + Genie Conversation API
+ Databricks Job: ADO OData → Delta (scheduled ingest)
+ Databricks Asset Bundle: dev (Free Edition) / prod (corporate) targets
```

- **Frontend**: React (Vite) SPA — chosen over Streamlit for CRUD polish; over Next.js
  because SSR/edge buys nothing inside a Databricks App.
- **Backend**: FastAPI (Python) — first-class Databricks SDK integration for Genie + SQL +
  Unity Catalog, and the BFF to the ADO REST API in one process.
- **Auth**: Databricks App provides the signed-in Databricks identity. ADO is authenticated
  separately — **PAT in a Databricks secret** for solo dev, **Entra ID OAuth** for corporate
  (ADO and Databricks likely share the tenant). PAT fallback mirrors the original app.
- **App state**: **Lakebase** (Databricks managed Postgres) on corporate; for Free Edition
  dev, start with a Delta table or minimal state (Lakebase availability there is TBD).
- **Deploy/config**: **Databricks Asset Bundles** — nothing hardcoded; workspace URL,
  warehouse/Genie Space IDs, and tokens come from target config + secrets.

## 4. Migration: personal/Free → corporate

This is designed in from day one, not bolted on later.

- **Asset Bundle targets** (`databricks.yml`): `dev` → personal Free Edition,
  `prod` → corporate. Move repos by changing the target, not the code.
- **Zero hardcoding**: all workspace/warehouse/Genie/token values via target config + secrets.
- **Native CI/CD**: `databricks bundle deploy -t {dev|prod}` is the standard corporate path,
  so it passes review.

## 5. Phased build

**Write-back is in the MVP** — it's the core "workflow tool" value, not a fast-follow.
The MVP = Phases 0–2.

- **Phase 0 — Foundation**: Databricks App skeleton (React+FastAPI) deployable via Asset
  Bundle to Free Edition; ADO auth (PAT secret); ADO API client; org/project picker.
- **Phase 1 — Read parity** ✅: work items board, PR list (status filter), pipeline runs,
  repos + commits — tabbed per project. Backend parsing covered by tests.
- **Phase 2 — Write / CRUD (in MVP)** 🔨: work item state change + comments, PR
  approve/abandon/reactivate — done, via the FastAPI BFF with query invalidation and
  per-row error surfacing. Remaining: create work items, queue/cancel pipeline runs.
- **Phase 3 — Analytics** ✅: live OData aggregates power the Overview; OData→Delta
  ingest job (daily 05:00 UTC + on-demand refresh with freshness stamp); Genie Space
  (API-created) + NL-Q&A tab via the Conversation API — proven end-to-end in the dev
  workspace 2026-07-01.
- **Phase 4 — Product depth** 🔨 (current; see §5a): identity + app-state store + audit,
  full work-item CRUD, Reports tab with filters, dedicated AI tab with session history,
  report builder, code browser.
- **Phase 5 — Surfaces (optional)**: Teams tab embedding the app; Tauri Mac wrapper.
  Also: DORA metrics; hybrid FMAPI copilot (live + historical answers; endpoint name is
  config — Databricks-served models only).

## 5a. Phase 4 — Product depth (the plan)

Two shared foundations first, then five feature tracks, each landing as its own PR
through the trunk (GitHub → mirror → ADO PR → pipeline).

**4A — Identity, settings, audit (foundation).**
- Read the Databricks Apps forwarded-identity headers (`X-Forwarded-Email` /
  `X-Forwarded-Preferred-Username`) in the BFF → `GET /api/whoami`. Verify header names
  on first deploy; fall back to the ADO connection identity if absent.
- App-state store: Delta schema `workspace.ado_companion_app` (settings, audit_log,
  ai_sessions), written by the app SP via the existing warehouse, behind a small store
  interface (swap to Lakebase later without touching callers). Async/buffered writes;
  audit middleware logs every mutating BFF call (who, what, target, when, outcome).
- UI: user chip (bottom-right of the shell footer) with a settings popover (theme,
  default project, default date range); settings persist per user.
- Human steps: grants for the app SP to CREATE/WRITE the new schema (documented in
  AGENTS.md when built).

**4B — Work items: full input + edit.**
- Create: "+ New item" opens a panel — type, title, description (markdown), assignee
  (picker fed by ADO identities), state, tags, iteration/area. POST via existing
  JSON-Patch create endpoint (`POST /{project}/_apis/wit/workitems/${type}`).
- Edit: row click opens a detail drawer — edit title/description/assignee/state/tags,
  view comment history (`GET .../comments`), add comments; all JSON-Patch updates.
- Backend additions: create_work_item, update_work_item fields beyond state, identity
  search (assignee picker), comments list, area/iteration paths.

**4C — Analytics tab → Reports.**
- The Genie chat moves out (→ 4D). Analytics becomes report widgets: state distribution,
  created vs completed, throughput/week, cycle time, per-assignee workload — each driven
  by OData `$apply` with shared **filters: assignee(s), work-item type, date range**
  (the existing 24h/7d/30d control generalizes to a date-range picker).
- Backend: extend the analytics client with parameterized filters (AssignedTo/UserName,
  WorkItemType, DateValue/CreatedDate windows).

**4D — AI Copilot (re-scoped 2026-07-02; v1 shipped).** Not a Genie chat relocation —
a **tool-calling agent** over an FMAPI serving endpoint (name is config) acting on the
live operational plane:
- Read tools execute immediately (work items, PRs, builds, identities, analytics
  summary) through the same ADO client as the REST routes.
- Write tools are **propose-then-apply**: the agent's create/update/comment calls come
  back as proposal cards; Apply executes through the normal REST routes (identical
  audit + permissions). Auto-apply may later become a per-user setting.
- **MLflow Tracing** records every turn (question → model calls → tool runs →
  proposals) to a workspace experiment. Runbook + design contract: AGENTS.md
  "AI Copilot activation".
- Later cuts: per-user session history in the app-state store; PR-review tools (needs
  4F's file/diff endpoints); artifact generation (PDF/Excel downloads); gated
  table-edit tools. Genie stays on the Analytics tab for historical questions and may
  later become one copilot tool among many.

**4E — Report builder.**
- Visual query builder over the OData analytics surface: entity (work items /
  snapshots), filters, group-bys, aggregate, chart type (table/bar/line/donut).
  Generates the `$apply` behind the scenes; "run" renders the widget; "save" stores the
  report definition per user (app-state store); saved reports render on the Reports tab.
- Explicitly *not* raw WIQL v1 — the OData aggregate surface covers reporting better.

**4F — Code browser.**
- The Code tab gains actual code: branch picker, repo file tree
  (`GET .../items?recursionLevel=...`), file viewer with syntax highlighting
  (lightweight highlighter, lazy-loaded), and blob download. Commits list remains.

**Order: 4A → 4B → 4C → 4D → 4E → 4F** (foundation first; daily-use value next;
the builder and code browser are the deepest cuts).

## 6. Open decisions

1. ~~Databricks availability~~ **Resolved**: Databricks-only host. Genie via Conversation API.
2. ~~Stack~~ **Resolved**: React (Vite) + FastAPI (Python) on Databricks Apps.
3. ~~MVP write-back scope~~ **Resolved**: core write-back is **in the MVP** (P0–P2).
   Full automation/bulk edits remain post-MVP.
4. **Bonus surfaces** — *Default: note Teams/M365 + Mac as optional P4; web (the Databricks
   App) is the product.*

## 7. Databricks Free Edition constraints (dev only)

Free Edition is great for prototyping; it is **not** a production backend.

| Capability | Free Edition limit | Consequence |
|---|---|---|
| Databricks Apps | ≤3, each stops 24h after start/redeploy | Solo-dev restart annoyance only; corporate (paid) runs continuously |
| SQL warehouse (Genie needs one) | One, 2X-Small only | Enough for personal/dev Genie |
| Genie Conversation API | Best-effort, ~5 questions/min | Fine for dev, not production throughput |
| Usage quota | Exceed → compute off rest of day/month | Analytics must degrade gracefully |
| Commercial use | **Non-commercial only** | Must move to corporate workspace before any real/corporate use |
| Other | One workspace/metastore, no SLA, deleted after prolonged inactivity | Treat as disposable dev infra |

## 8. Risks to verify early

- **Network egress**: the app calls `dev.azure.com` from inside Databricks. Free Edition
  serverless should allow it; **corporate** Databricks often restricts outbound — confirm
  the corporate workspace can reach the ADO org (the whole operational plane depends on it).
- **ADO flavor**: Azure DevOps Services (cloud) vs Server (on-prem) changes API base URLs/auth.
- **Lakebase on Free Edition**: TBD; have a Delta/minimal-state fallback for dev.
- **Commercial-use license** (see §7): do not let real corporate use run on Free Edition.

## 9. References

- Reference app: https://github.com/PurpleSoftSrl/azure_devops_app
- [Genie Conversation API](https://docs.databricks.com/aws/en/genie/conversation-api)
- [Add a Genie Space resource to a Databricks app](https://docs.databricks.com/aws/en/dev-tools/databricks-apps/genie)
- [Databricks Apps](https://docs.databricks.com/aws/en/dev-tools/databricks-apps/)
- [Databricks Asset Bundles](https://docs.databricks.com/aws/en/dev-tools/bundles/)
- [Databricks Free Edition limitations](https://docs.databricks.com/aws/en/getting-started/free-edition-limitations)
- [Azure DevOps REST API](https://learn.microsoft.com/en-us/rest/api/azure/devops/)
- [Azure DevOps Analytics (OData)](https://learn.microsoft.com/en-us/azure/devops/report/)
