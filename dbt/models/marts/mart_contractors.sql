-- Every prime contractor with work performed in the USVI: how much, for whom, and whether
-- the firm itself is based in the territory.
with t as (
    select *, coalesce(recipient_uei, recipient_name) as contractor_id
    from {{ ref('stg_transactions') }}
    where award_group = 'contracts'
),

latest as (
    select contractor_id, recipient_uei, recipient_name, recipient_parent_name, recipient_city,
           recipient_state, is_local_recipient, business_size, sba_8a, woman_owned, veteran_owned, hubzone
    from t
    qualify row_number() over (partition by contractor_id order by action_date desc, transaction_key desc) = 1
),

agency_rank as (
    select contractor_id, awarding_agency, sum(obligation) as amount,
           row_number() over (partition by contractor_id order by sum(obligation) desc) as rn
    from t group by contractor_id, awarding_agency
),

naics_rank as (
    select contractor_id, naics_code, any_value(naics_description) as naics_description,
           row_number() over (partition by contractor_id order by sum(obligation) desc) as rn
    from t where naics_code is not null group by contractor_id, naics_code
),

active as (
    select coalesce(recipient_uei, recipient_name) as contractor_id, count(*) as active_contracts
    from {{ ref('int_awards') }}
    where award_group = 'contracts' and current_end_date >= current_date
    group by all
),

totals as (
    select
        contractor_id,
        sum(obligation) as obligated_all_years,
        sum(obligation) filter (where {{ in_recent_fys('fiscal_year') }}) as obligated_recent,
        count(distinct award_key) as contracts,
        min(action_date) as first_action_date,
        max(action_date) as last_action_date
    from t
    group by contractor_id
)

select
    l.*,
    tot.obligated_all_years,
    coalesce(tot.obligated_recent, 0) as obligated_recent,
    tot.contracts,
    coalesce(a.active_contracts, 0) as active_contracts,
    tot.first_action_date,
    tot.last_action_date,
    ag.awarding_agency as main_agency,
    n.naics_code as main_naics_code,
    n.naics_description as main_naics_description
from latest l
join totals tot using (contractor_id)
left join active a using (contractor_id)
left join agency_rank ag on ag.contractor_id = l.contractor_id and ag.rn = 1
left join naics_rank n on n.contractor_id = l.contractor_id and n.rn = 1
