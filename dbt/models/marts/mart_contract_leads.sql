-- The lead list: contracts performed in the USVI whose current end date falls within the
-- next 24 months. When a contract ends, the agency usually buys the work again (a
-- "recompete"), and the prime that wins it often needs local subcontractors.
select
    award_key,
    award_id,
    parent_award_id,
    awarding_agency,
    awarding_sub_agency,
    awarding_office,
    recipient_name as prime_contractor,
    recipient_uei as prime_uei,
    recipient_city as prime_city,
    recipient_state as prime_state,
    is_local_recipient as prime_is_local,
    business_size,
    island,
    naics_code,
    naics_description,
    psc_code,
    psc_description,
    description,
    set_aside,
    extent_competed,
    offers_received,
    start_date,
    current_end_date,
    potential_end_date,
    date_diff('month', current_date, current_end_date) as months_left,
    case
        when current_end_date < current_date + interval 6 month then 'Within 6 months'
        when current_end_date < current_date + interval 12 month then '6 to 12 months'
        else '12 to 24 months'
    end as ends_in,
    -- potential end later than current end: the agency can still extend with options
    coalesce(potential_end_date > current_end_date, false) as has_options_left,
    obligated_in_usvi,
    greatest(coalesce(award_current_value, 0), coalesce(award_total_obligated, 0), obligated_in_usvi) as contract_value,
    permalink
from {{ ref('int_awards') }}
where award_group = 'contracts'
  and current_end_date >= current_date
  and current_end_date < current_date + interval {{ var('lead_horizon_months') }} month
  and greatest(coalesce(award_current_value, 0), coalesce(award_total_obligated, 0), obligated_in_usvi)
      >= {{ var('lead_min_value') }}
