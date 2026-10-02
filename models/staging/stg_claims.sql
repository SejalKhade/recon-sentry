-- Clean staging for customer claims.

with source as (
    select * from {{ source('raw', 'claims') }}
)

select
    claim_id,
    contract_id,
    servicer_id,
    cast(claim_date as date)                     as claim_date,
    cast(claim_amount as decimal(12,2))          as claim_amount,
    status
from source
