# Sewage Alerts Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a GitHub Actions cron job that emails the user when sewage overflow events have started within a configurable radius of their home postcode within a configurable lookback window.

**Architecture:** A single Python script (`check_spills.py`) queries the Severn Trent ArcGIS Feature Service with server-side spatial and time filters, computes display-only haversine distances, and sends a multipart HTML/text email via Gmail SMTP. A `configure.py` script handles one-time interactive setup, writing both `config.yml` and patching the cron expression in the workflow YAML to keep them in sync.

**Tech Stack:** Python 3.12, PyYAML==6.0.2, pytest (dev only), GitHub Actions, Gmail SMTP (port 465 SSL), ArcGIS Feature Service (INTERVAL + geometry filters), postcodes.io (no key required)

---

## File Map

| File | Responsibility |
|---|---|
| `check_spills.py` | All runtime logic: config loading, postcode lookup, ArcGIS query, distance calc, email |
| `configure.py` | Interactive setup: prompts user, writes config.yml, patches workflow cron |
| `config.yml` | User config: postcode, radius_km, lookback_hours, notify_email |
| `requirements.txt` | Runtime deps: PyYAML==6.0.2 |
| `requirements-dev.txt` | Dev deps: pytest |
| `.github/workflows/check_spills.yml` | Cron workflow, reads secrets, runs check_spills.py |
| `tests/__init__.py` | Empty — marks tests as package |
| `tests/test_check_spills.py` | All tests for check_spills.py functions |
| `tests/test_configure.py` | Tests for configure.py functions |
| `README.md` | Non-technical user setup instructions |

---

## Task 1: Project scaffold

**Files:**
- Create: `requirements.txt`
- Create: `requirements-dev.txt`
- Create: `config.yml`
- Create: `tests/__init__.py`
- Create: `check_spills.py` (importable skeleton)
- Create: `configure.py` (importable skeleton)

- [ ] **Step 1: Create `requirements.txt`**

```
PyYAML==6.0.2
```

- [ ] **Step 2: Create `requirements-dev.txt`**

```
pytest
```

- [ ] **Step 3: Create `config.yml`**

```yaml
postcode: "GL5 1HE"
radius_km: 20
lookback_hours: 24
notify_email: "you@gmail.com"
```

- [ ] **Step 4: Create `tests/__init__.py`**

Empty file.

- [ ] **Step 5: Create `check_spills.py` skeleton**

```python
#!/usr/bin/env python3
"""Check for sewage overflow events near a configured postcode and send email alerts."""

import json
import math
import os
import smtplib
import sys
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

import yaml

ARCGIS_URL = (
    "https://services1.arcgis.com/NO7lTIlnxRMMG9Gw/arcgis/rest/services/"
    "Severn_Trent_Water_Storm_Overflow_Activity/FeatureServer/0/query"
)
POSTCODES_URL = "https://api.postcodes.io/postcodes/{}"
STANDARD_LOOKBACK_HOURS = {6, 12, 24}


if __name__ == "__main__":
    pass
```

- [ ] **Step 6: Create `configure.py` skeleton**

```python
#!/usr/bin/env python3
"""Interactive setup script for sewage alerts."""

import re
import yaml

WORKFLOW_PATH = ".github/workflows/check_spills.yml"
CONFIG_PATH = "config.yml"


if __name__ == "__main__":
    pass
```

- [ ] **Step 7: Install dev dependencies**

```bash
pip install -r requirements-dev.txt -r requirements.txt
```

- [ ] **Step 8: Verify pytest runs (no tests yet)**

```bash
pytest tests/ -v
```

Expected: `no tests ran` or `0 passed`.

- [ ] **Step 9: Commit**

```bash
git add requirements.txt requirements-dev.txt config.yml tests/__init__.py check_spills.py configure.py
git commit -m "feat: scaffold project structure"
```

---

## Task 2: Haversine distance

**Files:**
- Modify: `check_spills.py` — add `haversine_km`
- Create: `tests/test_check_spills.py` — first tests

- [ ] **Step 1: Write the failing tests**

Create `tests/test_check_spills.py`:

```python
import math
import pytest
import check_spills


class TestHaversineKm:
    def test_zero_distance(self):
        assert check_spills.haversine_km(51.5, -0.1, 51.5, -0.1) == pytest.approx(0.0)

    def test_known_distance_london_to_paris(self):
        # London (51.5074, -0.1278) to Paris (48.8566, 2.3522) ≈ 340km
        dist = check_spills.haversine_km(51.5074, -0.1278, 48.8566, 2.3522)
        assert 330 < dist < 350

    def test_within_20km(self):
        # GL5 1HE approx (51.745, -2.216) to River Severn site (51.752, -2.449) ≈ 14km
        dist = check_spills.haversine_km(51.745, -2.216, 51.752, -2.449)
        assert dist < 20
        assert dist > 0
```

- [ ] **Step 2: Run tests to confirm failure**

```bash
pytest tests/test_check_spills.py -v
```

