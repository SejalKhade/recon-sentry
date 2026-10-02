-- Per-merchant scorecard: which merchants cause the most reconciliation friction.
-- Useful for account-management conversations with merchants.

with breaks as (
    select * from {{ ref('fct_recon_breaks') }} where merchant_id is not null
),
merchants as (
    select * from {{ source('raw', 'merchants') }}
),
contracts as (
    select * from {{ ref('stg_contracts') }}
),

merchant_totals as (
    select
        merchant_id,
        count(distinct contract_id) as total_contracts,
        sum(premium)                as total_premium_expected
    from contracts
    group by merchant_id
),

merchant_breaks as (
    select
        merchant_id,
        count(*)                                                as total_breaks,
        sum(amount_at_risk)                                     as total_amount_at_risk,
        sum(case when break_type = 'timing_break' then 1 else 0 end)     as timing_breaks,
        sum(case when break_type = 'amount_break' then 1 else 0 end)     as amount_breaks,
        sum(case when break_type = 'orphan_contract' then 1 else 0 end)  as orphan_contracts
    from breaks
    group by merchant_id
)

select
    m.merchant_id,
    m.merchant_name,
    m.category,
    coalesce(mt.total_contracts, 0)             as total_contracts,
    round(coalesce(mt.total_premium_expected, 0), 2) as total_premium_expected,
    coalesce(mb.total_breaks, 0)                as total_breaks,
    round(coalesce(mb.total_amount_at_risk, 0), 2) as total_amount_at_risk,
    coalesce(mb.timing_breaks, 0)               as timing_breaks,
    coalesce(mb.amount_breaks, 0)               as amount_breaks,
    coalesce(mb.orphan_contracts, 0)            as orphan_contracts,
    case
        when coalesce(mt.total_contracts, 0) = 0 then 0
        else round(coalesce(mb.total_breaks, 0) * 1.0 / mt.total_contracts, 3)
    end                                          as break_rate
from merchants m
left join merchant_totals mt on m.merchant_id = mt.merchant_id
left join merchant_breaks mb on m.merchant_id = mb.merchant_id
order by total_breaks desc
