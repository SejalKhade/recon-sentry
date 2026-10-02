-- Singular test: a single reimbursement should never exceed the coverage_limit
-- of the underlying contract. If this test returns rows, we have a bad
-- reimbursement that slipped past our checks.

select
    r.reimbursement_id,
    r.paid_amount,
    c.contract_id,
    c.coverage_limit
from {{ ref('stg_servicer_reimbursements') }} r
join {{ ref('stg_claims') }} cl on r.claim_id = cl.claim_id
join {{ ref('stg_contracts') }} c on cl.contract_id = c.contract_id
where r.paid_amount > c.coverage_limit
