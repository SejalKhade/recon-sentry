-- fct_daily_break_snapshot
--
-- Point-in-time capture of the reconciliation break state.
-- One row per (snapshot_date, break_key). On every dbt run, we insert
-- rows for today's snapshot and leave historical snapshots untouched.
--
-- Why incremental: `fct_recon_breaks` is a live "as of now" view.
-- Reconciliation trend analysis (are we accumulating breaks faster than
-- we resolve them?) needs history, and history has to be append-only.
-- Rebuilding this table on every run would delete yesterday's history.
--
-- Materialization strategy:
--   - full-refresh: build the entire history (only used on first run
--     or when explicitly forced with --full-refresh).
--   - incremental: append only rows whose snapshot_date is not already
--     present in the table.
--
-- Snowflake portability: current_date is ANSI. The `unique_key` and
-- `incremental_strategy` config values work identically on Snowflake
-- and DuckDB adapters.

{{ config(
    materialized = 'incremental',
    unique_key = ['snapshot_date', 'break_key'],
    incremental_strategy = 'delete+insert',
    on_schema_change = 'append_new_columns'
) }}

with breaks as (
    select * from {{ ref('fct_recon_breaks') }}
),

todays_snapshot as (
    select
        current_date                            as snapshot_date,
        break_key,
        break_type,
        severity,
        entity_type,
        entity_id,
        merchant_id,
        servicer_id,
        opened_at,
        days_open,
        amount_at_risk,
        description
    from breaks
)

select * from todays_snapshot

{% if is_incremental() %}
    -- Only append rows for snapshot_dates we have not yet recorded.
    -- On the very first run, is_incremental() is false and we insert
    -- everything. On subsequent runs, this WHERE clause skips days
    -- already captured.
    where snapshot_date not in (
        select distinct snapshot_date from {{ this }}
    )
{% endif %}