Expected: `AttributeError: module 'check_spills' has no attribute 'haversine_km'`

- [ ] **Step 3: Implement `haversine_km` in `check_spills.py`**

Add after the constants:

```python
def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Return great-circle distance in km between two lat/lon points."""
    R = 6371
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2) ** 2
    return 2 * R * math.asin(math.sqrt(a))
```

- [ ] **Step 4: Run tests to confirm they pass**

```bash
pytest tests/test_check_spills.py::TestHaversineKm -v
```

Expected: 3 passed.

- [ ] **Step 5: Commit**

```bash
git add check_spills.py tests/test_check_spills.py
git commit -m "feat: add haversine distance calculation"
```

---

## Task 3: Config loading and lookback validation

**Files:**
- Modify: `check_spills.py` — add `load_config`, `validate_lookback_hours`
- Modify: `tests/test_check_spills.py` — add tests

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_check_spills.py`:

```python
class TestLoadConfig:
    def test_loads_all_fields(self, tmp_path):
        f = tmp_path / "config.yml"
        f.write_text("postcode: GL5 1HE\nradius_km: 20\nlookback_hours: 24\nnotify_email: a@b.com\n")
        result = check_spills.load_config(str(f))
        assert result["postcode"] == "GL5 1HE"
        assert result["radius_km"] == 20
        assert result["lookback_hours"] == 24
        assert result["notify_email"] == "a@b.com"


class TestValidateLookbackHours:
    def test_standard_values_produce_no_warning(self, capsys):
        for hours in (6, 12, 24):
            check_spills.validate_lookback_hours(hours)
        assert capsys.readouterr().err == ""

    def test_nonstandard_value_warns_to_stderr(self, capsys):
        check_spills.validate_lookback_hours(7)
        err = capsys.readouterr().err
        assert "WARNING" in err
        assert "7" in err
```

- [ ] **Step 2: Run tests to confirm failure**

```bash
pytest tests/test_check_spills.py::TestLoadConfig tests/test_check_spills.py::TestValidateLookbackHours -v
```

Expected: `AttributeError` for both missing functions.

- [ ] **Step 3: Implement `load_config` and `validate_lookback_hours` in `check_spills.py`**

```python
def load_config(path: str = "config.yml") -> dict:
    """Load configuration from a YAML file."""
    with open(path) as f:
        return yaml.safe_load(f)


def validate_lookback_hours(hours: int) -> None:
    """Warn to stderr if lookback_hours is not a recognised standard value."""
    if hours not in STANDARD_LOOKBACK_HOURS:
        print(
            f"WARNING: lookback_hours={hours} is non-standard (expected 6, 12, or 24). "
            "Ensure your cron schedule matches.",
            file=sys.stderr,
        )
```

- [ ] **Step 4: Run tests to confirm they pass**

```bash
pytest tests/test_check_spills.py::TestLoadConfig tests/test_check_spills.py::TestValidateLookbackHours -v
```

Expected: 3 passed.

- [ ] **Step 5: Commit**

```bash
git add check_spills.py tests/test_check_spills.py
git commit -m "feat: add config loading and lookback validation"
```

---

## Task 4: Postcode lookup

**Files:**
- Modify: `check_spills.py` — add `get_postcode_coords`
- Modify: `tests/test_check_spills.py` — add tests

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_check_spills.py`:

```python
import json
from unittest.mock import MagicMock, patch


def _mock_urlopen(response_data: dict) -> MagicMock:
    """Return a context-manager mock for urllib.request.urlopen."""
    mock_cm = MagicMock()
    mock_cm.__enter__.return_value.read.return_value = json.dumps(response_data).encode()
    mock_cm.__exit__.return_value = False
    return mock_cm


class TestGetPostcodeCoords:
    def test_returns_lat_lon(self):
        payload = {"status": 200, "result": {"latitude": 51.745, "longitude": -2.216}}
        with patch("urllib.request.urlopen", return_value=_mock_urlopen(payload)):
            lat, lon = check_spills.get_postcode_coords("GL5 1HE")
        assert lat == pytest.approx(51.745)
        assert lon == pytest.approx(-2.216)

    def test_exits_on_network_error(self):
        with patch("urllib.request.urlopen", side_effect=Exception("network error")):
            with pytest.raises(SystemExit):
                check_spills.get_postcode_coords("GL5 1HE")
```

- [ ] **Step 2: Run tests to confirm failure**

```bash
pytest tests/test_check_spills.py::TestGetPostcodeCoords -v
```

Expected: `AttributeError: module 'check_spills' has no attribute 'get_postcode_coords'`

- [ ] **Step 3: Implement `get_postcode_coords` in `check_spills.py`**

