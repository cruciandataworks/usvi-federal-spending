-- Contract dollars by fiscal year: to firms based in the Virgin Islands, or elsewhere.
select
    fiscal_year,
    sum(obligation) as contract_obligations,
    sum(obligation) filter (where is_local_recipient) as local_obligations,
    sum(obligation) filter (where not is_local_recipient) as off_island_obligations,
    count(distinct coalesce(recipient_uei, recipient_name)) filter (where is_local_recipient) as local_contractors,
    count(distinct coalesce(recipient_uei, recipient_name)) filter (where not is_local_recipient) as off_island_contractors
from {{ ref('stg_transactions') }}
where award_group = 'contracts'
group by fiscal_year
