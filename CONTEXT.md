# CONTEXT.md

## The business problem

Recon Sentry models a hypothetical protection-plan platform for online
retailers. Its business runs on financial reconciliation across three
parties:

- **Merchants** sell protection plans alongside their products.
- **The platform** records the protection contracts, collects premiums from
  merchants, and pays claims.
- **Servicers** fulfill approved claims and get reimbursed by the platform.

Every day, thousands of these three-way transactions have to reconcile:
merchant remittance = contracts sold, servicer claims = reimbursements paid,
and no contract can exceed its coverage limit. The data here is synthetic.

## What Recon Sentry does

Given four operational data streams (merchant sales, contracts, claims,
servicer reimbursements), the pipeline:

1. Types and cleans the raw data in a staging layer with dbt tests.
2. Joins the streams in an intermediate layer to build contract and
   claim lifecycle views.
3. Detects seven categories of reconciliation break in a canonical fact
   table (`fct_recon_breaks`).
4. Aggregates the breaks into aging reports and merchant scorecards
   analysts and account managers would actually use.
5. Presents everything in a Streamlit dashboard where every metric shows
   the SQL that produced it.

## The seven break categories

- `orphan_contract` - A contract exists with no merchant sale to back it up.
  Either the merchant sale was never received, or the contract was created
  in error.
- `timing_break` - The contract was issued but the merchant has not
  remitted the premium within the SLA (14 days by default).
- `amount_break` - The remittance does not match the contract premium.
- `orphan_claim` - A servicer submitted a claim for a contract that does
  not exist.
- `duplicate_claim` - The same claim was reimbursed more than once.
- `overpayment` - Reimbursement exceeds the underlying claim amount.
- `coverage_exceeded` - Cumulative payouts on one contract exceed its
  coverage limit.

## Why dbt-duckdb locally, Snowflake as a second target

The whole pipeline runs locally with no cloud dependencies, so anyone can
`git clone` it and reproduce the numbers. The same models also target
Snowflake: warehouse-specific SQL is avoided (dbt's cross-database macros
replace `date_diff`, and aggregate `FILTER` clauses are written as `CASE`),
and `profiles.yml` has a `snowflake` target driven by environment variables.
`scripts/check_snowflake.py` runs the build against a real account and writes
a dated evidence file.

## Ground-truth validation

The synthetic data generator plants known breaks and writes them to
`planted_breaks.json`. The dashboard's final section compares planted vs
detected counts per category. If detection drops below plants, something
regressed. Detected counts often exceed planted counts because the pipeline
also catches natural breaks that emerged from random data.

## What this project does not claim

- It is not a production reconciliation system. Real production would need
  alerting, backfills, and integration with an actual accounting system.
- Break severity is coarse (high / medium). Real deployments would tune
  severity by dollar impact and business relationship.
- The API integrations in `postman/` are illustrative, not real.
- No fraud detection is claimed. Some break types are fraud indicators, but
  classifying fraud is a separate downstream problem.

## References

- dbt-duckdb: https://github.com/duckdb/dbt-duckdb
- dbt-snowflake: https://docs.getdbt.com/docs/core/connect-data-platform/snowflake-setup
- dbt best practices: https://docs.getdbt.com/best-practices