```python
def get_postcode_coords(postcode: str) -> tuple[float, float]:
    """Return (latitude, longitude) for a UK postcode via postcodes.io."""
    url = POSTCODES_URL.format(urllib.parse.quote(postcode))
    try:
        with urllib.request.urlopen(url) as resp:
            data = json.loads(resp.read())
        result = data["result"]
        return result["latitude"], result["longitude"]
    except Exception as exc:
        print(f"ERROR: Could not look up postcode '{postcode}': {exc}", file=sys.stderr)
        sys.exit(1)
```

- [ ] **Step 4: Run tests to confirm they pass**

```bash
pytest tests/test_check_spills.py::TestGetPostcodeCoords -v
```

Expected: 2 passed.

- [ ] **Step 5: Commit**

```bash
git add check_spills.py tests/test_check_spills.py
git commit -m "feat: add postcode to lat/lon lookup via postcodes.io"
```

---

## Task 5: ArcGIS spill query

**Files:**
- Modify: `check_spills.py` — add `query_spills`
- Modify: `tests/test_check_spills.py` — add tests

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_check_spills.py`:

```python
SAMPLE_FEATURE = {
    "type": "Feature",
    "geometry": {"type": "Point", "coordinates": [-2.449, 51.752]},
    "properties": {
        "Id": "SVT00291",
        "ReceivingWaterCourse": "RIVER SEVERN",
        "Latitude": 51.752,
        "Longitude": -2.449,
        "LatestEventStart": 1773753148000,
        "LatestEventEnd": 1773753431000,
    },
}


class TestQuerySpills:
    def test_returns_features_list(self):
        payload = {"type": "FeatureCollection", "features": [SAMPLE_FEATURE]}
        with patch("urllib.request.urlopen", return_value=_mock_urlopen(payload)):
            features = check_spills.query_spills(51.745, -2.216, 20, 24)
        assert len(features) == 1
        assert features[0]["properties"]["Id"] == "SVT00291"

    def test_returns_empty_list_when_no_results(self):
        payload = {"type": "FeatureCollection", "features": []}
        with patch("urllib.request.urlopen", return_value=_mock_urlopen(payload)):
            features = check_spills.query_spills(51.745, -2.216, 20, 24)
        assert features == []

    def test_exits_on_network_error(self):
        with patch("urllib.request.urlopen", side_effect=Exception("network error")):
            with pytest.raises(SystemExit):
                check_spills.query_spills(51.745, -2.216, 20, 24)

    def test_url_contains_interval_and_distance(self):
        payload = {"type": "FeatureCollection", "features": []}
        captured_url = []
        original = urllib.request.urlopen

        def capturing_urlopen(url, **kwargs):
            captured_url.append(url)
            return _mock_urlopen(payload)

        with patch("urllib.request.urlopen", side_effect=capturing_urlopen):
            check_spills.query_spills(51.745, -2.216, 20, 24)

        url = captured_url[0]
        assert "INTERVAL" in url
        assert "24" in url
        assert "20000" in url
        assert "esriSRUnit_Meter" in url
```

- [ ] **Step 2: Run tests to confirm failure**

```bash
pytest tests/test_check_spills.py::TestQuerySpills -v
```

Expected: `AttributeError: module 'check_spills' has no attribute 'query_spills'`

- [ ] **Step 3: Implement `query_spills` in `check_spills.py`**

```python
def query_spills(lat: float, lon: float, radius_km: float, lookback_hours: int) -> list:
    """Query ArcGIS for overflow events within radius_km and lookback_hours of now."""
    params = urllib.parse.urlencode({
        "geometry": f"{lon},{lat}",
        "geometryType": "esriGeometryPoint",
        "inSR": "4326",
        "spatialRel": "esriSpatialRelIntersects",
        "distance": str(int(radius_km * 1000)),
        "units": "esriSRUnit_Meter",
        "where": f"LatestEventStart >= CURRENT_TIMESTAMP - INTERVAL '{lookback_hours}' HOUR",
        "outFields": "*",
        "f": "geojson",
    })
    url = f"{ARCGIS_URL}?{params}"
    try:
        with urllib.request.urlopen(url) as resp:
            data = json.loads(resp.read())
        return data.get("features", [])
    except Exception as exc:
        print(f"ERROR: Could not query ArcGIS API: {exc}", file=sys.stderr)
        sys.exit(1)
```

- [ ] **Step 4: Run tests to confirm they pass**

```bash
pytest tests/test_check_spills.py::TestQuerySpills -v
```

Expected: 4 passed.

- [ ] **Step 5: Commit**

```bash
git add check_spills.py tests/test_check_spills.py
git commit -m "feat: add ArcGIS spill query with server-side spatial and time filters"
```

---

## Task 6: Spill row formatting

**Files:**
- Modify: `check_spills.py` — add `format_spill_row`
- Modify: `tests/test_check_spills.py` — add tests

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_check_spills.py`:

