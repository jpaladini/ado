"""Copilot model eval: one MLflow evaluation run per serving endpoint.

Answers "should copilot_endpoint be Llama or Claude?" with data instead of vibes:
the SAME task suite runs through the REAL agent loop (live read tools, writes
stay proposals — nothing mutates ADO), scored by deterministic checks plus
MLflow LLM judges, and logged as one mlflow.genai.evaluate() run per endpoint.
Compare runs side by side in the MLflow UI; each row links its full trace.

Usage (env needs ADO_ORG_URL, ADO_PAT, DATABRICKS_HOST, DATABRICKS_TOKEN):

  python scripts/eval_copilot.py --endpoint databricks-llama-4-maverick
  python scripts/eval_copilot.py --endpoint databricks-claude-sonnet-5 \
      --judge-model databricks:/databricks-claude-sonnet-5

Then open the experiment and compare the two runs' scorer metrics.

Notes
- Judge defaults to the endpoint under test — fine for smoke runs, but for a
  real comparison pin ONE judge model for both runs (ideally the strongest
  available, and not one of the contestants).
- Extra dep beyond the app: pandas (mlflow's evaluate needs it). Dev-only.
"""
import argparse
import asyncio
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

import mlflow  # noqa: E402
from mlflow.genai import evaluate  # noqa: E402
from mlflow.genai.scorers import ExpectationsGuidelines, scorer  # noqa: E402


# ---- deterministic scorers (the invariants that must not regress) --------------------


@scorer
def called_expected_tool(inputs, outputs, expectations):
    """Did the agent reach for one of the tools this task is about?"""
    want = expectations.get("expected_tools")
    if not want:
        return True
    used = {t["name"] for t in outputs.get("toolCalls", [])}
    return bool(used & set(want))


@scorer
def proposal_contract(inputs, outputs, expectations):
    """Write asks become the right proposal (with the right args); tasks that
    must NOT produce proposals (hallucinated targets) produce none."""
    proposals = outputs.get("proposals", [])
    if expectations.get("forbid_proposals"):
        return not proposals
    tool = expectations.get("proposal_tool")
    if not tool:
        return True
    match = [p for p in proposals if p["tool"] == tool]
    if not match:
        return False
    need = set(expectations.get("proposal_args_contain", []))
    return need <= set(match[0]["args"])


@scorer
def no_silent_writes(inputs, outputs, expectations):
    """The propose-then-apply invariant: write tools NEVER appear as executed
    tool calls, whatever the model tries."""
    from app.copilot import WRITE_TOOL_NAMES

    used = {t["name"] for t in outputs.get("toolCalls", [])}
    return not (used & set(WRITE_TOOL_NAMES))


@scorer
def step_efficiency(inputs, outputs, expectations):
    """Tool calls used vs the task's budget — flags models that flail."""
    return len(outputs.get("toolCalls", [])) <= int(expectations.get("max_steps", 6))


@scorer(aggregations=["mean", "p90"])
def latency_seconds(inputs, outputs, expectations):
    return float(outputs.get("_latencySec", 0.0))


# ---- harness --------------------------------------------------------------------------


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--endpoint", required=True, help="FMAPI chat endpoint under test")
    ap.add_argument(
        "--judge-model", default=None,
        help="Judge for guideline scorers, e.g. databricks:/databricks-claude-sonnet-5. "
             "Defaults to the endpoint under test — pin one judge when comparing two runs.",
    )
    ap.add_argument("--tasks", default=str(Path(__file__).parent.parent / "evals/copilot_tasks.json"))
    ap.add_argument("--experiment", default="/Shared/ado-companion-evals",
                    help="MLflow experiment path (created if missing)")
    ap.add_argument("--only", default=None, help="comma-separated task names to run")
    args = ap.parse_args()

    from app.config import settings

    settings.copilot_endpoint = args.endpoint  # the ONLY thing that varies between runs
    from app import copilot

    copilot.resolve_endpoint.cache_clear() if hasattr(copilot.resolve_endpoint, "cache_clear") else None

    suite = json.loads(Path(args.tasks).read_text())
    tasks = suite["tasks"]
    if args.only:
        keep = {n.strip() for n in args.only.split(",")}
        tasks = [t for t in tasks if t["name"] in keep]
    project = suite.get("project", "home")

    data = [
        {
            "inputs": {"message": t["inputs"]["message"], "project": project},
            "expectations": t["expectations"],
        }
        for t in tasks
    ]

    def predict_fn(message: str, project: str):
        t0 = time.monotonic()
        out = asyncio.run(copilot.chat(project, message))
        out["_latencySec"] = round(time.monotonic() - t0, 2)
        # keep eval rows light — tables/full args live in the linked trace
        out.pop("tables", None)
        return out

    judge = args.judge_model or f"databricks:/{args.endpoint}"
    scorers = [
        called_expected_tool,
        proposal_contract,
        no_silent_writes,
        step_efficiency,
        latency_seconds,
        ExpectationsGuidelines(name="judge_guidelines", model=judge),
    ]

    # runs belong in the workspace experiment, whatever local config is lying around
    mlflow.set_tracking_uri("databricks")
    mlflow.set_experiment(args.experiment)
    with mlflow.start_run(run_name=args.endpoint):
        mlflow.log_params({
            "endpoint": args.endpoint,
            "judge_model": judge,
            "tasks": len(data),
            "suite": Path(args.tasks).name,
        })
        result = evaluate(data=data, predict_fn=predict_fn, scorers=scorers)

    print(f"\nendpoint={args.endpoint} judge={judge} tasks={len(data)}")
    for k, v in sorted(result.metrics.items()):
        print(f"  {k}: {v}")
    print(f"run_id: {result.run_id}")


if __name__ == "__main__":
    main()
