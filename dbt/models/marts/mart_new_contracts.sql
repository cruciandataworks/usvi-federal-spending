-- Contracts performed in the USVI whose first action is recent: a new piece of work, a new
-- prime contractor in town, and possibly a new subcontracting opening.
select
    award_key, award_id, awarding_agency, awarding_sub_agency, recipient_name, recipient_state,
    is_local_recipient, naics_description, description, first_action_date, current_end_date,
    greatest(coalesce(award_current_value, 0), coalesce(award_total_obligated, 0), obligated_in_usvi) as contract_value,
    permalink
from {{ ref('int_awards') }}
where award_group = 'contracts'
  and first_action_date >= current_date - {{ var('new_award_days') }}
  and greatest(coalesce(award_current_value, 0), coalesce(award_total_obligated, 0), obligated_in_usvi)
      >= {{ var('new_award_alert_min') }}