```python
class TestFormatSpillRow:
    def test_all_fields_present(self):
        row = check_spills.format_spill_row(SAMPLE_FEATURE, 51.745, -2.216)
        assert row["site_id"] == "SVT00291"
        assert row["watercourse"] == "RIVER SEVERN"
        assert isinstance(row["distance_km"], float)
        assert row["distance_km"] < 20
        assert "UTC" in row["started"]
        assert "UTC" in row["ended"]

    def test_ongoing_when_end_is_none(self):
        feature = {
            "properties": {
                **SAMPLE_FEATURE["properties"],
                "LatestEventEnd": None,
            }
        }
        row = check_spills.format_spill_row(feature, 51.745, -2.216)
        assert row["ended"] == "Ongoing"

    def test_ongoing_when_end_is_zero(self):
        feature = {
            "properties": {
                **SAMPLE_FEATURE["properties"],
                "LatestEventEnd": 0,
            }
        }
        row = check_spills.format_spill_row(feature, 51.745, -2.216)
        assert row["ended"] == "Ongoing"
```

- [ ] **Step 2: Run tests to confirm failure**

```bash
pytest tests/test_check_spills.py::TestFormatSpillRow -v
```

Expected: `AttributeError: module 'check_spills' has no attribute 'format_spill_row'`

- [ ] **Step 3: Implement `format_spill_row` in `check_spills.py`**

```python
def _fmt_epoch_ms(epoch_ms) -> str:
    """Format an epoch-millisecond timestamp as a UTC string, or 'Ongoing' if falsy."""
    if not epoch_ms:
        return "Ongoing"
    dt = datetime.fromtimestamp(epoch_ms / 1000, tz=timezone.utc)
    return dt.strftime("%Y-%m-%d %H:%M UTC")


def format_spill_row(feature: dict, home_lat: float, home_lon: float) -> dict:
    """Return a display-ready dict for one spill feature."""
    props = feature["properties"]
    distance = haversine_km(home_lat, home_lon, props["Latitude"], props["Longitude"])
    return {
        "site_id": props["Id"],
        "watercourse": props["ReceivingWaterCourse"],
        "distance_km": round(distance, 1),
        "started": _fmt_epoch_ms(props.get("LatestEventStart")),
        "ended": _fmt_epoch_ms(props.get("LatestEventEnd")),
    }
```

- [ ] **Step 4: Run tests to confirm they pass**

```bash
pytest tests/test_check_spills.py::TestFormatSpillRow -v
```

Expected: 3 passed.

- [ ] **Step 5: Commit**

```bash
git add check_spills.py tests/test_check_spills.py
git commit -m "feat: add spill row formatting with haversine display distance"
```

---

## Task 7: Email content builders

**Files:**
- Modify: `check_spills.py` — add `build_html_email`, `build_text_email`
- Modify: `tests/test_check_spills.py` — add tests

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_check_spills.py`:

```python
SAMPLE_ROWS = [
    {
        "site_id": "SVT001",
        "watercourse": "RIVER TEST",
        "distance_km": 5.3,
        "started": "2026-03-17 10:00 UTC",
        "ended": "Ongoing",
    }
]


class TestBuildHtmlEmail:
    def test_subject_contains_count_and_postcode(self):
        subject, _ = check_spills.build_html_email(SAMPLE_ROWS, "GL5 1HE", 20)
        assert "1" in subject
        assert "GL5 1HE" in subject

    def test_html_contains_all_row_fields(self):
        _, html = check_spills.build_html_email(SAMPLE_ROWS, "GL5 1HE", 20)
        assert "SVT001" in html
        assert "RIVER TEST" in html
        assert "5.3" in html
        assert "2026-03-17 10:00 UTC" in html
        assert "Ongoing" in html

    def test_html_is_valid_table(self):
        _, html = check_spills.build_html_email(SAMPLE_ROWS, "GL5 1HE", 20)
        assert "<table" in html
        assert "<tr>" in html or "<tr " in html
        assert "<th>" in html or "<th " in html


class TestBuildTextEmail:
    def test_contains_all_row_fields(self):
        text = check_spills.build_text_email(SAMPLE_ROWS, "GL5 1HE", 20)
        assert "SVT001" in text
        assert "RIVER TEST" in text
        assert "Ongoing" in text
        assert "GL5 1HE" in text
```

- [ ] **Step 2: Run tests to confirm failure**

```bash
pytest tests/test_check_spills.py::TestBuildHtmlEmail tests/test_check_spills.py::TestBuildTextEmail -v
```

Expected: `AttributeError` for missing functions.

- [ ] **Step 3: Implement `build_html_email` and `build_text_email` in `check_spills.py`**

```python
def build_html_email(rows: list, postcode: str, radius_km: float) -> tuple[str, str]:
    """Return (subject, html_body) for the spill alert email."""
    count = len(rows)
    subject = f"Sewage alert: {count} spill(s) within {radius_km}km of {postcode}"
    rows_html = "\n".join(
        f"<tr><td>{r['site_id']}</td><td>{r['watercourse']}</td>"
        f"<td>{r['distance_km']}</td><td>{r['started']}</td><td>{r['ended']}</td></tr>"
        for r in rows
    )
    html = f"""<html><body>
<p>{count} sewage overflow event(s) started near {postcode} in the last check window.</p>
<table border="1" cellpadding="4" cellspacing="0">
  <thead>
    <tr>
      <th>Site ID</th><th>Watercourse</th><th>Distance (km)</th>
      <th>Event started</th><th>Event ended</th>
    </tr>
  </thead>
  <tbody>
    {rows_html}
  </tbody>
</table>
<p><small>Source: Severn Trent Water Storm Overflow Activity</small></p>
</body></html>"""
    return subject, html


