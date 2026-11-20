-- Every transaction must be performed in the Virgin Islands (state FIPS code 78).
select transaction_key, pop_state_fips
from {{ ref('stg_transactions') }}
where pop_state_fips is not null and pop_state_fips <> '78'
