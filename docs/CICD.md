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
The pipeline authenticates as a **service principal** (non-human identity) using OAuth
machine-to-machine. You need its **client ID** (= Application ID) and a **client secret**.

**Create it + find the client ID (Databricks UI):**
1. **Settings → Identity and access → Service principals → Add service principal**
   (e.g. name it `ado-deployer`). Do this in each workspace (dev/stg/prod), or create one
   account-level SP and grant it to each workspace.
2. Open the service principal — the **Application ID** shown is your `DATABRICKS_CLIENT_ID`
   (a UUID like `12345678-90ab-cdef-1234-567890abcdef`).
3. On the same page → **OAuth secrets → Generate secret**. Copy the **Secret**
   (`DATABRICKS_CLIENT_SECRET`) — it is shown **once**. (Set an expiry and rotate before it lapses.)
4. Grant the SP rights to deploy: **CAN_MANAGE** on the app `ado-companion` (and on the
   target catalog/schema/secret scope it touches). Also add it to the workspace if it's
   an account-level SP.

**Find the client ID later (CLI):**
```bash
databricks service-principals list   # the applicationId column is the client ID
```

> **Note:** OAuth M2M service principals are a **paid-workspace** capability. On personal
> **Free Edition** you may not be able to generate SP secrets — that's fine, because dev is
> bootstrapped with your own `databricks auth login` (no client ID). Client IDs are for the
> corporate stg/prod CI.

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

### 2b. (Free Edition / no service principal) — PAT auth alternative
If a workspace can't issue an SP OAuth secret (e.g. Free Edition), authenticate the
pipeline with a **personal access token** instead. The Databricks CLI uses PAT auth when
`DATABRICKS_TOKEN` + `DATABRICKS_HOST` are set.

- In the variable group, replace `DATABRICKS_CLIENT_ID` / `DATABRICKS_CLIENT_SECRET` with a
  single secret variable **`DATABRICKS_TOKEN`** (a Databricks PAT from
  *Settings → Developer → Access tokens*). Keep `DATABRICKS_HOST`.
- In `azure-pipelines.yml`, change the deploy step's `env:` block to:
  ```yaml
      env:
        DATABRICKS_HOST: $(DATABRICKS_HOST)
        DATABRICKS_TOKEN: $(DATABRICKS_TOKEN)
  ```
This is fine for personal/dev CI; prefer the service principal for corporate stg/prod
(no human-owned token, revocable, least-privilege).

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
