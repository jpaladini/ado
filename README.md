# ADO — Azure DevOps Companion (on Databricks Apps)

A web Azure DevOps companion — work items, PRs, pipelines + Genie analytics — hosted as a
**Databricks App**. React (Vite) SPA + FastAPI (Python) backend in one process.

See [`PLAN.md`](PLAN.md) for the full architecture and roadmap.

**Implemented (Phases 0–1):** project picker + a tabbed project view with **Work Items**,
**Pull Requests** (status filter), **Pipelines** (recent runs), and **Code** (repos + commits) —
all read live from the Azure DevOps REST API via the FastAPI BFF, served inside a Databricks App.

```
ado/
├─ databricks.yml        # Asset Bundle: dev (Free Edition) / prod (corporate) targets
├─ src/                  # the Databricks App (deployed)
│  ├─ app.yaml           # app entrypoint + env/secrets
│  ├─ serve.py           # binds DATABRICKS_APP_PORT
│  ├─ requirements.txt
│  ├─ app/
│  │  ├─ main.py         # FastAPI: API + serves the built SPA
│  │  ├─ config.py       # settings from env/secrets
│  │  ├─ ado/client.py   # Azure DevOps REST client (httpx)
│  │  └─ api/routes.py   # /api/health, /api/me, /api/projects
│  └─ static/            # React build output lands here
└─ frontend/             # React (Vite + TS + Tailwind)
```

## Prerequisites

- Python 3.11+, Node 20+
- A Databricks **Free Edition** workspace + the [Databricks CLI](https://docs.databricks.com/aws/en/dev-tools/cli/)
- An Azure DevOps **Personal Access Token** (scopes: Work Items, Code, Build — read/write)

## Run locally

**1. Backend**
```bash
cd src
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
export ADO_ORG_URL="https://dev.azure.com/your-org"
export ADO_PAT="your-pat"
python serve.py            # http://localhost:8000
```

**2. Frontend (separate terminal)**
```bash
cd frontend
npm install
npm run dev                # http://localhost:5173 (proxies /api -> :8000)
```

Open http://localhost:5173 — pick a project and browse its work items, PRs, pipelines, and code.

**Run backend tests:**
```bash
cd src && pip install -r requirements-dev.txt && pytest
```

## Deploy to Databricks

The full runbook is in **[`SETUP_DATABRICKS.md`](SETUP_DATABRICKS.md)** — automated and manual paths.
Pointing an **AI coding agent** (e.g. Genie Code) at the repo? It should follow
**[`AGENTS.md`](AGENTS.md)** — a deterministic, idempotent runbook. The built frontend is
committed under `src/static/`, so deploying needs **no Node**.

**Fast path** (from the repo root):
```bash
DBX_HOST=https://<workspace>.cloud.databricks.com \
ADO_ORG_URL=https://dev.azure.com/<org> \
ADO_PAT=<token> \
./scripts/setup.sh
```
This logs in, stores the PAT secret, sets the org URL, builds the frontend, deploys, and starts
the app — then prints its URL. Re-runnable and idempotent.

> **Free Edition notes:** apps stop ~24h after each deploy (just redeploy — fine for solo dev),
> and it's **non-commercial only**. Move to the corporate workspace for real use. See `PLAN.md` §7.
