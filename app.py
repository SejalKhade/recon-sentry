"""
Recon Sentry - Streamlit audit dashboard.

Reads directly from the DuckDB warehouse produced by `dbt run`. Every
number on the page comes from a SQL query shown in the sidebar with
"View SQL". No hidden logic.

Run: streamlit run app.py
"""
from __future__ import annotations

import json
from pathlib import Path

import duckdb
import pandas as pd
import streamlit as st

ROOT = Path(__file__).parent
DB = ROOT / "recon_sentry.duckdb"
PLANTED = ROOT / "planted_breaks.json"


# ------------------------------------------------------------------
# Page config
# ------------------------------------------------------------------

st.set_page_config(
    page_title="Recon Sentry",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.markdown(
    """
    <style>
    :root {
        --ink: #14161a;
        --ink-soft: #4a4f57;
        --line: #d9dbe0;
        --bg-panel: #f7f8fa;
        --accent: #1f3a68;
    }
    html, body, [class*="css"] {
        font-family: "Inter", "Helvetica Neue", Arial, sans-serif;
        color: var(--ink);
    }
    h1 { font-weight: 600; font-size: 1.9rem; letter-spacing: -0.01em; }
    h2 { font-weight: 600; font-size: 1.25rem; margin-top: 1.2rem; }
    h3 { font-weight: 600; font-size: 1.05rem; color: var(--ink-soft); }
    .metric-card {
        border: 1px solid var(--line);
        border-radius: 6px;
        padding: 14px 16px;
        background: var(--bg-panel);
    }
    .metric-label { font-size: 0.78rem; color: var(--ink-soft); text-transform: uppercase; letter-spacing: 0.06em; }
    .metric-value { font-size: 1.4rem; font-weight: 600; color: var(--ink); margin-top: 4px; }
    </style>
    """,
    unsafe_allow_html=True,
)


# ------------------------------------------------------------------
# Data access
# ------------------------------------------------------------------

@st.cache_resource
def get_conn():
    if not DB.exists():
        st.error(
            "recon_sentry.duckdb not found. Run these first:\n\n"
            "  python data_generator.py\n"
            "  dbt seed --profiles-dir .\n"
            "  dbt run --profiles-dir .\n"
        )
        st.stop()
    return duckdb.connect(str(DB), read_only=True)


def q(sql: str) -> pd.DataFrame:
    return get_conn().execute(sql).df()


# ------------------------------------------------------------------
# Header
# ------------------------------------------------------------------

st.markdown("# Recon Sentry")
st.markdown(
    "Reconciliation audit dashboard for the platform's claim reimbursement and "
    "contract sales flows. Reads directly from the dbt-modeled warehouse. "
    "Every metric on this page is derived from a SQL query shown alongside it."
)

with st.expander("About this project"):
    st.markdown(
        "- Data warehouse: DuckDB locally, Snowflake-portable with one config change.\n"
        "- Transformation: dbt models (staging -> intermediate -> marts -> analytics).\n"
        "- Data quality: dbt tests plus one singular test for the coverage-limit invariant.\n"
        "- The synthetic dataset plants known break patterns; `planted_breaks.json` "
        "in the repo is the ground truth this dashboard's numbers can be checked against."
    )


# ------------------------------------------------------------------
# Top-line metrics
# ------------------------------------------------------------------

st.markdown("## 1. Reconciliation health")

kpi_sql = """
select
    count(*)                            as total_breaks,
    count(*) filter (where severity='high')   as high_severity,
    round(sum(amount_at_risk), 2)       as total_amount_at_risk,
    round(avg(days_open), 1)            as avg_days_open
from marts.fct_recon_breaks
"""
kpi = q(kpi_sql).iloc[0]

cols = st.columns(4)
for col, label, value in zip(
    cols,
    ["Total breaks", "High severity", "Amount at risk (USD)", "Average days open"],
    [int(kpi.total_breaks), int(kpi.high_severity), f"${kpi.total_amount_at_risk:,.2f}", kpi.avg_days_open],
):
    col.markdown(
        f"<div class='metric-card'><div class='metric-label'>{label}</div>"
        f"<div class='metric-value'>{value}</div></div>",
        unsafe_allow_html=True,
    )

with st.expander("View SQL"):
    st.code(kpi_sql, language="sql")


# ------------------------------------------------------------------
# Break aging
# ------------------------------------------------------------------

st.markdown("## 2. Break aging by category")
st.caption(
    "How stale is each type of break. Rows at the top are the ones the "
    "operations lead would triage first."
)

aging_sql = "select * from analytics.break_aging order by severity, break_type, aging_bucket"
aging_df = q(aging_sql)
st.dataframe(aging_df, use_container_width=True, hide_index=True)

with st.expander("View SQL"):
    st.code(aging_sql, language="sql")


# ------------------------------------------------------------------
# Merchant scorecard
# ------------------------------------------------------------------

st.markdown("## 3. Merchant scorecard")
st.caption("Which merchants are generating the most reconciliation friction, and how much money is exposed.")

scorecard_sql = "select * from analytics.merchant_scorecard"
scorecard_df = q(scorecard_sql)
st.dataframe(scorecard_df, use_container_width=True, hide_index=True)

with st.expander("View SQL"):
    st.code(scorecard_sql, language="sql")


# ------------------------------------------------------------------
# Break drilldown
# ------------------------------------------------------------------

st.markdown("## 4. Break drilldown")
st.caption("The full list of open breaks. Filter by type or severity to triage.")

break_types = q("select distinct break_type from marts.fct_recon_breaks order by 1").break_type.tolist()
sev = q("select distinct severity from marts.fct_recon_breaks order by 1").severity.tolist()

c1, c2 = st.columns(2)
selected_types = c1.multiselect("Break type", break_types, default=break_types)
selected_sev = c2.multiselect("Severity", sev, default=sev)

if selected_types and selected_sev:
    where_types = "'" + "','".join(selected_types) + "'"
    where_sev = "'" + "','".join(selected_sev) + "'"
    drill_sql = f"""
    select
        break_type,
        severity,
        entity_type,
        entity_id,
        coalesce(merchant_id, servicer_id) as counterparty,
        opened_at,
        days_open,
        amount_at_risk,
        description
    from marts.fct_recon_breaks
    where break_type in ({where_types})
      and severity in ({where_sev})
    order by severity, days_open desc
    """
    st.dataframe(q(drill_sql), use_container_width=True, hide_index=True)
    with st.expander("View SQL"):
        st.code(drill_sql, language="sql")


# ------------------------------------------------------------------
# Ground-truth validation
# ------------------------------------------------------------------

st.markdown("## 5. Ground-truth validation")
st.caption(
    "This dashboard runs on synthetic data with pre-planted break "
    "patterns. The table below compares how many of each type of break "
    "were planted vs how many the dbt pipeline caught."
)

if PLANTED.exists():
    planted = json.loads(PLANTED.read_text())
    planted_df = pd.DataFrame(planted)
    planted_counts = planted_df.groupby("break_type").size().reset_index(name="planted")

    detected_sql = "select break_type, count(*) as detected from marts.fct_recon_breaks group by 1"
    detected_df = q(detected_sql)

    comparison = planted_counts.merge(detected_df, on="break_type", how="outer").fillna(0)
    comparison["planted"] = comparison["planted"].astype(int)
    comparison["detected"] = comparison["detected"].astype(int)
    comparison["catch_rate"] = comparison.apply(
        lambda r: f"{(r.detected / r.planted * 100):.0f}%" if r.planted else "N/A",
        axis=1,
    )
    st.dataframe(comparison, use_container_width=True, hide_index=True)
    st.caption(
        "Note: some break types (e.g. timing_break) can be detected in "
        "excess of what was planted because the pipeline also flags natural "
        "cases beyond the intentional plants. Detected < planted is the "
        "signal to investigate."
    )
else:
    st.info("planted_breaks.json not found; ground-truth validation unavailable.")


st.markdown("---")
st.caption(
    "Recon Sentry is a proof-of-concept reconciliation pipeline for the "
    "claim reimbursement and contract sales flow. Portable to Snowflake by "
    "changing the profile from duckdb to snowflake in profiles.yml. Every "
    "SQL query is auditable, and dbt tests enforce the invariants."
)
