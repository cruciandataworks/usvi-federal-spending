"""Step 3 - USAspending's own yearly totals for the territory, kept as a check on ours.

The website's "Spending over time" chart for the Virgin Islands comes from the
spending_over_time endpoint. We save its figure for every fiscal year and award type.
A dbt test then adds up our own transactions the same way and fails if any year and
type differs by more than one dollar - proof that nothing was lost or counted twice.

    python pipeline/step3_official.py
"""
import sys

import pandas as pd

from common import FIRST_FY, LAKE, USVI, fiscal_year, fy_bounds, now_utc, post, record_health, write_parquet

OUT = LAKE / "official" / "spending_over_time.parquet"
TYPES = {"Contract": "contracts", "Grant": "grants", "Direct": "direct_payments",
         "Loan": "loans", "Other": "other"}


def main():
    this_fy = fiscal_year(now_utc().date())
    start, _ = fy_bounds(FIRST_FY)
    _, end = fy_bounds(this_fy)
    try:
        d = post("search/spending_over_time/", {"group": "fiscal_year", "filters": {
            "place_of_performance_locations": USVI, "time_period": [{"start_date": start, "end_date": end}]}})
        rows = [{"fiscal_year": int(r["time_period"]["fiscal_year"]), "award_group": group,
                 "obligations": float(r.get(f"{name}_Obligations") or 0)}
                for r in d["results"] for name, group in TYPES.items()]
        df = pd.DataFrame(rows)
        df["fetched_utc"] = now_utc().replace(microsecond=0, tzinfo=None)
        write_parquet(df, OUT)
        latest = df[df.fiscal_year == this_fy - 1].obligations.sum()
        print(f"  {df.fiscal_year.nunique()} fiscal years; FY{this_fy - 1} total ${latest:,.0f}")
        record_health("usaspending_official", True, len(df))
    except Exception as e:  # noqa: BLE001
        record_health("usaspending_official", False, error=str(e))
        print(f"  USAspending totals failed: {e}", file=sys.stderr)
        raise SystemExit(1)


if __name__ == "__main__":
    main()
