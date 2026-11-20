-- Everything that needs attention right now, one row per alert. Step 6 keeps exactly one
-- GitHub issue open per alert_key and closes it when the row disappears.
with new_contracts as (
    select
        'new-contracts' as alert_key,
        'opportunity' as category,
        'info' as severity,
        count(*) || ' new USVI contract' || case when count(*) > 1 then 's' else '' end
            || ' of $' || format('{:,}', cast(round({{ var('new_award_alert_min') }}) as bigint)) || '+ in the last '
            || {{ var('new_award_days') }} || ' days' as title,
        string_agg(
            '- ' || recipient_name || ' (' || coalesce(recipient_state, '?') || '): $'
            || format('{:,}', cast(round(contract_value) as bigint)) || ' from ' || awarding_sub_agency
            || ', first action ' || strftime(first_action_date, '%Y-%m-%d') || '. '
            || coalesce(description, '') || ' ' || coalesce(permalink, ''),
            chr(10) order by contract_value desc) as message,
        current_timestamp as observed_at
    from {{ ref('mart_new_contracts') }}
    having count(*) > 0
),

reconcile as (
    select
        'reconcile' as alert_key,
        'data-quality' as category,
        'warning' as severity,
        'Totals differ from USAspending in ' || count(*) || ' year/type combination(s)' as title,
        string_agg('- FY' || fiscal_year || ' ' || award_group || ': ours $' || format('{:,.2f}', ours)
                   || ', USAspending $' || format('{:,.2f}', official), chr(10)) as message,
        current_timestamp as observed_at
    from {{ ref('mart_reconciliation') }}
    where not matches
    having count(*) > 0
),

collectors as (
    select
        'collector:' || source as alert_key,
        'pipeline' as category,
        'warning' as severity,
        source || ' has failed ' || consecutive_failures || ' runs in a row' as title,
        'Last success: ' || coalesce(strftime(last_success_utc, '%Y-%m-%d %H:%M UTC'), 'never')
            || '. Last error: ' || coalesce(last_error, '') as message,
        current_timestamp as observed_at
    from {{ ref('stg_source_health') }}
    where consecutive_failures >= {{ var('max_consecutive_failures') }}
)

select * from new_contracts
union all select * from reconcile
union all select * from collectors
