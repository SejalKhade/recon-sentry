"""
One-command proof that Recon Sentry runs on a REAL Snowflake account.

Setup (free 30-day trial is enough):
    pip install -r requirements-snowflake.txt
    export SNOWFLAKE_ACCOUNT=<orgname-accountname>   # Snowsight > account menu > copy account identifier
    export SNOWFLAKE_USER=...
    export SNOWFLAKE_PASSWORD=...
    # optional: SNOWFLAKE_ROLE SNOWFLAKE_WAREHOUSE SNOWFLAKE_DATABASE SNOWFLAKE_SCHEMA
    python scripts/check_snowflake.py

It runs `dbt debug` and `dbt build` (seeds, models, tests) with --target snowflake,
reads dbt's run_results.json, queries the break counts, and writes docs/snowflake_run.md
(UTC timestamp, dbt version, pass/fail counts). Commit that file as evidence.
Exit code is non-zero if anything fails, so it also works in CI with repository secrets.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
REQUIRED = ["SNOWFLAKE_ACCOUNT", "SNOWFLAKE_USER", "SNOWFLAKE_PASSWORD"]


def dbt(*args: str) -> subprocess.CompletedProcess:
    cmd = ["dbt", *args, "--profiles-dir", ".", "--target", "snowflake"]
    print("$", " ".join(cmd), flush=True)
    return subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True)


def main() -> int:
    missing = [k for k in REQUIRED if not os.environ.get(k)]
    if missing:
        print(f"Missing environment variables: {missing}. See the docstring at the top of this file.")
        return 2

    dbg = dbt("debug")
    if dbg.returncode != 0:
        print(dbg.stdout[-1500:], dbg.stderr[-500:])
        print("dbt debug failed: check account identifier, user, password, role and warehouse.")
        return 1

    build = dbt("build")
    print("\n".join(build.stdout.splitlines()[-10:]))
    results = json.loads((ROOT / "target" / "run_results.json").read_text(encoding="utf-8"))
    counts: dict[str, int] = {}
    for r in results["results"]:
        counts[r["status"]] = counts.get(r["status"], 0) + 1

    show = dbt("show", "--inline",
               "select break_type, count(*) as breaks, round(sum(amount_at_risk), 2) as amount_at_risk "
               "from {{ ref('fct_recon_breaks') }} group by 1 order by 1", "--limit", "20")
    ver = subprocess.run(["dbt", "--version"], cwd=ROOT, capture_output=True, text=True).stdout.strip()

    ok = build.returncode == 0
    out = ROOT / "docs"
    out.mkdir(exist_ok=True)
    (out / "snowflake_run.md").write_text(
        f"# Snowflake run evidence\n\n"
        f"- Run at (UTC): {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S')}\n"
        f"- Result: **{'PASS' if ok else 'FAIL'}**\n"
        f"- dbt statuses: `{counts}`\n"
        f"- Database / schema: `{os.environ.get('SNOWFLAKE_DATABASE', 'RECON_SENTRY')}` / "
        f"`{os.environ.get('SNOWFLAKE_SCHEMA', 'RECON')}`\n\n"
        f"## Versions\n```\n{ver}\n```\n\n"
        f"## Breaks detected on Snowflake\n```\n{show.stdout[-1800:]}\n```\n",
        encoding="utf-8")
    print(f"\n{'PASS' if ok else 'FAIL'}: {counts}\nEvidence written to docs/snowflake_run.md")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
