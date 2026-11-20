-- Rolling transactions up to awards must not lose or double a cent.
select a.total as awards_total, t.total as transactions_total
from (select sum(obligated_in_usvi) as total from {{ ref('int_awards') }}) a,
     (select sum(obligation) as total from {{ ref('stg_transactions') }}) t
where abs(a.total - t.total) > 0.01