def build_text_email(rows: list, postcode: str, radius_km: float) -> str:
    """Return plain-text body for the spill alert email."""
    count = len(rows)
    lines = [f"{count} sewage overflow event(s) near {postcode} (within {radius_km}km):\n"]
    for r in rows:
        lines.append(
            f"- {r['site_id']} | {r['watercourse']} | {r['distance_km']}km "
            f"| Started: {r['started']} | Ended: {r['ended']}"
        )
    lines.append("\nSource: Severn Trent Water Storm Overflow Activity")
    return "\n".join(lines)
```

- [ ] **Step 4: Run tests to confirm they pass**

```bash
pytest tests/test_check_spills.py::TestBuildHtmlEmail tests/test_check_spills.py::TestBuildTextEmail -v
```

Expected: 7 passed.

- [ ] **Step 5: Commit**

```bash
git add check_spills.py tests/test_check_spills.py
git commit -m "feat: add HTML and plain-text email builders"
```

---

## Task 8: Email sending via Gmail SMTP

**Files:**
- Modify: `check_spills.py` — add `send_email`
- Modify: `tests/test_check_spills.py` — add tests

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_check_spills.py`:

```python
class TestSendEmail:
    def test_calls_smtp_login_and_sendmail(self):
        mock_server = MagicMock()
        mock_smtp_cm = MagicMock()
        mock_smtp_cm.__enter__.return_value = mock_server
        mock_smtp_cm.__exit__.return_value = False

        with patch("smtplib.SMTP_SSL", return_value=mock_smtp_cm) as mock_smtp:
            check_spills.send_email(
                subject="Test subject",
                html="<p>html</p>",
                text="plain text",
                to_addr="to@example.com",
                from_addr="from@gmail.com",
                password="app_password",
            )

        mock_smtp.assert_called_once_with("smtp.gmail.com", 465)
        mock_server.login.assert_called_once_with("from@gmail.com", "app_password")
        mock_server.sendmail.assert_called_once()
        args = mock_server.sendmail.call_args[0]
        assert args[0] == "from@gmail.com"
        assert args[1] == "to@example.com"

    def test_exits_on_smtp_error(self):
        with patch("smtplib.SMTP_SSL", side_effect=Exception("connection refused")):
            with pytest.raises(SystemExit):
                check_spills.send_email(
                    "subj", "<p>html</p>", "text",
                    "to@example.com", "from@gmail.com", "pw",
                )
```

- [ ] **Step 2: Run tests to confirm failure**

```bash
pytest tests/test_check_spills.py::TestSendEmail -v
```

Expected: `AttributeError: module 'check_spills' has no attribute 'send_email'`

- [ ] **Step 3: Implement `send_email` in `check_spills.py`**

```python
def send_email(
    subject: str,
    html: str,
    text: str,
    to_addr: str,
    from_addr: str,
    password: str,
) -> None:
    """Send a multipart HTML/text email via Gmail SMTP SSL."""
    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = from_addr
    msg["To"] = to_addr
    msg.attach(MIMEText(text, "plain"))
    msg.attach(MIMEText(html, "html"))
    try:
        with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
            server.login(from_addr, password)
            server.sendmail(from_addr, to_addr, msg.as_string())
    except Exception as exc:
        print(f"ERROR: Could not send email: {exc}", file=sys.stderr)
        sys.exit(1)
```

- [ ] **Step 4: Run tests to confirm they pass**

```bash
pytest tests/test_check_spills.py::TestSendEmail -v
```

Expected: 2 passed.

- [ ] **Step 5: Confirm all tests still pass**

```bash
pytest tests/test_check_spills.py -v
```

Expected: all tests pass.

- [ ] **Step 6: Commit**

```bash
git add check_spills.py tests/test_check_spills.py
git commit -m "feat: add Gmail SMTP email sending"
```

---

## Task 9: Main orchestration

