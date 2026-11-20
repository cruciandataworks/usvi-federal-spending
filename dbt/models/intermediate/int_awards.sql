-- One row per award: what was agreed at the start (first transaction), where it stands
-- now (latest transaction), and how much of it was obligated for work in the USVI.
with t as (
    select * from {{ ref('stg_transactions') }}
),

ordered as (
    select
        *,
        row_number() over (partition by award_key
                           order by action_date, last_modified_at nulls last, transaction_key) as first_rank,
        row_number() over (partition by award_key
                           order by action_date desc, last_modified_at desc nulls last, transaction_key desc) as latest_rank
    from t
),

totals as (
    select
        award_key,
        min(action_date) as first_action_date,
        max(action_date) as last_action_date,
        min(fiscal_year) as first_fiscal_year,
        sum(obligation) as obligated_in_usvi,
        count(*) as transactions,
        min(start_date) as start_date
    from t
    group by award_key
)

select
    l.award_key,
    l.award_id,
    l.parent_award_id,
    l.kind,
    l.award_group,
    l.award_type,
    l.awarding_agency,
    l.awarding_sub_agency,
    l.awarding_office,
    l.recipient_uei,
    l.recipient_name,
    l.recipient_parent_name,
    l.recipient_city,
    l.recipient_state,
    l.is_local_recipient,
    l.recipient_kind,
    l.island,
    l.naics_code,
    l.naics_description,
    l.psc_code,
    l.psc_description,
    l.cfda_number,
    l.cfda_title,
    coalesce(f.base_description, f.description, l.description) as description,
    -- how the contract was won is recorded on the first action
    f.set_aside,
    f.extent_competed,
    f.offers_received,
    f.solicitation_id,
    l.business_size,
    l.woman_owned,
    l.veteran_owned,
    l.minority_owned,
    l.sba_8a,
    l.hubzone,
    tot.first_action_date,
    tot.last_action_date,
    tot.first_fiscal_year,
    tot.start_date,
    l.current_end_date,
    l.potential_end_date,
    tot.obligated_in_usvi,
    tot.transactions,
    l.award_total_obligated,
    l.award_current_value,
    l.award_potential_value,
    l.permalink
from ordered l
join ordered f on f.award_key = l.award_key and f.first_rank = 1
join totals tot on tot.award_key = l.award_key
where l.latest_rank = 1
