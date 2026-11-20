"""Step 5 - Export: write the small files the static dashboard reads.

    dashboard/data/summary.json      every number, chart and table on the page
    dashboard/data/leads.csv         the lead list, for opening in Excel
    dashboard/data/contractors.csv   every prime contractor with USVI work

The dashboard never talks to the warehouse or the API, so it can be hosted anywhere as
plain files.
"""
import json
import math
from datetime import date, datetime

import duckdb

from common import ROOT

DB = ROOT / "warehouse" / "spending.duckdb"
OUT = ROOT / "dashboard" / "data"


def clean(v):
    if isinstance(v, float):
        return None if math.isnan(v) else round(v, 2)
    if isinstance(v, (date, datetime)):
        return v.isoformat()[:10] if isinstance(v, date) and not isinstance(v, datetime) else v.isoformat(timespec="minutes")
    return v


def rows(con, sql):
    rel = con.sql(sql)
    return [{k: clean(v) for k, v in zip(rel.columns, r)} for r in rel.fetchall()]


def one(con, sql):
    return rows(con, sql)[0]


def main():
    con = duckdb.connect(str(DB), read_only=True)
    fy = one(con, "select (year(current_date) + case when month(current_date) >= 10 then 1 else 0 end) as fy")["fy"]
    recent = (fy - 5, fy - 1)

    meta = one(con, f"""
        select current_timestamp at time zone 'UTC' as generated_utc,
               max(action_date) as latest_action_date,
               max(last_modified_at) as latest_modified,
               min(fiscal_year) as first_fy,
               {fy} as current_fy, {recent[0]} as recent_from_fy, {recent[1]} as recent_to_fy,
               count(*) as transactions,
               count(distinct award_key) as awards
        from staging.stg_transactions""")
    meta["contractors"] = one(con, "select count(*) n from marts.mart_contractors")["n"]
    meta["subawards"] = one(con, "select count(*) n from staging.stg_subawards")["n"]

    years = rows(con, "select fiscal_year, award_group, obligations, awards from marts.mart_spending_by_year order by 1, 2")
    recon = rows(con, "select * from marts.mart_reconciliation order by fiscal_year, award_group")

    kpis = one(con, f"""
        select
          sum(obligations) filter (where fiscal_year = {fy - 1}) as last_fy_total,
          sum(obligations) filter (where fiscal_year between {recent[0]} and {recent[1]}) as recent_total,
          sum(obligations) filter (where fiscal_year between {recent[0]} and {recent[1]} and award_group = 'contracts') as recent_contracts,
          sum(obligations) filter (where fiscal_year between {recent[0]} and {recent[1]} and award_group = 'grants') as recent_grants,
          sum(obligations) as all_years_total
        from marts.mart_spending_by_year""")
    kpis.update(one(con, f"""
        select sum(local_obligations) / nullif(sum(contract_obligations), 0) as recent_local_share,
               sum(off_island_obligations) as recent_off_island
        from marts.mart_local_share where fiscal_year between {recent[0]} and {recent[1]}"""))
    kpis.update(one(con, """select count(*) as leads, sum(contract_value) as leads_value,
                                   count(*) filter (where not prime_is_local) as leads_off_island
                            from marts.mart_contract_leads"""))
    kpis["matched_years"] = sum(1 for r in recon if r["matches"])
    kpis["checked_years"] = len(recon)

    data = {
        "meta": meta,
        "kpis": kpis,
        "years": years,
        "reconciliation": recon,
        "local_share": rows(con, "select * from marts.mart_local_share order by fiscal_year"),
        "agencies": rows(con, "select * from marts.mart_agencies where obligations > 0 order by obligations desc limit 15"),
        "recipient_kinds": rows(con, """select recipient_kind, sum(obligations) as obligations
                                        from marts.mart_recipient_kinds group by 1 order by 2 desc"""),
        "naics": rows(con, """select naics_code, naics_description, obligations, contracts, contractors,
                                     coalesce(local_obligations, 0) as local_obligations
                              from marts.mart_naics_demand where obligations > 0
                              order by obligations desc limit 15"""),
        "contractors": rows(con, """select recipient_name, recipient_city, recipient_state, is_local_recipient,
                                           business_size, sba_8a, woman_owned, veteran_owned, hubzone,
                                           obligated_recent, obligated_all_years, contracts, active_contracts,
                                           last_action_date, main_agency, main_naics_description
                                    from marts.mart_contractors
                                    order by obligated_recent desc, obligated_all_years desc limit 150"""),
        "leads": rows(con, """select award_id, awarding_agency, awarding_sub_agency, awarding_office,
                                     prime_contractor, prime_city, prime_state, prime_is_local, business_size,
                                     island, naics_code, naics_description, psc_description, description,
                                     set_aside, extent_competed, offers_received, start_date, current_end_date,
                                     potential_end_date, months_left, ends_in, has_options_left,
                                     contract_value, obligated_in_usvi, permalink
                              from marts.mart_contract_leads order by current_end_date, contract_value desc"""),
        "subcontracting": rows(con, """select * from marts.mart_subcontracting
                                       qualify row_number() over (partition by kind order by subaward_amount desc) <= 25
                                       order by kind, subaward_amount desc"""),
        "recent_subawards": rows(con, """select kind, subawardee_name, subawardee_city, subawardee_state,
                                                is_local_subawardee, subaward_amount, subaward_action_date,
                                                prime_awardee_name, prime_awarding_sub_agency, subaward_description
                                         from staging.stg_subawards
                                         order by subaward_action_date desc nulls last, subaward_amount desc limit 60"""),
        "new_contracts": rows(con, "select * from marts.mart_new_contracts order by first_action_date desc"),
        "alerts": rows(con, "select alert_key, category, severity, title, message, observed_at from marts.mart_alerts"),
        "health": rows(con, "select * from staging.stg_source_health order by source"),
    }
    OUT.mkdir(parents=True, exist_ok=True)
    f = OUT / "summary.json"
    f.write_text(json.dumps(data, separators=(",", ":"), default=str))
    print(f"  wrote {f.relative_to(ROOT)} ({f.stat().st_size // 1024} KB)")

    for name, sql in {
        "leads.csv": "select * exclude (award_key) from marts.mart_contract_leads order by current_end_date",
        "contractors.csv": "select * exclude (contractor_id) from marts.mart_contractors order by obligated_recent desc",
    }.items():
        path = OUT / name
        con.execute(f"copy ({sql}) to '{path}' (header, delimiter ',')")
        print(f"  wrote {path.relative_to(ROOT)} ({path.stat().st_size // 1024} KB)")


if __name__ == "__main__":
    main()