**Files:**
- Modify: `check_spills.py` — add `main()`
- Modify: `tests/test_check_spills.py` — add integration tests

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_check_spills.py`:

```python
class TestMain:
    BASE_CONFIG = {
        "postcode": "GL5 1HE",
        "radius_km": 20,
        "lookback_hours": 24,
        "notify_email": "user@example.com",
    }

    def test_no_email_when_no_spills(self, tmp_path):
        config_file = tmp_path / "config.yml"
        import yaml as _yaml
        config_file.write_text(_yaml.dump(self.BASE_CONFIG))

        empty_features = {"type": "FeatureCollection", "features": []}
        postcode_payload = {"status": 200, "result": {"latitude": 51.745, "longitude": -2.216}}

        call_count = [0]

        def fake_urlopen(url, **kwargs):
            call_count[0] += 1
            if "postcodes.io" in url:
                return _mock_urlopen(postcode_payload)
            return _mock_urlopen(empty_features)

        with patch("urllib.request.urlopen", side_effect=fake_urlopen), \
             patch("smtplib.SMTP_SSL") as mock_smtp, \
             patch.dict("os.environ", {"GMAIL_ADDRESS": "sender@gmail.com", "GMAIL_APP_PASSWORD": "pw"}):
            check_spills.main(config_path=str(config_file))

        mock_smtp.assert_not_called()

    def test_sends_email_when_spills_found(self, tmp_path):
        config_file = tmp_path / "config.yml"
        import yaml as _yaml
        config_file.write_text(_yaml.dump(self.BASE_CONFIG))

        features_payload = {"type": "FeatureCollection", "features": [SAMPLE_FEATURE]}
        postcode_payload = {"status": 200, "result": {"latitude": 51.745, "longitude": -2.216}}

        def fake_urlopen(url, **kwargs):
            if "postcodes.io" in url:
                return _mock_urlopen(postcode_payload)
            return _mock_urlopen(features_payload)

        mock_server = MagicMock()
        mock_smtp_cm = MagicMock()
        mock_smtp_cm.__enter__.return_value = mock_server
        mock_smtp_cm.__exit__.return_value = False

        with patch("urllib.request.urlopen", side_effect=fake_urlopen), \
             patch("smtplib.SMTP_SSL", return_value=mock_smtp_cm), \
             patch.dict("os.environ", {"GMAIL_ADDRESS": "sender@gmail.com", "GMAIL_APP_PASSWORD": "pw"}):
            check_spills.main(config_path=str(config_file))

        mock_server.sendmail.assert_called_once()
```

- [ ] **Step 2: Run tests to confirm failure**

```bash
pytest tests/test_check_spills.py::TestMain -v
```

Expected: `TypeError: main() got an unexpected keyword argument 'config_path'`

- [ ] **Step 3: Implement `main()` in `check_spills.py`, replacing the `pass` in `if __name__ == "__main__":`**

```python
def main(config_path: str = "config.yml") -> None:
    config = load_config(config_path)
    postcode = config["postcode"]
    radius_km = config["radius_km"]
    lookback_hours = config["lookback_hours"]
    notify_email = config["notify_email"]

    validate_lookback_hours(lookback_hours)

    home_lat, home_lon = get_postcode_coords(postcode)
    features = query_spills(home_lat, home_lon, radius_km, lookback_hours)

    if not features:
        print(f"No spills found within {radius_km}km of {postcode} in the last {lookback_hours}h.")
        return

    rows = [format_spill_row(f, home_lat, home_lon) for f in features]
    subject, html = build_html_email(rows, postcode, radius_km)
    text = build_text_email(rows, postcode, radius_km)

    from_addr = os.environ["GMAIL_ADDRESS"]
    password = os.environ["GMAIL_APP_PASSWORD"]

    send_email(subject, html, text, notify_email, from_addr, password)
    print(f"Alert sent: {subject}")


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Run all tests to confirm they pass**

```bash
pytest tests/test_check_spills.py -v
```

Expected: all tests pass.

- [ ] **Step 5: Commit**

```bash
git add check_spills.py tests/test_check_spills.py
git commit -m "feat: add main orchestration function"
```

---

## Task 10: GitHub Actions workflow

**Files:**
- Create: `.github/workflows/check_spills.yml`

- [ ] **Step 1: Create the workflow directory**

```bash
mkdir -p .github/workflows
```

- [ ] **Step 2: Create `.github/workflows/check_spills.yml`**

```yaml
name: Check sewage spills

on:
  schedule:
    - cron: '0 7 * * *'   # daily at 07:00 UTC — keep in sync with lookback_hours in config.yml
  workflow_dispatch:        # allows manual trigger for testing

jobs:
  check:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - uses: actions/setup-python@v5
        with:
          python-version: '3.12'

      - name: Install dependencies
        run: pip install -r requirements.txt

      - name: Check for nearby spills
        run: python check_spills.py
        env:
          GMAIL_ADDRESS: ${{ secrets.GMAIL_ADDRESS }}
          GMAIL_APP_PASSWORD: ${{ secrets.GMAIL_APP_PASSWORD }}
```

- [ ] **Step 3: Commit**

```bash
git add .github/workflows/check_spills.yml
git commit -m "feat: add GitHub Actions cron workflow"
```

---

## Task 11: configure.py interactive setup

**Files:**
- Modify: `configure.py` — full implementation
- Create: `tests/test_configure.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/test_configure.py`:

