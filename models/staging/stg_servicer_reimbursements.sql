-- Clean staging for servicer reimbursements paid by the platform.

with source as (
    select * from {{ source('raw', 'servicer_reimbursements') }}
)

select
    reimbursement_id,
    claim_id,
    servicer_id,
    cast(paid_date as date)                      as paid_date,
    cast(paid_amount as decimal(12,2))           as paid_amount
from source
