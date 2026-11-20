-- Every transaction must carry an award type code we know. USAspending replaced the
-- assistance codes 02-11 with F001-F010 in October 2026; a code we do not list would
-- land in "other" and the reconciliation would fail with no clue why. This test names it.
select award_type_code, count(*) as transactions
from {{ ref('stg_transactions') }}
where award_type_code not in (
    'A', 'B', 'C', 'D',
    '02', '03', '04', '05', '06', '07', '08', '09', '10', '11', '-1',
    'F001', 'F002', 'F003', 'F004', 'F005', 'F006', 'F007', 'F008', 'F009', 'F010'
)
group by 1
