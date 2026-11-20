-- Our yearly totals beside USAspending's own. If these differ, a record was lost,
-- counted twice, or counted in the wrong year.
with ours as (
    select fiscal_year, award_group, sum(obligations) as ours
    from {{ ref('mart_spending_by_year') }}
    group by all
),

theirs as (
    select fiscal_year, award_group, obligations as official
    from {{ ref('stg_official_totals') }}
)

select
    coalesce(o.fiscal_year, t.fiscal_year) as fiscal_year,
    coalesce(o.award_group, t.award_group) as award_group,
    coalesce(o.ours, 0) as ours,
    coalesce(t.official, 0) as official,
    round(coalesce(o.ours, 0) - coalesce(t.official, 0), 2) as difference,
    abs(coalesce(o.ours, 0) - coalesce(t.official, 0)) <= {{ var('reconcile_tolerance_usd') }} as matches
from ours o
full join theirs t on t.fiscal_year = o.fiscal_year and t.award_group = o.award_group
