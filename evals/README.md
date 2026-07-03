# Copilot model comparison — runbook (corporate-ready)

> **Audience:** whoever runs the Llama-vs-Claude comparison in the corporate
> workspace — an AI agent session, or Jason pasting notebook cells. It is
> self-contained: no context from prior sessions needed. (Note: Databricks
> *Genie* is NL-to-SQL over tables and cannot run this; use an agent session
> or a notebook.)

## What this does

`scripts/eval_copilot.py` answers *"which serving endpoint should
`ado/copilot_endpoint` point at?"* with data:

- The **same task suite** (`evals/copilot_tasks.json`) runs through the **real
  agent loop** (`src/app/copilot.py`) — live ADO read tools execute; write
  tools become proposals by design, so **nothing in ADO is ever mutated**.
- Each answer is scored by:
  - **Deterministic scorers** (no LLM opinion): called the expected tool ·
    write asks became the right proposal with the right args · hallucinated
    targets (work item 999999) were rejected, not proposed · **no write tool
    ever executed** (the propose-then-apply invariant) · stayed within the
    step budget · latency (mean / p90).
  - **LLM judge** (`ExpectationsGuidelines`): per-task rubric strings in the
    suite (e.g. "durations must be in business days", "must say historical
    data is batch, not real-time"), scored by a judge model you pin.
- Results land as **one `mlflow.genai.evaluate()` run per endpoint** in the
  MLflow experiment `/Shared/ado-companion-evals` — compare runs side by side
  in the experiment's **Evaluation** view; every row links its full trace.

## The rules (do not skip)

1. **Pin ONE judge model for all runs you intend to compare.** Scores from
   different judges are not comparable, and a model judging itself inflates
   scores. Use the strongest available endpoint as judge (in corporate:
   Claude Sonnet), even when it is also a contestant — same judge for both
   runs keeps the bias symmetric.
2. **Run both endpoints within the same hour** against the same project so
   live ADO state is comparable.
3. **Deterministic scorers are a hard gate**: an endpoint that scores < 1.0 on
   `proposal_contract` or `no_silent_writes` is disqualified regardless of how
   good its prose is. Judge scores and latency break ties among endpoints that
   pass the gate.

## Option A — CLI (any machine with repo + network)

```bash
pip install -r src/requirements.txt pandas   # pandas: eval-only extra dep
export ADO_ORG_URL="https://dev.azure.com/<org>"
export ADO_PAT="<pat: Work Items R/W, Code R/W, Build R+E>"
export DATABRICKS_HOST="https://<workspace-host>"
export DATABRICKS_TOKEN="<pat or oauth token>"

# contestant 1
python scripts/eval_copilot.py \
  --endpoint <llama-endpoint-name> \
  --judge-model databricks:/<claude-sonnet-endpoint-name>

# contestant 2
python scripts/eval_copilot.py \
  --endpoint <claude-sonnet-endpoint-name> \
  --judge-model databricks:/<claude-sonnet-endpoint-name>
```

Useful flags: `--only task1,task2` (subset), `--tasks <path>` (alternate
suite), `--experiment <path>` (default `/Shared/ado-companion-evals`).
Endpoint names: workspace UI → Serving, or
`GET /api/2.0/serving-endpoints`.

## Option B — Databricks notebook (corporate-friendly)

Paste as cells; the repo must be available in the workspace (Databricks Repos
sync of the ADO repo works — corporate mirrors `dev` there already).

```python
# Cell 1 — deps (mlflow 3.x needed for mlflow.genai)
%pip install pandas "mlflow-skinny>=3.0" httpx pydantic-settings
dbutils.library.restartPython()
```

```python
# Cell 2 — env from the app's existing secret scope (never hardcode tokens)
import os
os.environ["ADO_ORG_URL"] = dbutils.secrets.get("ado", "ado_org_url").strip()
os.environ["ADO_PAT"] = dbutils.secrets.get("ado", "ado_pat").strip()
# in-workspace notebooks authenticate to MLflow/serving automatically;
# DATABRICKS_HOST/TOKEN env vars are only needed off-workspace
```

```python
# Cell 3 — run one contestant (repeat with the other endpoint, SAME judge)
import subprocess, sys
REPO = "/Workspace/Repos/<user-or-folder>/ado"   # adjust to the Repos path
r = subprocess.run(
    [sys.executable, f"{REPO}/scripts/eval_copilot.py",
     "--endpoint", "<llama-endpoint-name>",
     "--judge-model", "databricks:/<claude-sonnet-endpoint-name>"],
    capture_output=True, text=True, cwd=REPO,
)
print(r.stdout[-3000:], r.stderr[-2000:])
```

## Reading the results

1. Open the experiment `/Shared/ado-companion-evals` → **Evaluation runs**
   (each script invocation printed its direct URL).
2. Select both runs → compare per-scorer means:
   `called_expected_tool`, `proposal_contract`, `no_silent_writes`,
   `step_efficiency` → **must be 1.0** (hard gate);
   `judge_guidelines/mean` and `latency_seconds/mean|p90` → tiebreakers.
3. Click any row to see that task's answer, scorer rationales, and the full
   agent trace (every LLM call and tool execution).

## Acting on the verdict

Swapping models is a **secret change, no redeploy** (a HUMAN action — agents
are classifier-blocked from secret writes):

```python
# notebook cell, HUMAN runs it
from databricks.sdk import WorkspaceClient
WorkspaceClient().secrets.put_secret("ado", "copilot_endpoint",
                                     string_value="<winning-endpoint-name>")
```

The app reads the endpoint at runtime; the next copilot turn uses the new
model. Re-run the eval after any model/prompt/tool change — the runs
accumulate in the experiment as a regression history.

## Growing the suite

Both contestants scoring 1.0 everywhere means the suite is too easy, not that
the models are equal. Add tasks to `evals/copilot_tasks.json` that separate
them: multi-step PR review with anchored comments, ambiguous asks that need a
clarifying answer instead of a guess, prompts that tempt fabricated ids.
Keep `expectations` **value-agnostic** (assert tools/contracts/rubrics, never
row counts that drift with live data). Baseline for reference: dev workspace
2026-07-03, `databricks-llama-4-maverick` self-judged — all scorers 1.0,
latency mean ~7s, p90 ~12s.
