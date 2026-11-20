"""Step 1 - Prime award transactions performed in the U.S. Virgin Islands.

A "transaction" is one action on a federal award: the first obligation, a modification
that adds money, or a de-obligation that takes some back (a negative amount). Adding up
transactions by action date gives spending by year - the same way USAspending does.

    python pipeline/step1_transactions.py            # what the daily schedule runs
    python pipeline/step1_transactions.py --full 2025  # re-download one fiscal year

How it loads only what is new
-----------------------------
1. Backfill (first runs only): one download per fiscal year, FY2008 to today. Each
   finished year is noted in lake/_state/transactions.json, so if a run stops halfway
   the next run carries on where it left off.
2. Daily: ask only for transactions *modified* since the last successful run (minus
   3 days, in case USAspending loaded something late). They are merged into the right
   year's file on their unique key, so a corrected record replaces the old copy.
3. Weekly: the current and previous fiscal years are downloaded again in full and
   replace their files. That picks up the rare record USAspending deletes, which an
   "only what changed" request can never show.
"""
import argparse
import io
import sys
import zipfile
from concurrent.futures import ThreadPoolExecutor
from datetime import date, timedelta

import pandas as pd

from common import (ALL_PRIME_TYPES, FIRST_FY, LAKE, USVI, bulk_download, fiscal_year,
                    fy_bounds, load_state, now_utc, record_health, save_state, upsert,
                    write_parquet)

OUT = LAKE / "transactions"
KEY = ["transaction_key"]
REFRESH_DAYS = 7

# Our column name: (column in the contracts file, column in the assistance file).
# None means the file has no such column. Everything is kept as text here; dbt sets types.
COLUMNS = {
    "transaction_key": ("contract_transaction_unique_key", "assistance_transaction_unique_key"),
    "award_key": ("contract_award_unique_key", "assistance_award_unique_key"),
    "award_id": ("award_id_piid", "award_id_fain"),
    "parent_award_id": ("parent_award_id_piid", None),
    "modification_number": ("modification_number", "modification_number"),
    "action_date": ("action_date", "action_date"),
    "action_type": ("action_type", "action_type_description"),
    "award_type_code": ("award_type_code", "assistance_type_code"),
    "award_type": ("award_type", "assistance_type_description"),
    "record_type_code": (None, "record_type_code"),
    "federal_action_obligation": ("federal_action_obligation", "federal_action_obligation"),
    "obligation": ("federal_action_obligation", "generated_pragmatic_obligations"),
    "face_value_of_loan": (None, "face_value_of_loan"),
    "award_total_obligated": ("total_dollars_obligated", "total_obligated_amount"),
    "award_current_value": ("current_total_value_of_award", None),
    "award_potential_value": ("potential_total_value_of_award", None),
    "start_date": ("period_of_performance_start_date", "period_of_performance_start_date"),
    "current_end_date": ("period_of_performance_current_end_date", "period_of_performance_current_end_date"),
    "potential_end_date": ("period_of_performance_potential_end_date", None),
    "awarding_agency_code": ("awarding_agency_code", "awarding_agency_code"),
    "awarding_agency": ("awarding_agency_name", "awarding_agency_name"),
    "awarding_sub_agency": ("awarding_sub_agency_name", "awarding_sub_agency_name"),
    "awarding_office": ("awarding_office_name", "awarding_office_name"),
    "funding_agency": ("funding_agency_name", "funding_agency_name"),
    "recipient_uei": ("recipient_uei", "recipient_uei"),
    "recipient_name": ("recipient_name", "recipient_name"),
    "recipient_parent_uei": ("recipient_parent_uei", "recipient_parent_uei"),
    "recipient_parent_name": ("recipient_parent_name", "recipient_parent_name"),
    "recipient_city": ("recipient_city_name", "recipient_city_name"),
    "recipient_state": ("recipient_state_code", "recipient_state_code"),
    "recipient_country": ("recipient_country_code", "recipient_country_code"),
    "pop_state_fips": ("prime_award_transaction_place_of_performance_state_fips_code",
                       "prime_award_transaction_place_of_performance_state_fips_code"),
    "pop_city": ("primary_place_of_performance_city_name", "primary_place_of_performance_city_name"),
    "pop_county": ("primary_place_of_performance_county_name", "primary_place_of_performance_county_name"),
    "pop_zip": ("primary_place_of_performance_zip_4", "primary_place_of_performance_zip_4"),
    "naics_code": ("naics_code", None),
    "naics_description": ("naics_description", None),
    "psc_code": ("product_or_service_code", None),
    "psc_description": ("product_or_service_code_description", None),
    "cfda_number": (None, "cfda_number"),
    "cfda_title": (None, "cfda_title"),
    "description": ("transaction_description", "transaction_description"),
    "base_description": ("prime_award_base_transaction_description", "prime_award_base_transaction_description"),
    "def_codes": ("disaster_emergency_fund_codes_for_overall_award", "disaster_emergency_fund_codes_for_overall_award"),
    "set_aside": ("type_of_set_aside", None),
    "extent_competed": ("extent_competed", None),
    "offers_received": ("number_of_offers_received", None),
    "business_size": ("contracting_officers_determination_of_business_size", None),
    "solicitation_id": ("solicitation_identifier", None),
    "business_types": (None, "business_types_description"),
    "woman_owned": ("woman_owned_business", None),
    "veteran_owned": ("veteran_owned_business", None),
    "minority_owned": ("minority_owned_business", None),
    "sba_8a": ("c8a_program_participant", None),
    "hubzone": ("historically_underutilized_business_zone_hubzone_firm", None),
    "permalink": ("usaspending_permalink", "usaspending_permalink"),
    "last_modified_date": ("last_modified_date", "last_modified_date"),
}


