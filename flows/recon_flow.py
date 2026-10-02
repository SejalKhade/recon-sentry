"""
Prefect flow that orchestrates the Recon Sentry pipeline:

    generate synthetic data -> dbt seed -> dbt run -> dbt test -> dbt docs

Design choices (what an orchestrator is for):
  * retries on steps that can fail for transient reasons (generate, seed, run, docs)
  * NO retry on `dbt test`: a failing data-quality test is a real finding, not a glitch
  * every dbt step is a task, so the run shows per-step state, duration and logs
  * a markdown artifact summarizes models/tests built, passed and failed
  * the same flow runs against DuckDB (target "dev") or Snowflake (target "snowflake")

Usage:
    python flows/recon_flow.py                       # run once on DuckDB
    python flows/recon_flow.py --target snowflake    # run once on Snowflake (env vars required)
    python flows/recon_flow.py --serve "0 6 * * *"   # run daily at 06:00 and keep serving
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

from prefect import flow, get_run_logger, task
from prefect.artifacts import create_markdown_artifact

ROOT = Path(__file__).resolve().parent.parent


class DbtStepFailed(RuntimeError):
    """A dbt command exited non-zero."""


def _run(cmd: list[str]) -> str:
    logger = get_run_logger()
    logger.info("$ %s", " ".join(cmd))
    proc = subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True)
    tail = "\n".join((proc.stdout or "").strip().splitlines()[-12:])
    if proc.returncode != 0:
        logger.error("Step failed (exit %s):\n%s\n%s", proc.returncode, tail, (proc.stderr or "")[-600:])
        raise DbtStepFailed(f"{' '.join(cmd)} exited with {proc.returncode}")
    logger.info("OK\n%s", tail)
    return tail


@task(name="generate-data", retries=2, retry_delay_seconds=5)
def generate_data() -> str:
    return _run([sys.executable, "data_generator.py"])


@task(name="dbt-seed", retries=2, retry_delay_seconds=10)
def dbt_seed(target: str) -> str:
    return _run(["dbt", "seed", "--profiles-dir", ".", "--target", target])


@task(name="dbt-run", retries=2, retry_delay_seconds=10)
def dbt_run(target: str) -> str:
    return _run(["dbt", "run", "--profiles-dir", ".", "--target", target])


@task(name="dbt-test")  # deliberately no retries: a failing test is a data finding
def dbt_test(target: str) -> str:
    return _run(["dbt", "test", "--profiles-dir", ".", "--target", target])


@task(name="dbt-docs", retries=1, retry_delay_seconds=5)
def dbt_docs(target: str) -> str:
    return _run(["dbt", "docs", "generate", "--profiles-dir", ".", "--target", target])


def _summarize() -> dict:
    """Read dbt's own run_results.json for the most recent command."""
    path = ROOT / "target" / "run_results.json"
    if not path.exists():
        return {}
    data = json.loads(path.read_text(encoding="utf-8"))
    counts: dict[str, int] = {}
    for r in data.get("results", []):
        counts[r["status"]] = counts.get(r["status"], 0) + 1
    return {"counts": counts, "elapsed": round(data.get("elapsed_time", 0), 2)}


@flow(name="recon-sentry-pipeline", log_prints=True)
def recon_pipeline(target: str = "dev", generate: bool = True, docs: bool = True) -> dict:
    """Run the whole reconciliation pipeline and return a summary."""
    steps: list[tuple[str, str]] = []
    if generate:
        generate_data()
        steps.append(("generate data", "ok"))
    dbt_seed(target)
    steps.append(("dbt seed", "ok"))
    dbt_run(target)
    steps.append(("dbt run", "ok"))
    test_tail = dbt_test(target)
    steps.append(("dbt test", "ok"))
    test_summary = _summarize()
    if docs:
        dbt_docs(target)
        steps.append(("dbt docs generate", "ok"))

    summary = {"target": target, "steps": steps, "tests": test_summary, "test_output_tail": test_tail}
    rows = "\n".join(f"| {name} | {status} |" for name, status in steps)
    create_markdown_artifact(
        key="recon-sentry-run",
        markdown=(f"## Recon Sentry run on `{target}`\n\n| Step | Result |\n|---|---|\n{rows}\n\n"
                  f"dbt test results: `{test_summary.get('counts', {})}` in {test_summary.get('elapsed', '?')}s\n"),
        description="Per-step result of the latest pipeline run",
    )
    return summary


def main() -> None:
    ap = argparse.ArgumentParser(description="Recon Sentry orchestration (Prefect)")
    ap.add_argument("--target", default="dev", help="dbt target: dev (DuckDB) or snowflake")
    ap.add_argument("--no-generate", action="store_true", help="reuse existing seeds")
    ap.add_argument("--serve", metavar="CRON", help='serve on a schedule, e.g. "0 6 * * *"')
    a = ap.parse_args()
    if a.serve:
        recon_pipeline.serve(name="recon-sentry-scheduled", cron=a.serve,
                             parameters={"target": a.target, "generate": not a.no_generate})
    else:
        result = recon_pipeline(target=a.target, generate=not a.no_generate)
        print(json.dumps({k: result[k] for k in ("target", "steps", "tests")}, indent=2))


if __name__ == "__main__":
    main()
