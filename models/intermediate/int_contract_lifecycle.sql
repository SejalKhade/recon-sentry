-- Joins each contract to its originating merchant sale (if any).
-- One row per contract. sale_* fields are null when the contract is orphaned.

with contracts as (
    select * from {{ ref('stg_contracts') }}
),
sales as (
    select * from {{ ref('stg_merchant_sales') }}
)

select
    c.contract_id,
    c.sale_id                            as contract_sale_id,
    c.merchant_id                        as contract_merchant_id,
    c.issued_date,
    c.premium                            as contract_premium,
    c.coverage_limit,
    c.term_months,
    c.status                             as contract_status,

    s.sale_id                            as matched_sale_id,
    s.merchant_id                        as sale_merchant_id,
    s.sale_date,
    s.product_price,
    s.premium_charged                    as sale_premium_charged,
    s.remittance_amount                  as sale_remittance_amount,
    s.remittance_date                    as sale_remittance_date,

    case when s.sale_id is null then true else false end        as is_orphan_contract,
    case
        when s.sale_id is null then null
        when s.remittance_date is null then true
        else false
    end                                                          as is_unpaid,
    case
        when s.sale_id is null then null
        when abs(coalesce(s.remittance_amount, 0) - c.premium) > 0.01 then true
        else false
    end                                                          as has_amount_break
from contracts c
left join sales s on c.sale_id = s.sale_id
