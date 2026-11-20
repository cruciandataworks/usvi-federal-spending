"""Step 4 - Load: copy the lake into one DuckDB warehouse, in a "raw" schema dbt reads.

    raw.transactions     every prime award transaction performed in the USVI (step 1)
    raw.subawards        subcontracts and subgrants performed in the USVI (step 2)
    raw.official_totals  USAspending's own yearly totals (step 3)
    raw.source_health    when each collector last worked

Nothing is changed here; all the logic lives in dbt, where it is tested.
"""
import json

import duckdb
import pandas as pd

from common import LAKE, ROOT, STATE

DB = ROOT / "warehouse" / "spending.duckdb"


def main():
    DB.parent.mkdir(exist_ok=True)
    con = duckdb.connect(str(DB))
    con.execute("create schema if not exists raw")
    tables = {
        "transactions": f"read_parquet('{LAKE / 'transactions' / 'fy=*.parquet'}', union_by_name = true)",
        "subawards": f"read_parquet('{LAKE / 'subawards' / 'fy=*.parquet'}', union_by_name = true)",
        "official_totals": f"read_parquet('{LAKE / 'official' / 'spending_over_time.parquet'}')",
    }
    for table, source in tables.items():
        con.execute(f"create or replace table raw.{table} as select * from {source}")
        n = con.execute(f"select count(*) from raw.{table}").fetchall()[0][0]
        print(f"  raw.{table:<16} {n:>8,} rows")

    hf = STATE / "health.json"
    health = json.loads(hf.read_text()) if hf.exists() else {}
    cols = ["source", "last_attempt", "last_success", "consecutive_failures", "last_error", "detail"]
    hdf = pd.DataFrame([{"source": k, **{c: v.get(c) for c in cols[1:]}} for k, v in health.items()], columns=cols)
    hdf = hdf.astype({c: "string" for c in cols if c != "consecutive_failures"})
    con.register("hdf", hdf)
    con.execute("create or replace table raw.source_health as select * from hdf")
    con.close()


if __name__ == "__main__":
    main()
