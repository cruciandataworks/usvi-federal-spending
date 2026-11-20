# USVI Federal Spending

Portfolio project 06 · [Crucian Data Works](https://cruciandataworks.com) · Roger Simon

Where does federal money go in the U.S. Virgin Islands, who receives it, how much stays with local firms, and which contracts end soon? This pipeline downloads every federal contract, grant, loan and payment performed in the territory since fiscal year 2008 from [USAspending.gov](https://www.usaspending.gov/state/78/latest). It proves its totals match USAspending's own to the dollar, and refreshes every morning. When a new contract of $100,000 or more appears, it opens a GitHub alert.

Live dashboard: [cruciandataworks.com/projects/federal-spending](https://cruciandataworks.com/projects/federal-spending/)

## What it does

1. **Prime transactions.** The pipeline asks USAspending's [bulk download service](https://api.usaspending.gov/docs/endpoints) (`bulk_download/awards`) for every prime award transaction whose place of performance is the Virgin Islands, one fiscal year at a time. The first run downloads all 20 fiscal years, FY2008 to FY2027 (70,486 transactions on 39,420 awards). After that, each day it fetches only what changed in the last few days, and once a week it reloads the two most recent fiscal years in full.
2. **Subawards.** It downloads the subcontracts and subgrants that primes report for USVI work: 2,150 so far.
3. **Official totals.** It fetches USAspending's own yearly totals by award type (`search/spending_over_time`) for the same filter.
4. **Load.** It loads the Parquet lake into DuckDB.
5. **Model and test.** dbt builds 16 models and runs 35 data tests every time. The key test adds up every transaction and fails the build if any completed fiscal year differs from USAspending's total by more than $1. All 20 years and 100 year-and-type combinations match to the cent.
6. **Export.** It writes `summary.json` for the dashboard, plus `leads.csv` and `contractors.csv` for Excel.
7. **Alert.** It opens a GitHub issue for new contracts of $100,000 or more in the last 7 days, for a reconciliation gap, or when a collector fails two days running. It closes the issue when the condition clears.

## Results (first full build, 20 November 2026)

"Recent" means the last five complete fiscal years, FY2022 to FY2026.

| Measure | Result |
|---|---|
| Obligations for work in the USVI, FY2022–FY2026 | $24.9 billion |
| Through Homeland Security (almost all FEMA) | $19.0 billion, 76% |
| To the territorial government and its agencies | $21.3 billion, 86% |
| FEMA Public Assistance under the Hurricane Maria declaration (DR-4340), FY2022–FY2026 | $18.7 billion |
| Largest year | FY2025, $10.7 billion |
| Contracts, FY2022–FY2026 | $203 million, 0.8% of the total |
| Share of contract dollars won by USVI-based firms | 21% (FY2025: 7.6%, FY2026: 4.6%) |
| Contracts ending in the next 24 months, $25,000 or more | 85, worth $61.1 million; 45 held by off-island primes |
| Prime contractors with USVI work since FY2008 | 1,262 |
| Largest recent contractor | Conti Federal Services (Florida), $18.5 million, EPA remediation |

The story the data tells: almost all federal money in the territory is grants to the government for rebuilding after Irma and Maria, and the contract slice is small. Most contract dollars go to firms based elsewhere. The 45 off-island primes whose contracts end within two years are a ready list of companies that may need local partners when the work is bid again.

## A finding about the data itself

In October 2026 Treasury replaced the two-digit assistance type codes (`02`–`11`) with `F001`–`F010` ([GSDM validation rules v1.3](https://tfx.treasury.gov/system/files/2026-11/gsdm-validation-rules-v1.3.xlsx); [USAspending award types](https://api.usaspending.gov/api/v2/references/award_types/)). A download filtered on the old codes silently misses every new assistance record. The first build here was $244 million short for FY2026 and missed FY2027 entirely. The reconciliation test caught it, and a new test (`assert_known_award_types`) now names any code the pipeline does not recognise.

## Read with care

- These are obligations (commitments to pay), not cash. A negative figure is a reduction of an earlier award.
- Every row is work performed in the USVI, wherever the recipient is based.
- Assistance is reported monthly or later, so the current and previous fiscal years keep changing.
- A contract ending is not a solicitation. Check [SAM.gov](https://sam.gov/) for real opportunities.
- USAspending groups payments to individuals for privacy. No person is named here.

## Run it yourself

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
python tests/test_pipeline.py       # parser checks, no network
python run_pipeline.py              # about 10 minutes the first time (20 fiscal years)
python -m http.server 8806 -d dashboard
```

The full beginner walkthrough is in [docs/STEP_BY_STEP.md](docs/STEP_BY_STEP.md).

## Layout

```
pipeline/   step1_transactions.py  step2_subawards.py  step3_official.py  step4_load.py
            step5_export.py  step6_alerts.py  common.py
dbt/        staging -> intermediate -> marts, macros (fiscal years), tests (reconciliation)
dashboard/  index.html  app.js  spending.css  styles.css  data/summary.json  leads.csv  contractors.csv
tests/      test_pipeline.py, fixtures/ (small real USAspending downloads)
.github/workflows/refresh.yml   every day at 7:23 AM AST
```

## Credits

All data comes from the U.S. Department of the Treasury's [USAspending.gov](https://www.usaspending.gov/), through its [API](https://api.usaspending.gov/docs/endpoints) and [bulk download files](https://files.usaspending.gov/). This is an independent analysis, not procurement advice.
