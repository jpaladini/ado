# ADO — Azure DevOps Companion (on Databricks Apps)

A web Azure DevOps companion — work items, PRs, pipelines + Genie analytics — hosted as a
**Databricks App**. React (Vite) SPA + FastAPI (Python) backend in one process.

See [`PLAN.md`](PLAN.md) for the full architecture and roadmap. This is the **Phase 0**
skeleton: org/project picker proving the spine **React → FastAPI → Azure DevOps REST API**,
running inside a Databricks App.

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

Open http://localhost:5173 — you should see your ADO projects.

## Deploy to Databricks (Free Edition)

**1. Configure the bundle.** In `databricks.yml`, set the `dev` workspace `host` and the
`ado_org_url` variable. In `src/app.yaml`, set `ADO_ORG_URL`.

**2. Store the PAT as a secret:**
```bash
databricks secrets create-scope ado
databricks secrets put-secret ado ado_pat      # paste the PAT
```

**3. Build the frontend** (output goes to `src/static/`):
```bash
cd frontend && npm install && npm run build && cd ..
```

**4. Deploy + run:**
```bash
databricks bundle deploy -t dev
databricks bundle run ado_app -t dev
```

> **Free Edition notes:** apps stop ~24h after each deploy (redeploy to resume — fine for
> solo dev), and it's **non-commercial only**. Move to the corporate workspace (`-t prod`)
> for any real use. See `PLAN.md` §7.

## Migrating to corporate

Set the `prod` target's `host` in `databricks.yml`, create the `ado` secret + `ADO_ORG_URL`
in that workspace, then `databricks bundle deploy -t prod`. No code changes.
