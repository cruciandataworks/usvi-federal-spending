-- Prime contractors and grantees that already pass work to subawardees in the USVI, and
-- how much of it goes to firms based here. One row per prime and kind (subcontract or
-- subgrant). The most direct list of whom to call.
with s as (
    select * from {{ ref('stg_subawards') }}
),

by_prime as (
    select
        prime_awardee_name as prime,
        kind,
        any_value(prime_awardee_state) as prime_state,
        any_value(prime_awarding_agency) as agency,
        count(*) as subawards,
        count(distinct subawardee_name) as subawardees,
        sum(subaward_amount) as subaward_amount,
        coalesce(sum(subaward_amount) filter (where is_local_subawardee), 0) as to_local_firms,
        max(subaward_action_date) as last_subaward_date,
        max(prime_end_date) as latest_prime_end_date
    from s
    group by prime_awardee_name, kind
),

top_subs as (
    select prime, kind, string_agg(subawardee_name, '; ' order by amount desc) as top_subawardees
    from (
        select prime_awardee_name as prime, kind, subawardee_name, sum(subaward_amount) as amount,
               row_number() over (partition by prime_awardee_name, kind order by sum(subaward_amount) desc) as rn
        from s group by prime_awardee_name, kind, subawardee_name
    )
    where rn <= 3
    group by prime, kind
)

select p.*, t.top_subawardees
from by_prime p
left join top_subs t using (prime, kind)
