-- fct_recon_breaks: the single canonical fact table of every reconciliation
-- break detected across all sources. One row per break. Downstream reports
-- and the Streamlit dashboard read from this table.

-- Break types detected here:
--   orphan_contract    - contract with no matching merchant sale
--   timing_break       - remittance not received within SLA (14 days default)
--   amount_break       - remittance amount != contract premium
--   orphan_claim       - claim references non-existent contract
--   duplicate_claim    - same claim reimbursed more than once
--   overpayment        - reimbursement exceeds the underlying claim amount
--   coverage_exceeded  - cumulative payouts on one contract exceed coverage_limit

{% set today = "'2025-07-01'" %}  {# fixed 'as of' date so runs are reproducible #}
{% set timing_sla_days = 14 %}

with contract_lifecycle as (
    select * from {{ ref('int_contract_lifecycle') }}
),
claim_lifecycle as (
    select * from {{ ref('int_claim_lifecycle') }}
),

-- 1. orphan_contract
orphan_contracts as (
    select
        'orphan_contract'                       as break_type,
        'high'                                  as severity,
        contract_id                             as entity_id,
        'contract'                              as entity_type,
        contract_merchant_id                    as merchant_id,
        null::varchar                           as servicer_id,
        issued_date                             as opened_at,
        contract_premium                        as amount_at_risk,
        'Contract issued but no matching merchant sale exists.' as description
    from contract_lifecycle
    where is_orphan_contract = true
),

-- 2. timing_break: sale exists but remittance not received within SLA
timing_breaks as (
    select
        'timing_break'                          as break_type,
        case
            when {{ dbt.datediff('issued_date', 'cast(' ~ today ~ ' as date)', 'day') }} > 30 then 'high'
            else 'medium'
        end                                     as severity,
        contract_id                             as entity_id,
        'contract'                              as entity_type,
        contract_merchant_id                    as merchant_id,
        null::varchar                           as servicer_id,
        issued_date                             as opened_at,
        contract_premium                        as amount_at_risk,
        'Merchant has not remitted premium within '
            || {{ timing_sla_days }}
            || ' days of contract issuance.' as description
    from contract_lifecycle
    where is_orphan_contract = false
      and is_unpaid = true
      and {{ dbt.datediff('issued_date', 'cast(' ~ today ~ ' as date)', 'day') }} > {{ timing_sla_days }}
),

-- 3. amount_break
amount_breaks as (
    select
        'amount_break'                          as break_type,
        'medium'                                as severity,
        contract_id                             as entity_id,
        'contract'                              as entity_type,
        contract_merchant_id                    as merchant_id,
        null::varchar                           as servicer_id,
        issued_date                             as opened_at,
        abs(coalesce(sale_remittance_amount, 0) - contract_premium) as amount_at_risk,
        'Remittance amount '
            || cast(sale_remittance_amount as varchar)
            || ' does not match contract premium '
            || cast(contract_premium as varchar) as description
    from contract_lifecycle
    where has_amount_break = true
),

-- 4. orphan_claim
orphan_claims as (
    select distinct
        'orphan_claim'                          as break_type,
        'high'                                  as severity,
        claim_id                                as entity_id,
        'claim'                                 as entity_type,
        null::varchar                           as merchant_id,
        claim_servicer_id                       as servicer_id,
        claim_date                              as opened_at,
        claim_amount                            as amount_at_risk,
        'Claim references contract_id that does not exist in the contracts table.' as description
    from claim_lifecycle
    where is_orphan_claim = true
),

-- 5. duplicate_claim: claim_id appears more than once in reimbursements
duplicate_claims as (
    select
        'duplicate_claim'                       as break_type,
        'high'                                  as severity,
        claim_id                                as entity_id,
        'claim'                                 as entity_type,
        null::varchar                           as merchant_id,
        any_value(claim_servicer_id)            as servicer_id,
        min(claim_date)                         as opened_at,
        sum(paid_amount) - max(claim_amount)    as amount_at_risk,
        'Claim reimbursed '
            || cast(count(*) as varchar)
            || ' times, total paid = '
            || cast(sum(paid_amount) as varchar) as description
    from claim_lifecycle
    where reimbursement_id is not null
    group by claim_id
    having count(*) > 1
),

-- 6. overpayment
overpayments as (
    select
        'overpayment'                           as break_type,
        'medium'                                as severity,
        reimbursement_id                        as entity_id,
        'reimbursement'                         as entity_type,
        null::varchar                           as merchant_id,
        claim_servicer_id                       as servicer_id,
        paid_date                               as opened_at,
        paid_amount - claim_amount              as amount_at_risk,
        'Paid '
            || cast(paid_amount as varchar)
            || ' exceeds claim amount '
            || cast(claim_amount as varchar)    as description
    from claim_lifecycle
    where is_overpayment = true
),

-- 7. coverage_exceeded: cumulative payouts on a contract > its coverage_limit
contract_payouts as (
    select
        claim_contract_id                       as contract_id,
        sum(coalesce(paid_amount, 0))           as total_paid
    from claim_lifecycle
    where claim_contract_id is not null
      and reimbursement_id is not null
    group by claim_contract_id
),
coverage_exceeded as (
    select
        'coverage_exceeded'                     as break_type,
        'high'                                  as severity,
        cp.contract_id                          as entity_id,
        'contract'                              as entity_type,
        cl.contract_merchant_id                 as merchant_id,
        null::varchar                           as servicer_id,
        cl.issued_date                          as opened_at,
        cp.total_paid - cl.coverage_limit       as amount_at_risk,
        'Total paid '
            || cast(cp.total_paid as varchar)
            || ' exceeds coverage_limit '
            || cast(cl.coverage_limit as varchar) as description
    from contract_payouts cp
    join contract_lifecycle cl on cp.contract_id = cl.contract_id
    where cp.total_paid > cl.coverage_limit
),

all_breaks as (
    select * from orphan_contracts
    union all select * from timing_breaks
    union all select * from amount_breaks
    union all select * from orphan_claims
    union all select * from duplicate_claims
    union all select * from overpayments
    union all select * from coverage_exceeded
)

select
    row_number() over (order by opened_at, entity_id) as break_key,
    break_type,
    severity,
    entity_type,
    entity_id,
    merchant_id,
    servicer_id,
    opened_at,
    {{ dbt.datediff('opened_at', 'cast(' ~ today ~ ' as date)', 'day') }} as days_open,
    round(amount_at_risk, 2) as amount_at_risk,
    description,
    cast({{ today }} as date) as as_of_date
from all_breaks
