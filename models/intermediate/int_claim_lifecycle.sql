-- Joins claims to their contract and to reimbursements.
-- One row per (claim, reimbursement) pair. Duplicate reimbursements create multiple rows.

with claims as (
    select * from {{ ref('stg_claims') }}
),
reimbursements as (
    select * from {{ ref('stg_servicer_reimbursements') }}
),
contracts as (
    select * from {{ ref('stg_contracts') }}
)

select
    cl.claim_id,
    cl.contract_id                  as claim_contract_id,
    cl.servicer_id                  as claim_servicer_id,
    cl.claim_date,
    cl.claim_amount,

    r.reimbursement_id,
    r.paid_date,
    r.paid_amount,

    c.contract_id                   as matched_contract_id,
    c.coverage_limit,

    case when c.contract_id is null then true else false end     as is_orphan_claim,
    case when r.reimbursement_id is null then true else false end as is_unpaid_claim,
    case
        when r.paid_amount is null then null
        when r.paid_amount > cl.claim_amount + 0.01 then true
        else false
    end                                                            as is_overpayment
from claims cl
left join reimbursements r on cl.claim_id = r.claim_id
left join contracts c on cl.contract_id = c.contract_id