```python
import re
import pytest
import yaml
import configure


class TestBuildCronAndHours:
    def test_choice_1_every_6h(self):
        cron, hours = configure.build_cron_and_hours(1, hour=None)
        assert cron == "0 */6 * * *"
        assert hours == 6

    def test_choice_2_every_12h(self):
        cron, hours = configure.build_cron_and_hours(2, hour=None)
        assert cron == "0 */12 * * *"
        assert hours == 12

    def test_choice_3_daily_default_hour(self):
        cron, hours = configure.build_cron_and_hours(3, hour=7)
        assert cron == "0 7 * * *"
        assert hours == 24

    def test_choice_3_daily_custom_hour(self):
        cron, hours = configure.build_cron_and_hours(3, hour=8)
        assert cron == "0 8 * * *"
        assert hours == 24


class TestPatchWorkflowCron:
    def test_patches_cron_expression(self, tmp_path):
        workflow = tmp_path / "check_spills.yml"
        workflow.write_text("    - cron: '0 7 * * *'\n")
        configure.patch_workflow_cron("0 */6 * * *", str(workflow))
        result = workflow.read_text()
        assert "0 */6 * * *" in result
        assert "0 7 * * *" not in result

    def test_leaves_rest_of_file_intact(self, tmp_path):
        workflow = tmp_path / "check_spills.yml"
        workflow.write_text("name: foo\n    - cron: '0 7 * * *'\njobs:\n")
        configure.patch_workflow_cron("0 */12 * * *", str(workflow))
        result = workflow.read_text()
        assert "name: foo" in result
        assert "jobs:" in result


class TestWriteConfig:
    def test_writes_all_fields(self, tmp_path):
        config_path = str(tmp_path / "config.yml")
        configure.write_config(
            postcode="SW1A 1AA",
            radius_km=15,
            lookback_hours=12,
            notify_email="test@example.com",
            path=config_path,
        )
        with open(config_path) as f:
            result = yaml.safe_load(f)
        assert result["postcode"] == "SW1A 1AA"
        assert result["radius_km"] == 15
        assert result["lookback_hours"] == 12
        assert result["notify_email"] == "test@example.com"
```

- [ ] **Step 2: Run tests to confirm failure**

```bash
pytest tests/test_configure.py -v
```

Expected: `ImportError` or `AttributeError` for missing functions.

- [ ] **Step 3: Implement `configure.py` fully**

```python
#!/usr/bin/env python3
"""Interactive setup script for sewage alerts."""

import re
import sys
import yaml

WORKFLOW_PATH = ".github/workflows/check_spills.yml"
CONFIG_PATH = "config.yml"


def build_cron_and_hours(choice: int, hour: int) -> tuple[str, int]:
    """Return (cron_expression, lookback_hours) for the given menu choice."""
    if choice == 1:
        return "0 */6 * * *", 6
    elif choice == 2:
        return "0 */12 * * *", 12
    elif choice == 3:
        return f"0 {hour} * * *", 24
    else:
        print("Invalid choice, defaulting to daily at 07:00 UTC.", file=sys.stderr)
        return "0 7 * * *", 24


def patch_workflow_cron(cron_expr: str, workflow_path: str = WORKFLOW_PATH) -> None:
    """Replace the cron expression in the workflow YAML file."""
    with open(workflow_path) as f:
        content = f.read()
    new_content = re.sub(
        r"(- cron: ')[^']+(')",
        rf"\g<1>{cron_expr}\g<2>",
        content,
    )
    with open(workflow_path, "w") as f:
        f.write(new_content)


def write_config(
    postcode: str,
    radius_km: int,
    lookback_hours: int,
    notify_email: str,
    path: str = CONFIG_PATH,
) -> None:
    """Write configuration to a YAML file."""
    config = {
        "postcode": postcode,
        "radius_km": radius_km,
        "lookback_hours": lookback_hours,
        "notify_email": notify_email,
    }
    with open(path, "w") as f:
        yaml.dump(config, f, default_flow_style=False)


def _prompt(message: str, default: str = "") -> str:
    suffix = f" [{default}]" if default else ""
    value = input(f"{message}{suffix}: ").strip()
    return value or default


def main() -> None:
    print("Welcome to Sewage Alerts setup!\n")

    try:
        with open(CONFIG_PATH) as f:
            existing = yaml.safe_load(f) or {}
    except FileNotFoundError:
        existing = {}

    postcode = _prompt("Postcode", existing.get("postcode", "GL5 1HE"))
    notify_email = _prompt("Notification email", existing.get("notify_email", ""))
    radius_km = int(_prompt("Search radius (km)", str(existing.get("radius_km", 20))))

    print("\nCheck interval:")
    print("  1) Every 6 hours")
    print("  2) Every 12 hours")
    print("  3) Daily (default)")
    print("  4) Custom cron expression")
    choice_str = input("Choice [3]: ").strip() or "3"
    choice = int(choice_str)

    if choice == 4:
        cron_expr = input("Cron expression (e.g. 0 */8 * * *): ").strip()
        lookback_hours = int(input("Corresponding lookback_hours: ").strip())
    else:
        hour = 7
        if choice == 3:
            hour = int(_prompt("Hour to run (UTC, 0-23)", "7"))
        cron_expr, lookback_hours = build_cron_and_hours(choice, hour=hour)

    write_config(postcode, radius_km, lookback_hours, notify_email)
    print(f"\n✓ Written {CONFIG_PATH}")

    patch_workflow_cron(cron_expr)
    print(f"✓ Updated {WORKFLOW_PATH}")

    print(f"""
Setup complete! Run these commands to finish:

  gh secret set GMAIL_ADDRESS
  gh secret set GMAIL_APP_PASSWORD

Then push and test:

  git add {CONFIG_PATH} {WORKFLOW_PATH}
  git commit -m "configure sewage alerts"
  git push
  gh workflow run check_spills.yml
""")


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Run tests to confirm they pass**

```bash
pytest tests/test_configure.py -v
```

Expected: all tests pass.

- [ ] **Step 5: Run all tests**

```bash
pytest tests/ -v
```

Expected: all tests pass.

- [ ] **Step 6: Commit**

```bash
git add configure.py tests/test_configure.py
git commit -m "feat: add interactive configure.py setup script"
```

---

## Task 12: README

**Files:**
- Create: `README.md`

- [ ] **Step 1: Create `README.md`**

```markdown
# Sewage Alerts

