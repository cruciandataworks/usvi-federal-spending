-- Our totals, added up from individual transactions, must equal USAspending's own figure
-- for every fiscal year that closed more than a year ago, to within a dollar.
select * from {{ ref('mart_reconciliation') }}
where not matches and fiscal_year <= {{ current_fy() }} - 2
