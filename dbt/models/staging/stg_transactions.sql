-- One row per prime award transaction, with types, plain-English labels and a few
-- derived columns. All later models read this, never the raw table.
with src as (
    -- USAspending files a whole award under the type of its latest action (an award that
    -- began as a project grant and was later changed to a direct payment counts as a direct
    -- payment in every year). Doing the same here is what makes our totals match theirs.
    select
        *,
        award_type_code as transaction_type_code,
        first_value(award_type_code) over (
            partition by award_key
            order by action_date desc, last_modified_date desc nulls last, transaction_key desc
        ) as award_type_code_latest
    from {{ source('raw', 'transactions') }}
)

select
    transaction_key,
    transaction_type_code,
    award_key,
    award_id,
    parent_award_id,
    kind,
    case
        when award_type_code_latest in ('A', 'B', 'C', 'D') then 'contracts'
        when award_type_code_latest in ('02', '03', '04', '05', 'F001', 'F002') then 'grants'
        when award_type_code_latest in ('06', '10', 'F006', 'F007') then 'direct_payments'
        when award_type_code_latest in ('07', '08', 'F003', 'F004') then 'loans'
        else 'other'
    end as award_group,
    award_type_code_latest as award_type_code,
    -- USAspending's own labels changed over the years ("DO" and "DELIVERY ORDER"), so one
    -- label per code is set here
    case award_type_code_latest
        when 'A' then 'BPA call' when 'B' then 'Purchase order'
        when 'C' then 'Delivery order' when 'D' then 'Definitive contract'
        when '02' then 'Block grant' when '03' then 'Formula grant'
        when '04' then 'Project grant' when '05' then 'Cooperative agreement'
        when '06' then 'Direct payment for a specified use' when '10' then 'Direct payment, unrestricted'
        when '07' then 'Direct loan' when '08' then 'Guaranteed or insured loan'
        when '09' then 'Insurance'
        when 'F001' then 'Grant' when 'F002' then 'Cooperative agreement'
        when 'F003' then 'Direct loan' when 'F004' then 'Loan guarantee'
        when 'F005' then 'Indemnity or insurance' when 'F006' then 'Direct payment for a specified use'
        when 'F007' then 'Direct payment, unrestricted' when 'F008' then 'Asset forfeiture or equitable sharing'
        when 'F009' then 'Sale, exchange or donation of property' else 'Other financial assistance'
    end as award_type,
    cast(action_date as date) as action_date,
    cast(fiscal_year as integer) as fiscal_year,
    action_type,
    modification_number,
    -- what USAspending counts as spending: the obligation, or for a loan its subsidy cost
    coalesce(try_cast(obligation as double), 0) as obligation,
    try_cast(face_value_of_loan as double) as face_value_of_loan,
    try_cast(award_total_obligated as double) as award_total_obligated,
    try_cast(award_current_value as double) as award_current_value,
    try_cast(award_potential_value as double) as award_potential_value,
    try_cast(start_date as date) as start_date,
    try_cast(current_end_date as date) as current_end_date,
    try_cast(potential_end_date as date) as potential_end_date,
    awarding_agency_code,
    awarding_agency,
    awarding_sub_agency,
    awarding_office,
    funding_agency,
    recipient_uei,
    recipient_name,
    recipient_parent_uei,
    recipient_parent_name,
    recipient_city,
    recipient_state,
    recipient_country,
    -- "local" = the recipient's own address is in the Virgin Islands
    coalesce(recipient_state = 'VI', false) as is_local_recipient,
    case
        when recipient_name in ('MULTIPLE RECIPIENTS', 'REDACTED DUE TO PII')
          or business_types like 'INDIVIDUAL%' then 'Individuals'
        when kind = 'contract' then 'Businesses'
        when business_types similar to '.*(STATE GOVERNMENT|U.S. TERRITORY|CITY OR TOWNSHIP|SPECIAL DISTRICT|COUNTY GOVERNMENT|STATE CONTROLLED INSTITUTION).*'
          or recipient_name like '%GOVERNMENT OF THE VIRGIN ISLANDS%'
          or recipient_name like 'VIRGIN ISLANDS DEPARTMENT%' then 'Territorial government'
        when business_types similar to '.*(NONPROFIT|HIGHER EDUCATION|PRIVATE INSTITUTION).*' then 'Nonprofits and colleges'
        when business_types similar to '.*(SMALL BUSINESS|FOR-PROFIT).*' then 'Businesses'
        else 'Other and not stated'
    end as recipient_kind,
    pop_state_fips,
    case
        when upper(pop_county) like '%CROIX%' then 'St. Croix'
        when upper(pop_county) like '%JOHN%' then 'St. John'
        when upper(pop_county) like '%THOMAS%' then 'St. Thomas'
        else 'Territory-wide or not stated'
    end as island,
    upper(pop_city) as pop_city,
    naics_code,
    naics_description,
    psc_code,
    psc_description,
    cfda_number,
    cfda_title,
    description,
    base_description,
    def_codes,
    set_aside,
    extent_competed,
    try_cast(try_cast(offers_received as double) as integer) as offers_received,
    business_size,
    solicitation_id,
    business_types,
    woman_owned = 't' as woman_owned,
    veteran_owned = 't' as veteran_owned,
    minority_owned = 't' as minority_owned,
    sba_8a = 't' as sba_8a,
    hubzone = 't' as hubzone,
    permalink,
    try_cast(last_modified_date as timestamp) as last_modified_at
from src
