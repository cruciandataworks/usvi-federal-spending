"""Shared helpers: calls to the USAspending API, the Parquet "lake", and the source-health log.

The lake (all Parquet, never edited by hand):

    lake/transactions/fy=YYYY.parquet  every prime award action performed in the USVI, by fiscal year
    lake/awards/                        one row per contract and per grant (lifetime totals, end dates)
    lake/subawards/                     subcontracts and subgrants performed in the USVI
    lake/official/                      USAspending's own yearly totals, kept to check ours against
    lake/_state/                        how far each collector has got, and collector health
"""
import json
import os
import time
from datetime import date, datetime, timezone
from pathlib import Path

import duckdb
import pandas as pd
import requests

ROOT = Path(__file__).resolve().parents[1]
LAKE = Path(os.environ.get("LAKE_DIR", ROOT / "lake"))
STATE = LAKE / "_state"
API = "https://api.usaspending.gov/api/v2"
HEADERS = {"User-Agent": "CrucianDataWorks-portfolio/1.0 (hello@cruciandataworks.com)"}

# "Performed in the U.S. Virgin Islands": USAspending's primary place of performance filter
USVI = [{"country": "USA", "state": "VI"}]

# USAspending's award type codes, grouped the way its website groups them
GROUPS = {
    "contracts": ["A", "B", "C", "D"],              # definitive contracts, purchase and delivery orders, BPA calls
    "grants": ["02", "03", "04", "05"],             # block, formula, project grants, cooperative agreements
    "direct_payments": ["06", "10"],                # direct payments for a specified use, or unrestricted
    "loans": ["07", "08"],                          # direct and guaranteed loans
    "other": ["09", "11", "-1"],                    # insurance and other financial assistance
}
FIRST_FY = 2008   # the search API starts on 1 October 2007 (fiscal year 2008)
PAGE = 100        # the most rows the API returns per page
MAX_WINDOW = 9_500  # the search index cannot page past 10,000 rows, so bigger windows are split


def now_utc() -> datetime:
    return datetime.now(timezone.utc)


def fiscal_year(d: date) -> int:
    """The federal fiscal year starts on 1 October: 1 Oct 2025 is the first day of FY2026."""
    return d.year + 1 if d.month >= 10 else d.year


def fy_bounds(fy: int):
    return f"{fy - 1}-10-01", f"{fy}-09-30"


def post(endpoint, payload, tries=4, timeout=120):
    """POST to the API with retries: waits 5, 15 then 45 seconds after a failure.
    A 4xx answer (a mistake in our request) is not retried."""
    last = None
    for attempt in range(tries):
        try:
            r = requests.post(f"{API}/{endpoint}", json=payload, headers=HEADERS, timeout=timeout)
            if r.status_code >= 500 or r.status_code == 429:
                raise requests.HTTPError(f"HTTP {r.status_code}")
            if r.status_code >= 400:
                raise LookupError(f"HTTP {r.status_code} for {endpoint}: {r.text[:300]}")
            return r.json()
        except (requests.RequestException, requests.HTTPError) as e:
            last = e
            if attempt < tries - 1:
                time.sleep(5 * 3 ** attempt)
    raise RuntimeError(f"{endpoint} failed after {tries} attempts: {last}")


def write_parquet(df: pd.DataFrame, path: Path):
    """Write a whole table, beside the old file first so a crash never leaves half a file."""
    path.parent.mkdir(parents=True, exist_ok=True)
    df = df.copy()
    for c in df.columns:  # an all-empty text column must still be text
        if df[c].dtype == object and df[c].isna().all():
            df[c] = df[c].astype("string")
    con = duckdb.connect()
    con.register("df", df)
    tmp = path.with_suffix(".tmp")
    con.execute(f"copy df to '{tmp}' (format parquet, compression zstd)")
    os.replace(tmp, path)


