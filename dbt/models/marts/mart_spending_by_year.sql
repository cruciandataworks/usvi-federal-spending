-- Obligations by fiscal year and award type: the chart at the top of the dashboard.
select
    fiscal_year,
    award_group,
    sum(obligation) as obligations,
    count(*) as transactions,
    count(distinct award_key) as awards,
    fiscal_year = {{ current_fy() }} as is_current_year
from {{ ref('stg_transactions') }}
group by fiscal_year, award_group
