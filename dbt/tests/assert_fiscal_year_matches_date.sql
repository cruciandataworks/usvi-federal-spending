-- The fiscal year stored with each transaction must agree with its action date
-- (1 October starts the next fiscal year).
select transaction_key, action_date, fiscal_year
from {{ ref('stg_transactions') }}
where fiscal_year <> {{ fiscal_year_of('action_date') }}