def upsert(path: Path, df: pd.DataFrame, keys: list) -> int:
    """Merge rows into one Parquet file. A row whose keys already exist is replaced by the
    newer copy (an award that was changed), so repeating a run never creates duplicates.
    Returns how many rows are new."""
    if df.empty:
        return 0
    df = df.drop_duplicates(subset=keys, keep="last").copy()
    for c in df.columns:
        if df[c].dtype == object and df[c].isna().all():
            df[c] = df[c].astype("string")
    path.parent.mkdir(parents=True, exist_ok=True)
    con = duckdb.connect()
    con.register("new_rows", df)
    if path.exists():
        before = con.execute(f"select count(*) from read_parquet('{path}')").fetchall()[0][0]
        query = f"""
            select * exclude (src, rn) from (
                select *, row_number() over (partition by {', '.join(keys)} order by src desc) rn
                from (select *, 1 as src from new_rows
                      union all by name select *, 0 as src from read_parquet('{path}'))
            ) where rn = 1 order by {', '.join(keys)}"""
    else:
        before = 0
        query = f"select * from new_rows order by {', '.join(keys)}"
    tmp = path.with_suffix(".tmp")
    con.execute(f"copy ({query}) to '{tmp}' (format parquet, compression zstd)")
    after = con.execute(f"select count(*) from read_parquet('{tmp}')").fetchall()[0][0]
    os.replace(tmp, path)
    return after - before


def load_state(name):
    f = STATE / f"{name}.json"
    return json.loads(f.read_text()) if f.exists() else {}


def save_state(name, data):
    STATE.mkdir(parents=True, exist_ok=True)
    (STATE / f"{name}.json").write_text(json.dumps(data, indent=2, sort_keys=True))


def record_health(source: str, ok: bool, rows: int = 0, error: str = "", detail: str = ""):
    """One line per source: when it last worked, how many runs in a row failed, and the
    last error. The dashboard and the alerts read this file."""
    health = load_state("health")
    h = health.get(source, {"consecutive_failures": 0})
    h["last_attempt"] = now_utc().replace(microsecond=0).isoformat()
    if ok:
        h.update(last_success=h["last_attempt"], consecutive_failures=0, last_rows=rows,
                 last_error="", detail=detail)
    else:
        h["consecutive_failures"] = h.get("consecutive_failures", 0) + 1
        h["last_error"] = error[:300]
    health[source] = h
    save_state("health", health)


ALL_PRIME_TYPES = sum(GROUPS.values(), [])


def bulk_download(filters: dict, label: str, wait_minutes=25) -> bytes:
    """Ask USAspending to build a download, wait until it is ready, and return the zip.

    The bulk download service builds a zip of CSV files on request: one row per
    transaction with every published field (about 300 for contracts, 116 for assistance)
    and a unique key per row, which the paged search does not have. A year of USVI
    records takes about a minute to build."""
    job = post("bulk_download/awards/", {"filters": filters, "file_format": "csv"})
    deadline = time.time() + wait_minutes * 60
    misses = 0
    while time.time() < deadline:
        time.sleep(10)
        try:
            s = requests.get(job["status_url"], headers=HEADERS, timeout=60).json()
            misses = 0
        except (requests.RequestException, ValueError) as e:
            misses += 1  # one dropped status check is not a failed download; ten in a row is
            if misses >= 10:
                raise RuntimeError(f"{label}: lost contact with USAspending while waiting: {e}")
            continue
        if s.get("status") == "finished":
            for attempt in range(3):
                try:
                    r = requests.get(s["file_url"], headers=HEADERS, timeout=300)
                    r.raise_for_status()
                    print(f"    {label}: {s.get('total_rows', '?')} rows, built in "
                          f"{float(s.get('seconds_elapsed') or 0):.0f}s", flush=True)
                    return r.content
                except requests.RequestException:
                    time.sleep(10)
            raise RuntimeError(f"{label}: the download was built but could not be fetched")
        if s.get("status") == "failed":
            raise RuntimeError(f"{label}: USAspending could not build the download: {s.get('message')}")
    raise RuntimeError(f"{label}: the download was not ready after {wait_minutes} minutes")
