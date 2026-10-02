# Recon Sentry

[![dbt CI](https://github.com/SejalKhade/recon-sentry/actions/workflows/dbt.yml/badge.svg)](https://github.com/SejalKhade/recon-sentry/actions/workflows/dbt.yml)

A dbt reconciliation pipeline for the claim-reimbursement and contract-sales flow of a
hypothetical protection-plan platform (synthetic data). It finds seven kinds of financial
reconciliation break across merchants, the platform, and servicers; tests the data with
48 dbt tests; runs on DuckDB locally and on Snowflake; and is orchestrated with Prefect.

## Run it

```bash
pip install -r requirements.txt
python data_generator.py                 # synthetic data with 32 planted breaks
dbt build --profiles-dir .               # 6 seeds + 10 models + 48 tests
streamlit run app.py                     # audit dashboard
python flows/recon_flow.py               # same pipeline as an orchestrated Prefect flow
```

## What is verified

| Claim | How it was checked |
|---|---|
| 10 models in staging, intermediate, marts and analytics layers; 6 seeds | `dbt build`: 64 of 64 pass |
| 48 data tests (47 generic + 1 singular business invariant) | `dbt build` / `dbt test` |
| Incremental model with `delete+insert` (`fct_daily_break_snapshot`) | built and re-run without duplicating a day |
| Models avoid warehouse-specific SQL | `scripts/portability_check.py` in CI (it fails if `date_diff` or aggregate `FILTER` come back) |
| Orchestration with retries | `pytest flows`: full run, no retry on a failing `dbt test`, retry on a transient failure |
| Snowflake | Profile and models parse for the Snowflake adapter. **A real Snowflake run is recorded in `docs/snowflake_run.md` once `scripts/check_snowflake.py` has been run.** |

## Architecture

```
data_generator.py  ->  seeds/*.csv  ->  dbt seed
  staging      stg_claims, stg_contracts, stg_merchant_sales, stg_servicer_reimbursements   (typed views)
  intermediate int_contract_lifecycle, int_claim_lifecycle                                  (joins, flags)
  marts        fct_recon_breaks (7 break types), fct_daily_break_snapshot (incremental)
  analytics    break_aging, merchant_scorecard
tests/         singular test: a reimbursement never exceeds coverage
app.py         Streamlit dashboard; every metric shows its SQL
flows/         Prefect flow: generate -> seed -> run -> test -> docs
scripts/       portability_check.py (CI lint), check_snowflake.py (real-account proof)
```

## Break types

`orphan_contract`, `timing_break`, `amount_break`, `orphan_claim`, `duplicate_claim`,
`overpayment`, `coverage_exceeded`. The dashboard compares planted breaks with detected ones;
detected counts can exceed planted because the random data also contains natural breaks.

## Run on Snowflake

```bash
pip install -r requirements-snowflake.txt
export SNOWFLAKE_ACCOUNT=<orgname-accountname> SNOWFLAKE_USER=... SNOWFLAKE_PASSWORD=...
python scripts/check_snowflake.py      # dbt debug + dbt build on Snowflake, writes docs/snowflake_run.md
```

Credentials are read from environment variables only. To run Snowflake in CI, add
`SNOWFLAKE_ACCOUNT`, `SNOWFLAKE_USER` and `SNOWFLAKE_PASSWORD` as repository secrets; the
`snowflake` job is skipped when they are absent.

Warehouse differences handled in the models: `dbt.datediff` instead of `date_diff`,
`CASE` instead of aggregate `FILTER`, and `sources.yml` follows `target.schema`.

## Orchestration

```bash
python flows/recon_flow.py                       # run once
python flows/recon_flow.py --target snowflake    # run once on Snowflake
python flows/recon_flow.py --serve "0 6 * * *"   # daily at 06:00
```

Transient steps (generate, seed, run, docs) retry; `dbt test` does not, because a failing
test is a data finding rather than a glitch. Each run publishes a markdown summary artifact.

## What this project does not claim

- It is not a production reconciliation system: no alerting, backfills, or real accounting
  integration.
- Break severity is coarse (high / medium).
- Not a fraud detector; some break types are fraud indicators, classification is separate.
- Not benchmarked at scale: it runs on 300 sales and finishes in seconds.
- The Postman collection is illustrative; the APIs are not real.
