# Snowflake Run — Verified 2026-11-19

**Account:** `SK92715.us-east-2.aws` (AWS US-East-2)  
**Database:** `RECON_SENTRY`  
**Schema:** `RECON`  
**Warehouse:** `COMPUTE_WH` (X-Small)  
**dbt version:** 1.12.5  
**Adapter:** dbt-snowflake 1.12.1

## Result

```
Running with dbt=1.12.5
Registered adapter: snowflake=1.12.1
Found 10 models, 48 data tests, 6 seeds, 6 sources, 562 macros

Concurrency: 4 threads (target='snowflake')

Finished running 1 incremental model, 6 seeds, 3 table models, 48 data tests, 6 view models
in 0 hours 0 minutes and 18.64 seconds (18.64s).

Completed successfully

Done. PASS=64 WARN=0 ERROR=0 SKIP=0 NO-OP=0 REUSED=0 TOTAL=64
```

All 64 steps passed: 6 seeds loaded, 10 models built (staging views, intermediate views, mart tables, incremental snapshot), and all 48 data tests passed — including the singular business-invariant test (`reimbursement_never_exceeds_coverage`).
