"""Run every step in order. This is what the daily schedule calls.

    python run_pipeline.py            # full run: USAspending, rebuild, export, alerts
    python run_pipeline.py --from 4   # skip downloading, rebuild from the lake

Steps 2 and 3 (subawards, USAspending's own totals) may fail without stopping the run:
the failure is recorded, the dashboard shows it, and two failed days in a row raise an
alert. Step 1 (transactions) and any failure from step 4 on stop the run, so incomplete
or untested data never reaches the dashboard.
"""
import argparse
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
PY = sys.executable
STEPS = [
    (1, "Prime award transactions (USAspending)", [PY, "pipeline/step1_transactions.py"], False),
    (2, "Subawards (USAspending)", [PY, "pipeline/step2_subawards.py"], True),
    (3, "Official yearly totals (USAspending)", [PY, "pipeline/step3_official.py"], True),
    (4, "Load DuckDB", [PY, "pipeline/step4_load.py"], False),
    (5, "dbt build (models + tests)", ["dbt", "build", "--profiles-dir", "."], False),
    (6, "Export dashboard data", [PY, "pipeline/step5_export.py"], False),
    (7, "Sync alert issues", [PY, "pipeline/step6_alerts.py"], False),
]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--from", dest="start", type=int, default=1)
    ap.add_argument("--to", dest="end", type=int, default=7)
    args = ap.parse_args()
    if os.environ.get("TEST_FAILURE") == "true":
        print("TEST_FAILURE is set - failing on purpose to test the failure alert.")
        sys.exit(1)
    for n, label, cmd, tolerant in STEPS:
        if n < args.start or n > args.end:
            continue
        print(f"\n=== Step {n}: {label} ===", flush=True)
        cwd = ROOT / "dbt" if cmd[0] == "dbt" else ROOT
        result = subprocess.run(cmd, cwd=cwd, env=os.environ.copy())
        if result.returncode != 0:
            if tolerant:
                print(f"Step {n} failed - carrying on; the failure is recorded in source health.")
            else:
                print(f"Step {n} failed - stopping so bad data never reaches the dashboard.")
                sys.exit(result.returncode)
    print("\nAll steps finished.")


if __name__ == "__main__":
    main()
