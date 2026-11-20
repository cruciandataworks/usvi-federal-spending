-- Every lead ends between today and the horizon and is worth at least the minimum.
select award_key, current_end_date, contract_value
from {{ ref('mart_contract_leads') }}
where current_end_date < current_date
   or current_end_date >= current_date + interval {{ var('lead_horizon_months') }} month
   or contract_value < {{ var('lead_min_value') }}
