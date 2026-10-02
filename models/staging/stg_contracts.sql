-- Clean staging for protection contracts issued by the platform.

with source as (
    select * from {{ source('raw', 'contracts') }}
)

select
    contract_id,
    sale_id,
    merchant_id,
    cast(issued_date as date)                    as issued_date,
    cast(premium as decimal(12,2))               as premium,
    cast(coverage_limit as decimal(12,2))        as coverage_limit,
    cast(term_months as integer)                 as term_months,
    status
from source
