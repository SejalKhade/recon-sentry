-- Clean, typed staging layer for merchant sales.
-- One row per sale. Nulls in remittance_date mean the merchant has not yet remitted.

with source as (
    select * from {{ source('raw', 'merchant_sales') }}
)

select
    sale_id,
    merchant_id,
    cast(sale_date as date)                                  as sale_date,
    cast(product_price as decimal(12,2))                     as product_price,
    cast(premium_charged as decimal(12,2))                   as premium_charged,
    cast(remittance_amount as decimal(12,2))                 as remittance_amount,
    nullif(remittance_date, '')                              as remittance_date_raw,
    try_cast(nullif(remittance_date, '') as date)             as remittance_date,
    customer_email
from source
