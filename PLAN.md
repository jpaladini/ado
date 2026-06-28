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
- **Phase 1 — Read parity**: work items board, PR list, pipeline runs, commits (matches the mobile app).
- **Phase 2 — Write / CRUD (in MVP)**: create/edit work items, comment, approve/abandon PRs,
  queue/cancel runs. Every write goes through the FastAPI BFF with optimistic UI + rollback.
- **Phase 3 — Analytics**: OData→Delta ingest job; Genie Space; DORA dashboards
  (lead time, deploy frequency, change-fail rate, MTTR) + NL-Q&A panel via Conversation API.
- **Phase 4 — Surfaces (optional)**: Teams tab embedding the app; Tauri Mac wrapper.

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
