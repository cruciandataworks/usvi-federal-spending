-- Who receives the money, over the last complete fiscal years.
select
    recipient_kind,
    award_group,
    sum(obligation) as obligations,
    count(distinct award_key) as awards
from {{ ref('stg_transactions') }}
where {{ in_recent_fys('fiscal_year') }}
group by all
