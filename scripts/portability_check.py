"""
Warehouse-portability lint for the dbt models.

These models must run on DuckDB (local, CI) AND Snowflake. This script fails if a model
uses a construct that works in only one of them. It is cheap, needs no database, and runs in CI.

Add a rule here whenever a warehouse-specific bug is found.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

# (regex, why it is not portable, what to use instead)
RULES = [
    (r"\bdate_diff\s*\(", "DuckDB-only function; Snowflake uses DATEDIFF", "{{ dbt.datediff(a, b, 'day') }}"),
    (r"\bfilter\s*\(\s*where\b", "aggregate FILTER clause is not supported by Snowflake", "sum(case when ... then 1 else 0 end)"),
    (r"\b(list_|array_agg_distinct|struct_pack|unnest)\w*\s*\(", "DuckDB list/struct functions", "dbt_utils / plain SQL"),
    (r"\bstrftime\s*\(|\bstrptime\s*\(", "DuckDB date formatting", "to_char / to_date via dbt macros"),
    (r"\bqualify\b", "QUALIFY is supported by Snowflake and DuckDB but not by every adapter; avoid unless needed", "subquery + row_number()"),
    (r"\bgenerate_series\s*\(", "DuckDB/Postgres function; Snowflake uses GENERATOR", "dbt_utils.date_spine"),
]


def strip_comments(sql: str) -> str:
    sql = re.sub(r"--[^\n]*", "", sql)
    sql = re.sub(r"\{#.*?#\}", "", sql, flags=re.S)
    return re.sub(r"/\*.*?\*/", "", sql, flags=re.S)


def main() -> int:
    problems = []
    files = sorted(list((ROOT / "models").rglob("*.sql")) + list((ROOT / "tests").glob("*.sql")))
    for f in files:
        text = strip_comments(f.read_text(encoding="utf-8"))
        for lineno, line in enumerate(text.splitlines(), 1):
            for pattern, why, fix in RULES:
                if re.search(pattern, line, re.I):
                    problems.append(f"{f.relative_to(ROOT)}:{lineno}: {why}. Use: {fix}\n    {line.strip()}")
    if problems:
        print("Portability problems:\n" + "\n".join(problems))
        return 1
    print(f"portability check passed: {len(files)} SQL files, {len(RULES)} rules")
    return 0


if __name__ == "__main__":
    sys.exit(main())
