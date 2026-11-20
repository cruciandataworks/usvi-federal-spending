"""Step 2 - Subcontracts and subgrants performed in the U.S. Virgin Islands.

When a prime contractor or a grant recipient passes part of the work to another firm,
it must report the subaward if it is $30,000 or more (the FFATA rule). These reports show
which large companies already hire subcontractors here, and whom they hire - the most
direct lead list for a firm that wants to subcontract.

    python pipeline/step2_subawards.py

Subaward reports are small (a few hundred a year here) but are often filed or corrected
months late, so this step re-downloads the current and previous fiscal years every day,
and every year once a week. Each year's file is replaced, never appended to.
"""
import io
import sys
import zipfile
from concurrent.futures import ThreadPoolExecutor
from datetime import date

import pandas as pd

from common import (FIRST_FY, LAKE, USVI, bulk_download, fiscal_year, fy_bounds, load_state,
                    now_utc, record_health, save_state, write_parquet)

OUT = LAKE / "subawards"
REFRESH_DAYS = 7

# Our column name: the same column in both subaward files (contracts and assistance)
COLUMNS = {
    "subaward_key": "subaward_sam_report_id",
    "subaward_type": "subaward_type",
    "subaward_number": "subaward_number",
    "subaward_amount": "subaward_amount",
    "subaward_action_date": "subaward_action_date",
    "subawardee_uei": "subawardee_uei",
    "subawardee_name": "subawardee_name",
    "subawardee_parent_name": "subawardee_parent_name",
    "subawardee_city": "subawardee_city_name",
    "subawardee_state": "subawardee_state_code",
    "subawardee_business_types": "subawardee_business_types",
    "sub_pop_city": "subaward_primary_place_of_performance_city_name",
    "subaward_description": "subaward_description",
    "prime_award_key": "prime_award_unique_key",
    "prime_award_amount": "prime_award_amount",
    "prime_awardee_uei": "prime_awardee_uei",
    "prime_awardee_name": "prime_awardee_name",
    "prime_awardee_parent_name": "prime_awardee_parent_name",
    "prime_awardee_state": "prime_awardee_state_code",
    "prime_awarding_agency": "prime_award_awarding_agency_name",
    "prime_awarding_sub_agency": "prime_award_awarding_sub_agency_name",
    "prime_end_date": "prime_award_period_of_performance_current_end_date",
    "prime_naics_code": "prime_award_naics_code",
    "prime_naics_description": "prime_award_naics_description",
    "prime_description": "prime_award_base_transaction_description",
    "permalink": "usaspending_permalink",
    "last_modified_date": "subaward_sam_report_last_modified_date",
}
# only the subcontract file has these (a grant has no industry code)
CONTRACT_ONLY = {"prime_naics_code", "prime_naics_description"}


def read_zip(content: bytes) -> pd.DataFrame:
    frames = []
    with zipfile.ZipFile(io.BytesIO(content)) as z:
        for name in z.namelist():
            if name.endswith(".csv"):
                raw = pd.read_csv(z.open(name), dtype=str, keep_default_na=False, na_values=[""])
                df = pd.DataFrame({ours: raw[theirs] if theirs in raw else pd.NA
                                   for ours, theirs in COLUMNS.items()}, index=raw.index)
                df.insert(0, "kind", "subcontract" if "_Contracts_" in name else "subgrant")
                frames.append(df)
    if not frames:
        return pd.DataFrame(columns=["kind", *COLUMNS], dtype="string")
    return pd.concat(frames, ignore_index=True).astype("string")


def year(fy):
    start, end = fy_bounds(fy)
    df = read_zip(bulk_download({"sub_award_types": ["procurement", "grant"], "date_type": "action_date",
                                 "date_range": {"start_date": start, "end_date": end},
                                 "place_of_performance_locations": USVI}, f"subawards FY{fy}"))
    df["fiscal_year"] = fy
    write_parquet(df, OUT / f"fy={fy}.parquet")
    return len(df)


def main():
    state = load_state("subawards")
    today = now_utc().date()
    this_fy = fiscal_year(today)
    last = state.get("last_full_refresh")
    weekly = not last or (today - date.fromisoformat(last)).days >= REFRESH_DAYS
    years = list(range(FIRST_FY, this_fy + 1)) if weekly else [this_fy - 1, this_fy]
    try:
        with ThreadPoolExecutor(max_workers=2) as pool:
            counts = dict(zip(years, pool.map(year, years)))
        if weekly:
            state["last_full_refresh"] = today.isoformat()
        save_state("subawards", state)
        print(f"  {sum(counts.values()):,} subawards in FY{years[0]}-FY{years[-1]}"
              f"{' (weekly full refresh)' if weekly else ''}")
        record_health("usaspending_subawards", True, sum(counts.values()), detail=f"through {today}")
    except Exception as e:  # noqa: BLE001
        record_health("usaspending_subawards", False, error=str(e))
        print(f"  USAspending subawards failed: {e}", file=sys.stderr)
        raise SystemExit(1)


if __name__ == "__main__":
    main()
