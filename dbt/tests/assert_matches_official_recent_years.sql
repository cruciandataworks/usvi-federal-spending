-- The same check for this year and last year. Agencies are still reporting these, and our
-- download and USAspending's total are taken minutes apart, so a difference here is a
-- warning (and an alert) rather than a failed build.
{{ config(severity = 'warn') }}
select * from {{ ref('mart_reconciliation') }}
where not matches and fiscal_year >= {{ current_fy() }} - 1
