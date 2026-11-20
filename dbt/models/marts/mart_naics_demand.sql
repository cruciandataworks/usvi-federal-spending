-- What the government buys here: contract obligations by industry (NAICS), recent years.
with t as (
    select * from {{ ref('stg_transactions') }}
    where award_group = 'contracts' and {{ in_recent_fys('fiscal_year') }} and naics_code is not null
)

select
    naics_code,
    any_value(naics_description) as naics_description,
    left(naics_code, 2) as sector_code,
    sum(obligation) as obligations,
    count(distinct award_key) as contracts,
    count(distinct coalesce(recipient_uei, recipient_name)) as contractors,
    sum(obligation) filter (where is_local_recipient) as local_obligations
from t
group by naics_code
