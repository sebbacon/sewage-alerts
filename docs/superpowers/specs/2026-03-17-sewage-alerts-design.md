# Sewage Alerts — Design Spec

**Date:** 2026-03-17

## Overview

A GitHub Actions-powered tool that runs on a configurable cron schedule and emails the user when sewage overflow events have started near their home within a configurable lookback window. Designed to be forkable and usable by non-technical users with a guided setup script and clear documentation.

---

## Data Source

**ArcGIS Feature Service — Severn Trent Water Storm Overflow Activity**

```
https://services1.arcgis.com/NO7lTIlnxRMMG9Gw/arcgis/rest/services/
  Severn_Trent_Water_Storm_Overflow_Activity/FeatureServer/0/query
```

**Relevant fields:**

| Field | Type | Description |
|---|---|---|
| `Id` | string | Site identifier (e.g. `SVT00291`) |
| `ReceivingWaterCourse` | string | Name of affected watercourse |
| `Latitude` / `Longitude` | float | Site coordinates |
| `LatestEventStart` | epoch ms | When the most recent overflow began |
| `LatestEventEnd` | epoch ms | When it ended (if it has) |
| `Status` | int | Current status code |
| `LastUpdated` | epoch ms | When this record was last refreshed |

**Key findings from API exploration:**
- 2,413 total records in the dataset
- The ArcGIS API supports server-side spatial filtering via `geometry` + `distance` + `units=esriSRUnit_Meter`
- The ArcGIS API supports server-side time filtering via `INTERVAL` syntax: `LatestEventStart >= CURRENT_TIMESTAMP - INTERVAL '24' HOUR`
- Both filters can be combined in a single request, keeping response sizes small (e.g. 1 result for 20km / 24h around GL5 1HE at time of design)
- No pagination required given spatial pre-filtering

---

## Alert Trigger

An alert is sent when one or more overflow events have **started** (based on `LatestEventStart`) within the configured `lookback_hours` window AND within `radius_km` of the configured postcode. Events that started before the lookback window are ignored, avoiding repeat alerts for long-running spills.

**Assumption:** `LatestEventStart` represents when the event began and is not updated mid-event. If Severn Trent's system were to refresh this field during an ongoing spill, an active spill could re-trigger on consecutive runs — this is considered acceptable behaviour if it occurs, as the alert remains factually correct.

---

## Repository Structure

```
sewage_alerts/
├── .github/
│   └── workflows/
│       └── check_spills.yml      # GitHub Actions cron workflow
├── docs/
│   └── superpowers/
│       └── specs/
│           └── 2026-03-17-sewage-alerts-design.md
├── check_spills.py               # Main script
├── setup.py                      # Interactive setup script
├── config.yml                    # User-editable configuration
├── requirements.txt              # PyYAML pinned
└── README.md                     # Setup instructions
```

---

## Configuration (`config.yml`)

```yaml
postcode: "GL5 1HE"
radius_km: 20
lookback_hours: 24
notify_email: "you@gmail.com"
```

The `lookback_hours` value must match the cron schedule interval. The `setup.py` script writes both together, ensuring consistency at setup time. If a user later edits either file manually, `check_spills.py` will log a warning to stderr if `lookback_hours` does not correspond to a recognised standard interval (6, 12, or 24 hours), but will not abort.

---

## Script Logic (`check_spills.py`)

```
1. Load config.yml
2. GET https://api.postcodes.io/postcodes/{postcode}
   → extract latitude, longitude
3. GET ArcGIS query with:
   - geometry={lon},{lat}&geometryType=esriGeometryPoint&inSR=4326
   - distance={radius_km * 1000}&units=esriSRUnit_Meter
   - where=LatestEventStart >= CURRENT_TIMESTAMP - INTERVAL '{lookback_hours}' HOUR
   - outFields=*&f=geojson
4. If 0 results → exit 0 (no email sent)
5. If results found:
   - Compute haversine distance from home for each result (for display only — ArcGIS spatial filter already guarantees all results are within radius_km)
   - Send HTML email via Gmail SMTP (smtplib)
```

