"""Checks for the parts of the pipeline that read USAspending's files. No network needed.

    python tests/test_pipeline.py

The two fixture zips are real USAspending bulk downloads cut down to a few rows:
three FY2025 contract transactions and three assistance transactions (a project grant,
a loan and a direct payment), and two FY2020 subawards. If USAspending ever renames a
column we rely on, these tests fail before the daily run does.
"""
import sys
from datetime import date
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "pipeline"))

from common import fiscal_year  # noqa: E402
import step1_transactions as s1  # noqa: E402
import step2_subawards as s2  # noqa: E402

FIX = ROOT / "tests" / "fixtures"


def test_fiscal_year():
    assert fiscal_year(date(2025, 9, 30)) == 2025
    assert fiscal_year(date(2025, 10, 1)) == 2026  # the federal year starts on 1 October
    assert fiscal_year(date(2026, 1, 15)) == 2026


def test_prime_zip():
    df = s1.read_zip((FIX / "prime_fy2025_sample.zip").read_bytes())
    assert len(df) == 6, len(df)
    assert set(df.kind) == {"contract", "assistance"}
    assert df.transaction_key.is_unique and df.transaction_key.notna().all()
    assert (df.fiscal_year == 2025).all()
    assert (df.pop_state_fips == "78").all(), df.pop_state_fips.unique()  # 78 = U.S. Virgin Islands
    # contracts have NAICS codes, assistance has assistance listings (CFDA numbers)
    assert df[df.kind == "contract"].naics_code.notna().all()
    assert df[df.kind == "assistance"].cfda_number.notna().all()
    # a loan's obligation is its subsidy cost, not its face value - the way USAspending counts it
    loan = df[df.award_type_code == "07"].iloc[0]
    assert pd.isna(pd.to_numeric(loan.federal_action_obligation)) or float(loan.federal_action_obligation) == 0
    assert float(loan.obligation) != 0 and float(loan.face_value_of_loan) > abs(float(loan.obligation))


def test_every_column_exists():
    """Every source column named in step 1 and step 2 must be in USAspending's files."""
    import io
    import zipfile
    for fixture, cols, optional in [("prime_fy2025_sample.zip", s1.COLUMNS, set()),
                                    ("subawards_fy2020_sample.zip", s2.COLUMNS, s2.CONTRACT_ONLY)]:
        with zipfile.ZipFile(FIX / fixture) as z:
            for name in z.namelist():
                header = set(pd.read_csv(io.BytesIO(z.read(name)), nrows=0).columns)
                i = 0 if "_Contracts_" in name else 1
                for ours, theirs in cols.items():
                    if ours in optional and "_Contracts_" not in name:
                        continue
                    src = theirs[i] if isinstance(theirs, tuple) else theirs
                    assert src is None or src in header, f"{name}: missing {src} (for {ours})"


def test_subaward_zip():
    df = s2.read_zip((FIX / "subawards_fy2020_sample.zip").read_bytes())
    assert len(df) == 4 and set(df.kind) == {"subcontract", "subgrant"}
    assert df.subaward_key.is_unique and df.prime_award_key.notna().all()
    assert (pd.to_numeric(df.subaward_amount) > 0).all()


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn()
            print(f"  ok  {name}")


def test_new_assistance_codes_are_collected():
    """USAspending's F001-F010 codes (from October 2026) must be in the download filter."""
    from common import ALL_PRIME_TYPES, GROUPS
    assert {"F001", "F002"} <= set(GROUPS["grants"])
    assert {"F006", "F007"} <= set(GROUPS["direct_payments"])
    assert {f"F{n:03d}" for n in range(1, 11)} <= set(ALL_PRIME_TYPES)
