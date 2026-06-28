# CI/CD — branch-based promotion to dev / stg / prod

Each protected branch deploys to its own Databricks workspace via a Databricks Asset
Bundle target. Config is per-workspace secrets, so the **code is identical across
branches** — PR promotion carries no environment diffs.

```
 branch: dev  ──merge──▶  azure-pipelines.yml  ──▶  bundle deploy -t dev   ──▶  dev workspace
 branch: stg  ──merge──▶  azure-pipelines.yml  ──▶  bundle deploy -t stg   ──▶  stg workspace
 branch: prod ──merge──▶  azure-pipelines.yml  ──▶  bundle deploy -t prod  ──▶  prod workspace
```

Promotion path: open a PR `dev → stg`, then `stg → prod`. Each merge triggers a deploy to
that environment. Direct pushes are blocked by branch policy; merges go through PRs.

## Pipelines in this repo

| File | Purpose | Trigger |
|---|---|---|
| `azure-pipelines.yml` | Build frontend → `bundle deploy` + `run` to the branch's workspace | Push/merge to `dev`/`stg`/`prod` |
| `azure-pipelines-validate.yml` | Frontend build + backend `pytest` + `bundle validate` (no deploy) | Branch policy (build validation) on PRs |

## One-time setup (per environment)

### 1. Service principal per workspace
In each workspace (dev/stg/prod), create a **service principal** and an **OAuth secret**
(client ID + client secret). Grant it:
- permission to deploy/manage the app (`ado-companion`), and
- `CAN_MANAGE`/deploy rights for the bundle resources.

The app's runtime secrets (`ado/ado_org_url`, `ado/ado_pat`) are created **once per
workspace** by a human (via `scripts/setup.sh` or `databricks secrets put-secret`) — the
pipeline does **not** manage them, so the PAT never touches CI.

### 2. Variable groups in Azure DevOps
Create three variable groups (Pipelines → Library): `databricks-dev`, `databricks-stg`,
`databricks-prod`. Each contains:

| Variable | Notes |
|---|---|
| `DATABRICKS_HOST` | Workspace URL, e.g. `https://<ws>.cloud.databricks.com` |
| `DATABRICKS_CLIENT_ID` | Service principal application ID |
| `DATABRICKS_CLIENT_SECRET` | OAuth secret — mark as **secret** |

The deploy pipeline auto-selects the group matching the branch.

### 3. Register the pipelines
- Create a pipeline from `azure-pipelines.yml` (the deploy pipeline).
- Create a pipeline from `azure-pipelines-validate.yml`, then add it as a **Build
  Validation** policy on the `dev`, `stg`, and `prod` branches (Repos → Branches →
  Branch policies). This enforces tests + build + validate before merge.

## Notes
- The committed `src/static/` is a convenience for manual/agent deploys; CI rebuilds it
  fresh each run, so prod always ships a clean build.
- `dev` uses bundle `mode: development` (resources name-prefixed per principal); `stg`/`prod`
  use `mode: production` (clean names). See `databricks.yml`.
- Manual/agent deploys (`scripts/setup.sh`, `AGENTS.md`) remain valid for **dev/bootstrap**;
  stg/prod should flow through PR + pipeline only.