**Dependencies:** Python stdlib (`urllib`, `smtplib`, `json`, `math`) plus `PyYAML` (pinned in `requirements.txt`).

**Email format:** Multipart MIME (text + HTML). HTML body contains a table with columns: Site ID, Watercourse, Distance from home (km), Event started (local time), Event ended (local time or "Ongoing"). `Status` field is intentionally excluded — its integer codes are undocumented.

**Credentials:** Read from environment variables `GMAIL_ADDRESS` and `GMAIL_APP_PASSWORD`, set as GitHub Actions secrets.

---

## GitHub Actions Workflow (`.github/workflows/check_spills.yml`)

```yaml
on:
  schedule:
    - cron: '0 7 * * *'    # daily at 07:00 UTC — kept in sync with lookback_hours by setup.py
  workflow_dispatch:         # allows manual trigger for testing

jobs:
  check:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: '3.12'
      - run: pip install -r requirements.txt
      - run: python check_spills.py
        env:
          GMAIL_ADDRESS: ${{ secrets.GMAIL_ADDRESS }}
          GMAIL_APP_PASSWORD: ${{ secrets.GMAIL_APP_PASSWORD }}
```

---

## Setup Script (`setup.py`)

Interactive script run once by the user after forking. Prompts for:

1. Postcode (default: existing value from `config.yml`)
2. Notification email
3. Check interval (1=Every 6h, 2=Every 12h, 3=Daily, 4=Custom cron)
4. Time of day for daily/12h runs (UTC hour)

Outputs:
- Updated `config.yml`
- Updated cron expression in `.github/workflows/check_spills.yml`
- Printed next-step commands ready to copy-paste:

```
Setup complete! Run these commands to finish:

  gh secret set GMAIL_ADDRESS
  gh secret set GMAIL_APP_PASSWORD

Then push and test:

  git add config.yml .github/workflows/check_spills.yml
  git commit -m "configure sewage alerts"
  git push
  gh workflow run check_spills.yml
```

---

## User Setup Flow (documented in README)

Designed for non-technical users. Prerequisites: Python 3 installed.

1. Create a GitHub account at github.com/signup
2. Install GitHub CLI: follow instructions at cli.github.com
3. Run: `gh auth login`
4. Run: `gh repo fork <this-repo> --clone && cd sewage-alerts`
5. **Enable GitHub Actions on your fork:** go to your forked repo on github.com → Actions tab → click "I understand my workflows, go ahead and enable them"
6. Run: `python setup.py` and follow the prompts
7. Create a Gmail App Password:
   - Google Account → Security → 2-Step Verification → App Passwords
   - Name it "Sewage Alerts", copy the generated password
8. Paste and run the commands printed by `setup.py`
9. Done — the action will run on schedule and email you when spills are found nearby

**Geographic note:** This tool uses Severn Trent Water's dataset and only covers their service area (broadly the Midlands and parts of the East of England). If your postcode is outside this area, the script will run without error but will never find any events. Check the [Severn Trent service area map](https://www.stwater.co.uk/) if unsure.

---

## Error Handling

- Postcode lookup failure (invalid postcode, API down): script exits non-zero, workflow fails visibly in GitHub Actions UI
- ArcGIS API failure: script exits non-zero, workflow fails visibly
- SMTP failure: script exits non-zero, workflow fails visibly
- All errors print a descriptive message to stderr before exiting

Workflow failures generate a GitHub notification email to the repo owner (separate from spill alert emails).

---

## Out of Scope

- Support for water companies other than Severn Trent (dataset is Severn Trent specific)
- Historical reporting or data persistence
- Deduplication across runs (by design — lookback window handles this)
- Mobile push notifications
- Multiple recipient addresses