def read_zip(content: bytes) -> pd.DataFrame:
    """Read every CSV in a bulk download into one table with our column names."""
    frames = []
    with zipfile.ZipFile(io.BytesIO(content)) as z:
        for name in z.namelist():
            if not name.endswith(".csv"):
                continue
            kind = "contract" if "_Contracts_" in name else "assistance"
            raw = pd.read_csv(z.open(name), dtype=str, keep_default_na=False, na_values=[""])
            i = 0 if kind == "contract" else 1
            df = pd.DataFrame({ours: raw[cols[i]] if cols[i] else pd.NA for ours, cols in COLUMNS.items()},
                              index=raw.index)
            df.insert(0, "kind", kind)
            frames.append(df)
    if not frames:
        return pd.DataFrame(columns=["kind", *COLUMNS])
    df = pd.concat(frames, ignore_index=True).astype("string")
    df["fiscal_year"] = df["action_date"].map(lambda d: fiscal_year(date.fromisoformat(d[:10]))).astype("Int64")
    return df


def filters(start, end, date_type="action_date"):
    return {"prime_award_types": ALL_PRIME_TYPES, "date_type": date_type,
            "date_range": {"start_date": start, "end_date": end},
            "place_of_performance_locations": USVI}


def save_year(fy, df, replace):
    path = OUT / f"fy={fy}.parquet"
    part = df[df.fiscal_year == fy]
    if replace:
        write_parquet(part, path)
        return len(part)
    return upsert(path, part, KEY)


def full_year(fy):
    start, end = fy_bounds(fy)
    df = read_zip(bulk_download(filters(start, end), f"FY{fy}"))
    return save_year(fy, df, replace=True)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--full", type=int, help="re-download one fiscal year in full")
    args = ap.parse_args()
    state = load_state("transactions")
    today = now_utc().date()
    this_fy = fiscal_year(today)
    rows = 0
    try:
        if args.full:
            print(f"  FY{args.full}: {full_year(args.full):,} transactions")
            return

        # 1. Backfill any fiscal year not yet downloaded. The start date of the backfill is
        #    remembered so step 2 later asks for everything modified since then.
        done = set(state.get("years_done", []))
        state.setdefault("modified_since", today.isoformat())
        todo = [fy for fy in range(FIRST_FY, this_fy + 1) if fy not in done]
        # USAspending builds downloads in parallel, so ask for two years at a time
        with ThreadPoolExecutor(max_workers=2) as pool:
            for fy, n in zip(todo, pool.map(full_year, todo)):
                rows += n
                done.add(fy)
                state["years_done"] = sorted(done)
                save_state("transactions", state)
                print(f"  FY{fy}: {n:,} transactions", flush=True)

        # 2. Only what changed since the last run (3 days of overlap).
        since = (date.fromisoformat(state["modified_since"]) - timedelta(days=3)).isoformat()
        df = read_zip(bulk_download(filters(since, today.isoformat(), "last_modified_date"),
                                    f"modified since {since}"))
        new = sum(save_year(int(fy), df, replace=False) for fy in df.fiscal_year.dropna().unique())
        print(f"  {len(df):,} transactions modified since {since}; {new:,} of them new")
        rows += len(df)
        state["modified_since"] = today.isoformat()

        # 3. Weekly: replace the two most recent fiscal years in full.
        last = state.get("last_full_refresh")
        if not last or (today - date.fromisoformat(last)).days >= REFRESH_DAYS:
            for fy in (this_fy - 1, this_fy):
                print(f"  weekly refresh FY{fy}: {full_year(fy):,} transactions", flush=True)
            state["last_full_refresh"] = today.isoformat()

        save_state("transactions", state)
        record_health("usaspending_transactions", True, rows, detail=f"through {today}")
    except Exception as e:  # noqa: BLE001 - recorded, then the run stops
        save_state("transactions", state)
        record_health("usaspending_transactions", False, error=str(e))
        print(f"  USAspending transactions failed: {e}", file=sys.stderr)
        raise SystemExit(1)


if __name__ == "__main__":
    main()
