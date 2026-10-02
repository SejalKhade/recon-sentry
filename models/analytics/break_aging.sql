-- Break aging by category. This is the exact view an accounting or ops
-- lead would look at first thing in the morning.

with breaks as (
    select * from {{ ref('fct_recon_breaks') }}
)

select
    break_type,
    severity,
    case
        when days_open <= 7  then '0-7 days'
        when days_open <= 30 then '8-30 days'
        when days_open <= 60 then '31-60 days'
        else '60+ days'
    end                                                as aging_bucket,
    count(*)                                           as break_count,
    round(sum(amount_at_risk), 2)                      as total_amount_at_risk,
    round(avg(days_open), 1)                           as avg_days_open,
    max(days_open)                                     as max_days_open
from breaks
group by 1, 2, 3
order by
    case severity when 'high' then 1 when 'medium' then 2 else 3 end,
    break_type,
    aging_bucket
