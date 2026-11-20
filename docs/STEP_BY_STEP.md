# USVI Federal Spending: Step-by-Step Guide

Portfolio project 06 · Crucian Data Works · Roger Simon

This guide walks through the project in the order it was built. Each step covers the goal, why it is done that way, the command to run and what you should see. Work through it top to bottom and you will be able to rebuild the project yourself and explain every decision to a client.

Sources:
- [USAspending.gov, U.S. Virgin Islands profile](https://www.usaspending.gov/state/78/latest), run by the U.S. Department of the Treasury.
- [USAspending API endpoints](https://api.usaspending.gov/docs/endpoints), especially `bulk_download/awards`, `download/status` and `search/spending_over_time`.
- [USAspending bulk files](https://files.usaspending.gov/) and the [award type reference](https://api.usaspending.gov/api/v2/references/award_types/).
- Treasury [GSDM validation rules v1.3](https://tfx.treasury.gov/system/files/2026-11/gsdm-validation-rules-v1.3.xlsx), for the October 2026 change of assistance type codes.

This project is an independent analysis, not procurement advice.

---

## The big picture

Federal money is the largest outside source of income in the Virgin Islands. Every contract, grant, loan and payment is public on USAspending.gov. But the website answers one question at a time, and it does not tell a local firm "which contracts here end soon, who holds them, and do they hire local subcontractors?"

This project downloads everything performed in the territory since fiscal year 2008, proves that nothing was lost, and turns it into a lead list.

```
USAspending bulk download ─► 1 transactions ─┐
USAspending bulk download ─► 2 subawards ────┼─► Parquet lake ─► 4 load DuckDB ─► 5 dbt models + tests
USAspending search API ────► 3 official totals┘                                       │
                                         dashboard + CSV ◄─ 6 export ◄────────────────┤
                                           GitHub issues ◄─ 7 sync alerts ◄───────────┘
```

Three words you will see everywhere:

- **Obligation.** The government's legal commitment to pay. This is what USAspending counts as "spending". Cash goes out later (an outlay). A negative obligation reduces an earlier one.
- **Fiscal year.** October to September. FY2026 ran from 1 October 2025 to 30 September 2026.
- **Place of performance.** Where the work happens. A Florida firm repairing a St. Thomas pier counts here; a USVI firm working in Puerto Rico does not.

### Final results (first full build, 20 November 2026)

| Measure | Result |
|---|---|
| Fiscal years / transactions / awards | FY2008–FY2027 / 70,486 / 39,420 |
| Subawards reported | 2,150 |
| Reconciliation with USAspending | 100 of 100 year-and-type totals match to the cent |
| dbt | 16 models, 35 data tests, all pass |

What the data shows:

- **$24.9 billion in five years.** From FY2022 to FY2026, 76% came through Homeland Security (almost all FEMA) and 86% went to the territorial government and its agencies.
- **Maria is still the story.** $18.7 billion of that is FEMA Public Assistance under the Hurricane Maria declaration, DR-4340. FY2025 alone was $10.7 billion.
- **Contracts are a small slice, and mostly off-island.** $203 million in contracts over five years, and only 21% went to firms based in the USVI. In FY2026 it was 4.6%.
- **85 contracts end in the next two years**, worth $61.1 million. 45 of them are held by off-island primes.

---

## Step 0: Set up your machine

You need Python 3.12 or newer.

```bash
cd 06-usvi-federal-spending
python -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -r requirements.txt    # requests, duckdb, pandas, dbt-core, dbt-duckdb
```

### Project layout

```
pipeline/
  common.py               shared helpers: award type codes, HTTP with retries, bulk download, upsert, health log
  step1_transactions.py   prime transactions -> lake/transactions/fy=YYYY.parquet
  step2_subawards.py      subcontracts and subgrants -> lake/subawards/fy=YYYY.parquet
  step3_official.py       USAspending's own yearly totals -> lake/official
  step4_load.py           lake -> DuckDB "raw" schema
  step5_export.py         marts -> dashboard/data/summary.json, leads.csv, contractors.csv
  step6_alerts.py         open / update / close GitHub issues
dbt/
  macros/                 fiscal.sql (fiscal year of a date, the current year, "recent years")
  models/staging          clean names, types and labels
  models/intermediate     int_awards: one row per award
  models/marts            years, reconciliation, agencies, contractors, leads, NAICS, local share, subawards, alerts
  tests/                  reconciliation, known award types, all in USVI, fiscal years, leads window
tests/test_pipeline.py    parser checks against small real downloads (no network)
run_pipeline.py           runs steps 1 to 7
```

---

## Step 1: Download prime transactions

**Goal:** every prime award transaction performed in the USVI, with a unique key per row.

```bash
python pipeline/step1_transactions.py
```

USAspending offers two ways in. The **search API** pages through results 100 at a time and has no unique key per transaction. The **bulk download service** builds a zip of CSV files on request, with every published field (about 300 for contracts, 116 for assistance) and a unique key per row. This project uses bulk downloads:

1. POST a filter to `bulk_download/awards`: all prime award types, place of performance `{"country": "USA", "state": "VI"}`, and one fiscal year of action dates. The service only accepts a date range of one year or less.
2. USAspending replies with a `status_url`. Poll it every few seconds until the file is `finished`.
3. Download the zip and read the contracts and assistance CSVs into one table with our own column names (`COLUMNS` in the script maps both file layouts).

The first run downloads all 20 fiscal years, two at a time. You should see lines like:

```
    FY2018: 16952 rows, built in 87s
  FY2018: 16,952 transactions
```

FY2018 is the largest by far: the year after Irma and Maria. A whole backfill takes about 10 minutes.

**Resumable.** Each finished year is written to `lake/_state/transactions.json` (`years_done`). If the connection drops halfway (it did, during this build), the next run carries on from the missing year.

**Daily and weekly.** After the backfill, each run asks for everything whose `last_modified_date` falls in the last few days (3 days of overlap) and merges it in by `transaction_key`. A changed record replaces the old copy, so repeating a run never creates duplicates. Once a week the current and previous fiscal years are reloaded in full, which also removes anything USAspending deleted.

### Key idea: which number is "the" spending?

Contracts report `federal_action_obligation`. Assistance reports several amounts. For loans the obligation is the subsidy cost, not the face value of the loan. USAspending's own totals use `generated_pragmatic_obligations` for assistance, so this project uses the same. Choosing a different column would still look plausible, and only the reconciliation in Step 5 would tell you it was wrong.

### Key idea: the codes changed under us

The filter asks for "all prime award types" by listing their codes (`GROUPS` in `common.py`). In October 2026 Treasury replaced the assistance codes `02`–`11` with `F001`–`F010`. The first build of this project used the old list, so it silently missed every assistance record reported since then: $244 million in FY2026, and all of FY2027.

The fix lists both sets. The download state also remembers which code list it used (`type_codes`). When the list changes, every year is downloaded again. A unit test checks that the new codes are there, and a dbt test fails if any transaction carries a code we do not know.

---

## Step 2: Download subawards

**Goal:** the subcontracts and subgrants that primes report for USVI work.

```bash
python pipeline/step2_subawards.py
```

The same bulk download, with `sub_award_types: ["procurement", "grant"]`. Primes report subawards late, sometimes months after the work, so each day the current and previous fiscal years are downloaded again, and once a week all years are.

```
  2,150 subawards in FY2008-FY2027 (weekly full refresh)
```

This is the most direct answer to "who do the big primes hire here?". Subaward reporting is required only above $30,000 ($25,000 before late 2020) and is known to be incomplete, so treat every figure as a floor.

---

## Step 3: Fetch USAspending's own totals

**Goal:** an independent number to check ourselves against.

```bash
python pipeline/step3_official.py
```

`search/spending_over_time`, grouped by fiscal year, with the same place-of-performance filter. It returns totals for contracts, grants, direct payments, loans and other assistance.

```
  20 fiscal years; FY2026 total $1,540,129,944
```

Steps 2 and 3 are "tolerant": if USAspending is down, the run records the failure and carries on with yesterday's data. Two failures in a row open an alert.

---

## Step 4: Load into DuckDB

```bash
python pipeline/step4_load.py
```

Creates `warehouse/spending.duckdb` with four raw tables: `transactions`, `subawards`, `official_totals` and `source_health`. Every column is loaded as text, exactly as USAspending sent it. Types are set in dbt, where each choice is visible and tested.

---

## Step 5: Model and test with dbt

```bash
cd dbt && dbt build --profiles-dir . && cd ..
```

You should see `PASS=51 WARN=0 ERROR=0`.

### The layers

- **Staging** (`stg_transactions`, `stg_subawards`, `stg_official_totals`, `stg_source_health`): types, award groups, labels, recipient kind (territorial government, individuals, businesses, nonprofits and colleges), island, and the "local" flag (the recipient's own address is in the USVI).
- **Intermediate** (`int_awards`): one row per award. It records what was agreed at the start, where the award stands now (latest end date and value), and how much of it was obligated for work in the USVI.
- **Marts**: spending by year, reconciliation, agencies, recipient kinds, contractors, NAICS demand, local share, contract leads, subcontracting, new contracts and alerts.

### Key idea 1: reconcile to the cent

`mart_reconciliation` adds up our transactions by fiscal year and award type and puts them beside USAspending's totals. Two tests read it:

- `assert_matches_official_completed_years` fails the build if any year that closed more than a year ago differs by more than $1 (`reconcile_tolerance_usd`).
- `assert_matches_official_recent_years` only warns for the current and previous year, which agencies are still reporting.

On this build all 100 combinations match to the cent. This test is what found the code change in Step 1. Without it the dashboard would have shown FY2026 $290 million too low, and nobody would have known.

### Key idea 2: classify the award, not the transaction

At first, a few years were off by small amounts. The cause: an award sometimes changes type, for example a project grant later recorded as a direct payment. USAspending files the whole award under the type of its latest action, in every year. `stg_transactions` does the same with a window function (`first_value(...) over (partition by award_key order by action_date desc ...)`), and every year then matched exactly.

### Key idea 3: define a lead and say it

`mart_contract_leads` is a contract performed in the USVI that is worth $25,000 or more and whose current end date falls in the next 24 months. Both numbers are `vars` in `dbt_project.yml`, so a client can change them and rebuild. When a contract ends, the agency usually buys the work again. The new prime, often from off-island, may need local subcontractors, equipment or space. `has_options_left` shows when the agency can still extend without competing.

### Key idea 4: tests that say what must be true

- `assert_all_in_usvi`: every transaction is performed in the territory (state FIPS 78).
- `assert_fiscal_year_matches_date`: the fiscal year in the file name matches the action date.
- `assert_awards_add_up`: the award table adds up to the transaction table.
- `assert_leads_in_window`: no lead ends in the past or beyond the horizon.
- `assert_known_award_types`: every award type code is one we know.

---

## Step 6: Export for the dashboard

```bash
python pipeline/step5_export.py
```

```
  wrote dashboard/data/summary.json (236 KB)
  wrote dashboard/data/leads.csv (49 KB)
  wrote dashboard/data/contractors.csv (298 KB)
```

The dashboard is plain HTML and JavaScript that reads `summary.json`. It never talks to USAspending or the database, so it can be hosted anywhere as files. Open it with:

```bash
python -m http.server 8806 -d dashboard
```

The CSV files are linked from the page ("Download CSV"), so a business owner can open the lead list in Excel.

---

## Step 7: Alert issues on GitHub

```bash
python pipeline/step6_alerts.py
```

Without a `GH_TOKEN` it only prints what it would do. In GitHub Actions it keeps one issue open per alert key, labelled `spending-alert`:

- `new-contracts`: contracts of $100,000 or more whose first action was in the last 7 days, listed with agency, contractor and a link.
- `reconcile`: a year and type that no longer matches USAspending.
- `collector:<source>`: a download that failed two days in a row.

GitHub emails you when an issue opens. It closes itself when the condition clears.

---

## Step 8: Run everything with one command

```bash
python tests/test_pipeline.py     # 5 parser checks, no network
python run_pipeline.py            # steps 1-7
python run_pipeline.py --from 4   # rebuild from the lake without downloading
```

Step 1 failing stops the run, and so does any failure from step 4 on, so incomplete or untested data never reaches the dashboard.

---

## Step 9: Schedule it every day

`.github/workflows/refresh.yml` runs at 11:23 UTC, 7:23 AM in the Virgin Islands. USAspending loads new records overnight. Each run:

1. Downloads the lake from a GitHub release called `lake` (one `lake.tar.gz`, none of it in git).
2. Runs the unit tests and the pipeline.
3. Uploads the lake again, even if a later step failed, so a long backfill never restarts from nothing.
4. Commits the dashboard data. GitHub pauses schedules in repositories with no commits for 60 days.
5. Uploads the dashboard to Hostinger, if the FTP secrets exist.
6. On any failure, opens or updates a "refresh failed" issue.

Run it by hand from Actions → Federal spending refresh → Run workflow. `collect_only` runs steps 1 to 3 only, which is how the first backfill was done.

### Setup checklist in GitHub

1. Settings → Secrets and variables → Actions → Secrets: `FTP_SERVER`, `FTP_USERNAME`, `FTP_PASSWORD`.
2. Variables: `FTP_SERVER_DIR` = `/public_html/projects/federal-spending/`. Optionally set `ALERT_ASSIGNEE`.
3. Actions → Federal spending refresh → Run workflow, to test.

---

## Talking about this project

- "Every figure on the page is tested against Treasury's own totals, to the cent, for 20 years."
- "That test caught a change in federal reporting codes that silently dropped $290 million from the most recent year. Most dashboards built on this data would still be wrong."
- "For a local firm, the useful output is not a chart. It is a list of 85 contracts ending in the next two years, who holds them and how to reach the agency."
- "Definitions such as the $25,000 minimum and the 24-month horizon are settings, stated on the page, so they can be changed for a client."

For a chamber of commerce, an economic development agency or a contractor, the same pipeline can watch any place, agency or industry code.

## Publishing to cruciandataworks.com

The workflow uploads `dashboard/` to `/public_html/projects/federal-spending/` on every run once the FTP secrets are set. The homepage card links to [cruciandataworks.com/projects/federal-spending](https://cruciandataworks.com/projects/federal-spending/).
