# Recon Sentry

[![dbt CI](https://github.com/SejalKhade/recon-sentry/actions/workflows/dbt.yml/badge.svg)](https://github.com/SejalKhade/recon-sentry/actions/workflows/dbt.yml)

**Stack:** dbt · Snowflake · DuckDB · Python · Prefect · Streamlit · GitHub Actions

A production-pattern dbt pipeline that detects financial reconciliation breaks across a protection-plan platform — merchants, contracts, claims, and servicer reimbursements. Runs end-to-end on Snowflake with 48 automated data tests and CI on every push.

---

## Validated on Snowflake

```
dbt build --target snowflake
Done. PASS=64  WARN=0  ERROR=0  SKIP=0  TOTAL=64  (18.6s)
```

Account: AWS US-East-2 · Warehouse: COMPUTE_WH · Full log: [`docs/snowflake_run.md`](docs/snowflake_run.md)

---

## What it does

Detects 7 break types across the claim-reimbursement and contract-sales flow:

`orphan_contract` · `timing_break` · `amount_break` · `orphan_claim` · `duplicate_claim` · `overpayment` · `coverage_exceeded`

A Streamlit audit dashboard shows detected vs. planted breaks with the underlying SQL for every metric.

---

## Architecture — Medallion layers

```
Raw seeds (CSV)
  └── staging      stg_claims, stg_contracts, stg_merchant_sales, stg_servicer_reimbursements
        └── intermediate   int_contract_lifecycle, int_claim_lifecycle
              └── marts    fct_recon_breaks · fct_daily_break_snapshot (incremental, delete+insert)
                    └── analytics   break_aging · merchant_scorecard
```

---

## Data quality — 48 tests

| Layer | Tests |
|---|---|
| Sources | not_null, unique, referential integrity on all 6 source tables |
| Staging | not_null + unique on every model |
| Marts | accepted_values, not_null, unique + 1 singular business invariant |
| Singular invariant | `reimbursement_never_exceeds_coverage` — a reimbursement can never exceed its contract's coverage limit |

---

## CI — runs on every push and PR

```yaml
jobs:
  dbt-ci:   dbt build (seeds + models + 48 tests) on DuckDB — no credentials needed
  snowflake: dbt build on Snowflake — runs when SNOWFLAKE_* secrets are set
```

---

## Run locally

```bash
pip install -r requirements.txt
python data_generator.py        # generates synthetic data with 32 planted breaks
dbt build --profiles-dir .      # 6 seeds + 10 models + 48 tests → all pass
streamlit run app.py            # audit dashboard
python flows/recon_flow.py      # Prefect-orchestrated pipeline with retries
```

## Run on Snowflake

```bash
pip install -r requirements-snowflake.txt
export SNOWFLAKE_ACCOUNT=<orgname-accountname> SNOWFLAKE_USER=... SNOWFLAKE_PASSWORD=...
dbt build --profiles-dir . --target snowflake
```

Credentials are read from environment variables only — never committed.

---

## Orchestration (Prefect)

```bash
python flows/recon_flow.py                       # run once
python flows/recon_flow.py --target snowflake    # run once on Snowflake
python flows/recon_flow.py --serve "0 6 * * *"   # schedule daily at 06:00
```

Transient steps (generate, seed, run, docs) retry on failure. `dbt test` does not retry — a failing test is a data finding, not a glitch.
