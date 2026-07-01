# Genie setup — natural-language analytics

The **Analytics** tab answers plain-language questions about your Azure DevOps data via
**Databricks Genie**. Genie answers over **Delta tables in Unity Catalog**, so setup is:
ingest the data → create a Genie Space over it → tell the app the Space ID.

The app degrades gracefully until this is done — the Analytics tab shows setup guidance
and everything else works normally.

## 1. Run the ingestion job (once, then unpause the schedule)

The bundle deploys a job, **`ado-analytics-ingest`**, that reads the same ADO Analytics
OData feed the dashboard uses and lands two tables:

| Table | Contents |
|---|---|
| `main.ado_analytics.work_items` | Current work items (id, title, type, state, category, assignee, dates) |
| `main.ado_analytics.work_item_daily` | Daily counts by state for the last 90 days (trend history) |

- Set the **project**: edit the job task's `--project` parameter (Workflows → the job →
  task parameters), or create an `ado/ado_project` secret with the project name.
- **Run it once** manually (Workflows → `ado-analytics-ingest` → Run now) and confirm the
  two tables exist.
- **Unpause the schedule** (it deploys `PAUSED`; it runs daily 05:00 UTC once enabled).
- The principal running the job needs **READ on the `ado` secret scope**.

## 2. Create the Genie Space (human step — UI only)

1. In the workspace: **Genie → New → Genie Space** (requires a SQL warehouse; 2X-Small is fine).
2. Add the two tables above.
3. Optional but recommended — paste instructions like:
   *"work_items holds current Azure DevOps work items; state_category is one of
   Proposed/InProgress/Resolved/Completed/Removed. work_item_daily holds daily counts per
   state — use it for trends over time."*
4. Ask it a test question in the Genie UI (e.g. "how many open items by state?").
5. Copy the **Space ID** from the URL: `…/genie/rooms/<SPACE-ID>` — that token is the ID.

## 3. Give the app access + the Space ID

```bash
# the app reads this at runtime — no redeploy needed
databricks secrets put-secret ado genie_space_id --string-value "<SPACE-ID>"
```

Then grant the **app's service principal** access to the Space (share the Genie Space with
it — at least *Can Run*) and to the SQL warehouse it uses. Without this, /api/genie/ask
returns a permission error from Databricks.

## 4. Verify

- `GET <app-url>/api/health` → `"genie_configured": true`
- Open the **Analytics** tab → ask "How many open work items are there by state?"

## How it works

```
Analytics tab → POST /api/genie/ask → Genie Conversation API (space id from
ado/genie_space_id) → SQL over main.ado_analytics.* → text + table back to the UI
```

- Conversations continue: follow-up questions pass the `conversationId` back.
- The Space ID lookup is cached after first success; the secret is read with the app's
  existing scope-level READ on `ado`.
- Free Edition note: Genie is best-effort (~5 questions/min) — fine for dev.