Emails you when sewage overflow events start near your home. Runs automatically on a schedule using GitHub Actions.

> **Geographic note:** This tool uses Severn Trent Water's dataset and only covers their service area (broadly the Midlands and parts of the East of England). If your postcode is outside this area, the script will run without error but will never find events.

## Prerequisites

- Python 3.9 or later installed on your computer
- A Gmail account

## Setup

### 1. Create a GitHub account

Sign up at [github.com/signup](https://github.com/signup) if you don't have one.

### 2. Install the GitHub CLI

Follow the instructions at [cli.github.com](https://cli.github.com) for your operating system.

### 3. Log in to GitHub

```bash
gh auth login
```

Follow the prompts. Choose "GitHub.com" and "HTTPS" when asked.

### 4. Fork and clone this repository

```bash
gh repo fork <REPO_URL> --clone && cd sewage-alerts
```

### 5. Enable GitHub Actions on your fork

Go to your forked repository on github.com → click the **Actions** tab → click **"I understand my workflows, go ahead and enable them"**.

### 6. Create a Gmail App Password

You'll need this in the next step.

1. Go to your [Google Account](https://myaccount.google.com) → **Security**
2. Under "How you sign in to Google", click **2-Step Verification** (enable it if not already on)
3. Scroll to the bottom and click **App passwords**
4. Name it "Sewage Alerts" and click **Create**
5. Copy the 16-character password shown — you'll need it shortly

### 7. Run the setup script

```bash
python configure.py
```

Follow the prompts to enter your postcode, email address, and preferred check interval.

### 8. Run the commands printed by the setup script

The script will print something like:

```
  gh secret set GMAIL_ADDRESS
  gh secret set GMAIL_APP_PASSWORD

  git add config.yml .github/workflows/check_spills.yml
  git commit -m "configure sewage alerts"
  git push
  gh workflow run check_spills.yml
```

Copy and run each command. When prompted by `gh secret set`, paste the value (your Gmail address or App Password).

The last command triggers an immediate test run. You can watch it at:
`https://github.com/<your-username>/sewage-alerts/actions`

If spills are found near you, you'll receive an email. If not, the workflow will complete silently — that's normal.

## Configuration

Edit `config.yml` to change settings:

```yaml
postcode: "GL5 1HE"     # Your home postcode
radius_km: 20            # Search radius in kilometres
lookback_hours: 24       # How far back to look for new spills
notify_email: "you@gmail.com"  # Where to send alerts
```

After editing, commit and push:

```bash
git add config.yml
git commit -m "update config"
git push
```

To change the schedule, run `python configure.py` again.

## How it works

1. The workflow runs on your configured schedule
2. It looks up your postcode's coordinates via [postcodes.io](https://postcodes.io)
3. It queries Severn Trent Water's live overflow data for events that **started** within `lookback_hours` and within `radius_km` of your home
4. If any are found, it sends you an HTML email with a table of nearby spills
5. If none are found, it exits silently — no email is sent
```

- [ ] **Step 2: Commit**

```bash
git add README.md
git commit -m "docs: add user setup README"
```

---

## Final verification

- [ ] **Run the full test suite**

```bash
pytest tests/ -v
```

Expected: all tests pass.

- [ ] **Smoke test the script (no credentials needed — just verify imports and config load)**

```bash
python -c "import check_spills; cfg = check_spills.load_config(); print(cfg)"
```

Expected: prints the config dict without errors.

- [ ] **Verify configure.py imports cleanly**

```bash
python -c "import configure; print('OK')"
```

Expected: `OK`
