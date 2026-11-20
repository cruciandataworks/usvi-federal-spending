-- Which federal departments spend in the territory, over the last complete fiscal years.
with t as (
    select * from {{ ref('stg_transactions') }}
    where {{ in_recent_fys('fiscal_year') }}
),

by_sub as (
    select awarding_agency, awarding_sub_agency, sum(obligation) as obligations,
           row_number() over (partition by awarding_agency order by sum(obligation) desc) as rn
    from t
    group by awarding_agency, awarding_sub_agency
)

select
    t.awarding_agency as agency,
    sum(t.obligation) as obligations,
    sum(t.obligation) filter (where award_group = 'contracts') as contracts,
    sum(t.obligation) filter (where award_group = 'grants') as grants,
    sum(t.obligation) filter (where award_group not in ('contracts', 'grants')) as other_assistance,
    count(distinct t.award_key) as awards,
    count(distinct t.award_key) filter (where award_group = 'contracts') as contract_awards,
    any_value(s.awarding_sub_agency) as largest_sub_agency,
    min(t.fiscal_year) as from_fy,
    max(t.fiscal_year) as to_fy
from t
left join by_sub s on s.awarding_agency = t.awarding_agency and s.rn = 1
group by t.awarding_agency
