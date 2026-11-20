select
    cast(fiscal_year as integer) as fiscal_year,
    award_group,
    cast(obligations as double) as obligations,
    fetched_utc
from {{ source('raw', 'official_totals') }}
