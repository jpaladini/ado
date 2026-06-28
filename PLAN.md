# ADO — Web-First Azure DevOps Companion

> Planning document. Status: **draft for review.** Defaults below are recommendations, not commitments — flag anything to change.

## 1. What we're building

A **web-first Azure DevOps companion** inspired by the unofficial mobile client
[PurpleSoftSrl/azure_devops_app](https://github.com/PurpleSoftSrl/azure_devops_app)
(Flutter; auth via Microsoft account or PAT; work items, pull requests, pipelines, commits).

We reimagine it for the browser and go beyond the original in two ways:

1. **CRUD workflow** — not just viewing ADO data, but creating/editing work items,
   commenting, approving/abandoning PRs, queuing pipeline runs.
2. **Analytics** — a dashboard surface (DORA-style delivery metrics) plus
   **natural-language Q&A via Databricks Genie**, which the mobile app never had.

One-line pitch: *Manage your Azure DevOps work and understand your delivery — from one web app.*

## 2. The core architectural decision: two data planes

ADO functionality splits into two planes. Keeping them separate is the central design choice.

| Plane | Source | Nature | Powers |
|---|---|---|---|
| **Operational** | Azure DevOps REST API (live) | Low-latency, read **+ write** | Work items, PRs, pipelines, commits — the CRUD tool |
| **Analytical** | ADO data ingested into a lakehouse/warehouse | Batch, read-only, aggregate | Dashboards + Genie natural-language Q&A |

- The **operational plane** talks directly to the live ADO REST API. No copy of ADO
  data is stored; we only persist app-specific state (saved views, favorites, prefs).
- The **analytical plane** requires ADO history in a queryable store. Genie answers
  only over **Databricks Unity Catalog**, so this means ingesting ADO's
  [Analytics OData feed](https://learn.microsoft.com/en-us/azure/devops/report/)
  into Delta tables, then pointing a Genie Space at them.

### Analytics is pluggable (the Databricks fork)

| Path | When | How |
|---|---|---|
| **Databricks Genie** (default) | On Databricks, or willing to add it | OData → Delta → Genie Space; embed via iframe (GA 2026) or Conversation API |
| **Non-Databricks fallback** | Not on Databricks | Mirror ADO data → Postgres; NL→SQL with the Claude API; charts in-app |

We build the analytics surface behind an interface so the backing engine can swap
without touching the UI. **Decision still open — confirm Databricks availability.**

## 3. Recommended stack (web-first, single codebase)

- **App**: Next.js 15 (App Router) + TypeScript + Tailwind + shadcn/ui; TanStack Query.
- **Auth**: **Microsoft Entra ID** (OAuth/OIDC) via Auth.js, with **PAT fallback**
  (parity with the original). Entra is the natural fit and unlocks Teams/M365 SSO later.
- **Backend**: Next.js Route Handlers as a BFF proxying the ADO REST API — keeps tokens
  server-side, centralizes pagination/rate-limit handling.
- **App-state DB**: small Postgres (Neon/Supabase) for saved views, favorites, prefs.
  *Not* a mirror of ADO data.
- **Analytics**: Databricks (Genie Space + embedded dashboards) or the Postgres/Claude
  fallback, behind a common interface.
- **Deploy**: Vercel.

## 4. Cross-platform: build once, shell everywhere

The web app is the single source of truth; other surfaces wrap or embed it.

1. **Web on Vercel** — primary. ✅
2. **Microsoft Teams tab / M365 app** — strongest bonus. Same codebase, Entra SSO,
   and DevOps teams already live in Teams. Highest value-to-effort.
3. **Mac app via Tauri** — cheap wrapper; menu-bar/offline niceties. Low effort.
4. **Databricks App (React)** — Databricks Apps host Node/React natively; if data is in
   Databricks this becomes the natural analytics host (Genie + Unity Catalog auth built in).

## 5. Phased build

- **Phase 0 — Foundation**: Next.js scaffold, Entra + PAT auth, ADO API client, org/project picker.
- **Phase 1 — Read parity**: work items board, PR list, pipeline runs, commits (matches the mobile app).
- **Phase 2 — Write / CRUD**: create/edit work items, comment, approve/abandon PRs, queue/cancel runs.
- **Phase 3 — Analytics**: DORA dashboards (lead time, deploy frequency, change-fail rate, MTTR) + embedded Genie.
- **Phase 4 — Surfaces**: Teams tab, then Tauri Mac. (Databricks App if applicable.)

## 6. Open decisions

1. **Databricks availability** — drives the entire analytics path (Genie vs Postgres/Claude). *Default: design pluggable, lead with Genie.*
2. **Write-back scope for MVP** — read-only / core write-back / full CRUD+automation. *Default: read parity (P1) then core write-back (P2).*
3. **Bonus surfaces to plan in vs. defer** — *Default: plan Teams/M365 in; note Mac + Databricks App as follow-ons.*
4. **Stack confirmation** — Next.js/React assumed. Push back if you prefer otherwise.

## 7. References

- Reference app: https://github.com/PurpleSoftSrl/azure_devops_app
- [Genie Conversation API](https://docs.databricks.com/aws/en/genie/conversation-api)
- [Embed a Genie Space in an external app](https://docs.databricks.com/aws/en/genie/embed)
- [Databricks Apps](https://docs.databricks.com/aws/en/dev-tools/databricks-apps/)
- [Azure DevOps REST API](https://learn.microsoft.com/en-us/rest/api/azure/devops/)
- [Azure DevOps Analytics (OData)](https://learn.microsoft.com/en-us/azure/devops/report/)
