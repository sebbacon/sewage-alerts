# Multi-Company Support Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Extend the sewage alerts tool to query all 9 England/Wales water companies so any UK postcode works, not just those in the Severn Trent area.

**Architecture:** A new `companies.yml` file lists all 9 ArcGIS FeatureServer endpoints. `check_spills.py` loads this file, queries every company's API with the same spatial+time filter, and aggregates results. Per-company failures are caught individually; if any fail the action exits non-zero and the user is notified by email.

**Tech Stack:** Python 3.9+ stdlib only (no new dependencies). Pytest for tests. ArcGIS FeatureServer REST API (GeoJSON). Simple line-based YAML parser (same pattern as `load_config`).

---

## File Structure

| File | Role |
|---|---|
| `companies.yml` | New — lists all 9 company names + query URLs |
| `check_spills.py` | All changes: `load_companies()`, updated `query_spills()`, updated `format_spill_row()`, updated email builders, updated `main()` |
| `tests/test_check_spills.py` | New and updated tests for all changed functions |
| `README.md` | Remove Severn Trent–only geographic note |

---

### Task 1: Create `companies.yml`

**Files:**
- Create: `companies.yml`

- [ ] **Step 1: Create the file**

```yaml
# Endpoints discovered 2026-03-18 via ArcGIS Online public search API:
#   https://www.arcgis.com/sharing/rest/search?q=Storm_Overflow_Activity&f=json&num=20
# All 9 use the same ArcGIS FeatureServer REST API and INTERVAL SQL syntax.
# ArcGIS SQL WHERE clauses are case-insensitive for field names.
# South West Water uses camelCase field names in responses; all others use PascalCase.
# Field normalisation is handled in check_spills.py.
# Scottish Water (services3.arcgis.com/Bb8lfThdhugyc4G3) is intentionally excluded —
# it is not part of the England/Wales streamwaterdata.co.uk data hub.
companies:
  - name: Anglian Water
    query_url: https://services3.arcgis.com/VCOY1atHWVcDlvlJ/arcgis/rest/services/stream_service_outfall_locations_view/FeatureServer/0/query
  - name: Northumbrian Water
    query_url: https://services-eu1.arcgis.com/MSNNjkZ51iVh8yBj/arcgis/rest/services/Northumbrian_Water_Storm_Overflow_Activity_2_view/FeatureServer/0/query
  - name: Severn Trent Water
    query_url: https://services1.arcgis.com/NO7lTIlnxRMMG9Gw/arcgis/rest/services/Severn_Trent_Water_Storm_Overflow_Activity/FeatureServer/0/query
  - name: South West Water
    query_url: https://services-eu1.arcgis.com/OMdMOtfhATJPcHe3/arcgis/rest/services/NEH_outlets_PROD/FeatureServer/0/query
  - name: Southern Water
    query_url: https://services-eu1.arcgis.com/XxS6FebPX29TRGDJ/arcgis/rest/services/Southern_Water_Storm_Overflow_Activity/FeatureServer/0/query
  - name: Thames Water
    query_url: https://services2.arcgis.com/g6o32ZDQ33GpCIu3/arcgis/rest/services/Thames_Water_Storm_Overflow_Activity_(Production)_view/FeatureServer/0/query
  - name: United Utilities
    query_url: https://services5.arcgis.com/5eoLvR0f8HKb7HWP/arcgis/rest/services/United_Utilities_Storm_Overflow_Activity/FeatureServer/0/query
  - name: Wessex Water
    query_url: https://services.arcgis.com/3SZ6e0uCvPROr4mS/arcgis/rest/services/Wessex_Water_Storm_Overflow_Activity/FeatureServer/0/query
  - name: Yorkshire Water
    query_url: https://services-eu1.arcgis.com/1WqkK5cDKUbF0CkH/arcgis/rest/services/Yorkshire_Water_Storm_Overflow_Activity/FeatureServer/0/query
```

- [ ] **Step 2: Commit**

```bash
git add companies.yml
git commit -m "feat: add companies.yml with all 9 England/Wales water company endpoints"
```

---

### Task 2: `load_companies()` — parse companies.yml

**Files:**
- Modify: `requirements-dev.txt`
- Modify: `check_spills.py` (add after `load_config`, around line 56)
- Modify: `tests/test_check_spills.py` (add `TestLoadCompanies` class after `TestLoadConfig`)

- [ ] **Step 1: Add `pyyaml` to `requirements-dev.txt`**

`import yaml` is already at the top of `tests/test_check_spills.py` and is used by `TestMain._write_config`. It must be listed explicitly so `uv pip install -r requirements-dev.txt` installs it in clean environments.

Replace the contents of `requirements-dev.txt` with:

```
pytest>=8,<10
pyyaml>=6
```

Then run:

```bash
uv pip install -r requirements-dev.txt -q
```

- [ ] **Step 2: Write the failing test**

Add this class to `tests/test_check_spills.py` after `TestLoadConfig`:

```python
class TestLoadCompanies:
    def test_loads_all_companies(self, tmp_path):
        f = tmp_path / "companies.yml"
        f.write_text(
            "companies:\n"
            "  - name: Anglian Water\n"
            "    query_url: https://example.com/anglian/query\n"
            "  - name: Thames Water\n"
            "    query_url: https://example.com/thames/query\n"
        )
        result = check_spills.load_companies(str(f))
        assert len(result) == 2
        assert result[0] == {
            "name": "Anglian Water",
            "query_url": "https://example.com/anglian/query",
        }
        assert result[1] == {
            "name": "Thames Water",
            "query_url": "https://example.com/thames/query",
        }

    def test_ignores_comments_and_header(self, tmp_path):
        f = tmp_path / "companies.yml"
        f.write_text(
            "# This is a comment\n"
            "companies:\n"
            "  - name: Test Water\n"
            "    query_url: https://example.com/query\n"
        )
        result = check_spills.load_companies(str(f))
        assert len(result) == 1
        assert result[0]["name"] == "Test Water"
```

- [ ] **Step 2: Run test to verify it fails**

```bash
uv run pytest tests/test_check_spills.py::TestLoadCompanies -v
```

Expected: `FAILED` — `AttributeError: module 'check_spills' has no attribute 'load_companies'`

- [ ] **Step 3: Implement `load_companies()`**

Add this function to `check_spills.py` directly after `load_config()` (after line 56):

```python
def load_companies(path: str = "companies.yml") -> list[dict]:
    """Load water company endpoint list from a YAML file."""
    companies = []
    current: dict = {}
    with open(path) as f:
        for line in f:
            stripped = line.strip()
            if stripped.startswith("#") or stripped in ("", "companies:"):
                continue
            if stripped.startswith("- name:"):
                if current:
                    companies.append(current)
                current = {"name": stripped[len("- name:"):].strip()}
            elif stripped.startswith("query_url:"):
                current["query_url"] = stripped[len("query_url:"):].strip()
    if current:
        companies.append(current)
    return companies
```

- [ ] **Step 4: Run test to verify it passes**

```bash
uv run pytest tests/test_check_spills.py::TestLoadCompanies -v
```

Expected: `2 passed`

- [ ] **Step 5: Run full suite to confirm no regressions**

```bash
uv run pytest tests/ -v
```

Expected: all tests pass.

- [ ] **Step 6: Commit**

```bash
git add check_spills.py tests/test_check_spills.py
git commit -m "feat: add load_companies() with tests"
```

---

### Task 3: Update `query_spills()` — add `query_url` parameter, raise instead of exit

**Files:**
- Modify: `check_spills.py` lines 82–102
- Modify: `tests/test_check_spills.py` — `TestQuerySpills` class

The `ARCGIS_URL` constant (lines 26–29) is removed. `query_spills` takes a `query_url` parameter instead.

- [ ] **Step 1: Update `TestQuerySpills` tests first**

Replace the entire `TestQuerySpills` class in `tests/test_check_spills.py`:

```python
FAKE_QUERY_URL = "https://fake.arcgis.com/FeatureServer/0/query"


class TestQuerySpills:
    def test_returns_features_list(self):
        payload = {"type": "FeatureCollection", "features": [SAMPLE_FEATURE]}
        with patch("urllib.request.urlopen", return_value=_mock_urlopen(payload)):
            features = check_spills.query_spills(51.745, -2.216, 20, 24, FAKE_QUERY_URL)
        assert len(features) == 1
        assert features[0]["properties"]["Id"] == "SVT00291"

    def test_returns_empty_list_when_no_results(self):
        payload = {"type": "FeatureCollection", "features": []}
        with patch("urllib.request.urlopen", return_value=_mock_urlopen(payload)):
            features = check_spills.query_spills(51.745, -2.216, 20, 24, FAKE_QUERY_URL)
        assert features == []

    def test_raises_on_network_error(self):
        with patch("urllib.request.urlopen", side_effect=Exception("network error")):
            with pytest.raises(RuntimeError, match="network error"):
                check_spills.query_spills(51.745, -2.216, 20, 24, FAKE_QUERY_URL)

    def test_url_contains_interval_and_distance(self):
        payload = {"type": "FeatureCollection", "features": []}
        captured_url = []

        def capturing_urlopen(url, **kwargs):
            captured_url.append(url)
            return _mock_urlopen(payload)

        with patch("urllib.request.urlopen", side_effect=capturing_urlopen):
            check_spills.query_spills(51.745, -2.216, 20, 24, FAKE_QUERY_URL)

        url = captured_url[0]
        assert "INTERVAL" in url
        assert "24" in url
        assert "20000" in url
        assert "esriSRUnit_Meter" in url
        assert FAKE_QUERY_URL in url
```

- [ ] **Step 2: Run tests to confirm they fail for the right reason**

```bash
uv run pytest tests/test_check_spills.py::TestQuerySpills -v
```

Expected: failures mentioning wrong number of arguments or missing `query_url`.

- [ ] **Step 3: Update `query_spills()` in `check_spills.py`**

Remove the `ARCGIS_URL` constant (lines 26–29). Replace `query_spills` (lines 82–102) with:

```python
def query_spills(lat: float, lon: float, radius_km: float, lookback_hours: int, query_url: str) -> list:
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
    url = f"{query_url}?{params}"
    try:
        with urllib.request.urlopen(url) as resp:
            data = json.loads(resp.read())
        return data.get("features", [])
    except Exception as exc:
        raise RuntimeError(f"ArcGIS query failed: {exc}") from exc
```

- [ ] **Step 4: Run `TestQuerySpills` to verify all pass**

```bash
uv run pytest tests/test_check_spills.py::TestQuerySpills -v
```

Expected: `4 passed`

- [ ] **Step 5: Run full suite to check for regressions**

```bash
uv run pytest tests/ -v
```

Expected: `TestMain` tests will fail because `main()` still calls `query_spills` without `query_url`. That's fine — we fix `main()` in Task 6. All other tests should pass.

- [ ] **Step 6: Commit**

```bash
git add check_spills.py tests/test_check_spills.py
git commit -m "feat: add query_url param to query_spills(), raise instead of exit on error"
```

---

### Task 4: Update `format_spill_row()` — geometry coords, field normalisation, `company` arg

**Files:**
- Modify: `check_spills.py` lines 113–123
- Modify: `tests/test_check_spills.py` — `SAMPLE_FEATURE`, `SAMPLE_ROWS`, `TestFormatSpillRow`

Key changes:
- 4th argument `company: str` added
- Distance uses `feature["geometry"]["coordinates"]` (`[lon, lat]`) instead of `props["Latitude"]`/`props["Longitude"]`
- Watercourse normalised: `props.get("ReceivingWaterCourse") or props.get("receivingWaterCourse")`
- Event fields normalised: `props.get("LatestEventStart") or props.get("latestEventStart")` etc.
- `"company": company` added to returned dict

- [ ] **Step 1: Update test fixtures and `TestFormatSpillRow`**

`SAMPLE_FEATURE` already has a `geometry` key — no change needed there.

Add `SAMPLE_FEATURE_SOUTH_WEST` after `SAMPLE_FEATURE`:

```python
SAMPLE_FEATURE_SOUTH_WEST = {
    "type": "Feature",
    "geometry": {"type": "Point", "coordinates": [-4.826, 50.514]},
    "properties": {
        "Id": "SBB00407",
        "receivingWaterCourse": "CAMEL ESTUARY",
        # South West Water uses camelCase; coordinates come from geometry, not properties
        "latestEventStart": 1773224866000,
        "latestEventEnd": 1773224876000,
    },
}
```

Update `SAMPLE_ROWS` to add `"company"` field:

```python
SAMPLE_ROWS = [
    {
        "site_id": "SVT001",
        "company": "Test Water Co",
        "watercourse": "RIVER TEST",
        "distance_km": 5.3,
        "started": "2026-03-17 10:00 UTC",
        "ended": "Ongoing",
    }
]
```

Replace `TestFormatSpillRow` with:

```python
class TestFormatSpillRow:
    def test_all_fields_present(self):
        row = check_spills.format_spill_row(SAMPLE_FEATURE, 51.745, -2.216, "Severn Trent Water")
        assert row["site_id"] == "SVT00291"
        assert row["company"] == "Severn Trent Water"
        assert row["watercourse"] == "RIVER SEVERN"
        assert isinstance(row["distance_km"], float)
        assert row["distance_km"] < 20
        assert "UTC" in row["started"]
        assert "UTC" in row["ended"]

    def test_ongoing_when_end_is_none(self):
        feature = {
            "geometry": SAMPLE_FEATURE["geometry"],
            "properties": {
                **SAMPLE_FEATURE["properties"],
                "LatestEventEnd": None,
            },
        }
        row = check_spills.format_spill_row(feature, 51.745, -2.216, "Test Co")
        assert row["ended"] == "Ongoing"

    def test_ongoing_when_end_is_zero(self):
        feature = {
            "geometry": SAMPLE_FEATURE["geometry"],
            "properties": {
                **SAMPLE_FEATURE["properties"],
                "LatestEventEnd": 0,
            },
        }
        row = check_spills.format_spill_row(feature, 51.745, -2.216, "Test Co")
        assert row["ended"] == "Ongoing"

    def test_camelcase_fields_normalised(self):
        row = check_spills.format_spill_row(SAMPLE_FEATURE_SOUTH_WEST, 51.745, -2.216, "South West Water")
        assert row["site_id"] == "SBB00407"
        assert row["company"] == "South West Water"
        assert row["watercourse"] == "CAMEL ESTUARY"
        assert "UTC" in row["started"]
        assert "UTC" in row["ended"]
```

- [ ] **Step 2: Run tests to confirm they fail**

```bash
uv run pytest tests/test_check_spills.py::TestFormatSpillRow -v
```

Expected: failures about wrong number of arguments.

- [ ] **Step 3: Update `format_spill_row()` in `check_spills.py`**

Replace `format_spill_row` (lines 113–123):

```python
def format_spill_row(feature: dict, home_lat: float, home_lon: float, company: str) -> dict:
    """Return a display-ready dict for one spill feature."""
    props = feature["properties"]
    lon, lat = feature["geometry"]["coordinates"]
    distance = haversine_km(home_lat, home_lon, lat, lon)
    watercourse = props.get("ReceivingWaterCourse") or props.get("receivingWaterCourse", "")
    start = props.get("LatestEventStart") or props.get("latestEventStart")
    end = props.get("LatestEventEnd") or props.get("latestEventEnd")
    return {
        "site_id": props["Id"],
        "company": company,
        "watercourse": watercourse,
        "distance_km": round(distance, 1),
        "started": _fmt_epoch_ms(start),
        "ended": _fmt_epoch_ms(end),
    }
```

- [ ] **Step 4: Run `TestFormatSpillRow` to verify all pass**

```bash
uv run pytest tests/test_check_spills.py::TestFormatSpillRow -v
```

Expected: `4 passed`

- [ ] **Step 5: Run full suite**

```bash
uv run pytest tests/ -v
```

Expected: `TestBuildHtmlEmail` and `TestBuildTextEmail` may fail because `SAMPLE_ROWS` now has a `company` key that the email builders don't yet handle — that's fine, fixed in Task 5.

- [ ] **Step 6: Commit**

```bash
git add check_spills.py tests/test_check_spills.py
git commit -m "feat: update format_spill_row() — geometry coords, camelCase normalisation, company arg"
```

---

### Task 5: Update email builders — add Company column

**Files:**
- Modify: `check_spills.py` — `build_html_email()` and `build_text_email()`
- Modify: `tests/test_check_spills.py` — `TestBuildHtmlEmail`, `TestBuildTextEmail`

- [ ] **Step 1: Update email builder tests**

Replace `TestBuildHtmlEmail` with:

```python
class TestBuildHtmlEmail:
    def test_subject_contains_count_and_postcode(self):
        subject, _ = check_spills.build_html_email(SAMPLE_ROWS, "GL5 1HE", 20)
        assert "1" in subject
        assert "GL5 1HE" in subject

    def test_html_contains_all_row_fields(self):
        _, html = check_spills.build_html_email(SAMPLE_ROWS, "GL5 1HE", 20)
        assert "SVT001" in html
        assert "Test Water Co" in html
        assert "RIVER TEST" in html
        assert "5.3" in html
        assert "2026-03-17 10:00 UTC" in html
        assert "Ongoing" in html

    def test_html_is_valid_table(self):
        _, html = check_spills.build_html_email(SAMPLE_ROWS, "GL5 1HE", 20)
        assert "<table" in html
        assert "<tr>" in html or "<tr " in html
        assert "<th>" in html or "<th " in html

    def test_html_appends_failure_warning(self):
        subject, html = check_spills.build_html_email(
            SAMPLE_ROWS, "GL5 1HE", 20, failures=[("United Utilities", "timeout")]
        )
        assert "United Utilities" in html
        assert "unreported" in html
```

Replace `TestBuildTextEmail` with:

```python
class TestBuildTextEmail:
    def test_contains_all_row_fields(self):
        text = check_spills.build_text_email(SAMPLE_ROWS, "GL5 1HE", 20)
        assert "SVT001" in text
        assert "Test Water Co" in text
        assert "RIVER TEST" in text
        assert "Ongoing" in text
        assert "GL5 1HE" in text

    def test_text_appends_failure_warning(self):
        text = check_spills.build_text_email(
            SAMPLE_ROWS, "GL5 1HE", 20, failures=[("United Utilities", "timeout")]
        )
        assert "United Utilities" in text
        assert "unreported" in text
```

- [ ] **Step 2: Run tests to confirm they fail**

```bash
uv run pytest tests/test_check_spills.py::TestBuildHtmlEmail tests/test_check_spills.py::TestBuildTextEmail -v
```

Expected: failures about missing `Company` column and missing `failures` parameter.

- [ ] **Step 3: Update `build_html_email()` in `check_spills.py`**

Replace `build_html_email` (lines 126–150):

```python
def build_html_email(
    rows: list, postcode: str, radius_km: float, failures: list | None = None
) -> tuple[str, str]:
    """Return (subject, html_body) for the spill alert email."""
    count = len(rows)
    subject = f"Sewage alert: {count} spill(s) within {radius_km}km of {postcode}"
    rows_html = "\n".join(
        f"<tr><td>{r['company']}</td><td>{r['site_id']}</td><td>{r['watercourse']}</td>"
        f"<td>{r['distance_km']}</td><td>{r['started']}</td><td>{r['ended']}</td></tr>"
        for r in rows
    )
    html = f"""<html><body>
<p>{count} sewage overflow event(s) started near {postcode} in the last check window.</p>
<table border="1" cellpadding="4" cellspacing="0">
  <thead>
    <tr>
      <th>Company</th><th>Site ID</th><th>Watercourse</th><th>Distance (km)</th>
      <th>Event started</th><th>Event ended</th>
    </tr>
  </thead>
  <tbody>
    {rows_html}
  </tbody>
</table>
<p><small>Source: England and Wales water companies via streamwaterdata.co.uk</small></p>"""
    if failures:
        failed_names = ", ".join(name for name, _ in failures)
        html += (
            f"<p>&#x26A0; The following companies could not be queried and may have "
            f"unreported events: {failed_names}</p>"
        )
    html += "\n</body></html>"
    return subject, html
```

- [ ] **Step 4: Update `build_text_email()` in `check_spills.py`**

Replace `build_text_email` (lines 153–163):

```python
def build_text_email(
    rows: list, postcode: str, radius_km: float, failures: list | None = None
) -> str:
    """Return plain-text body for the spill alert email."""
    count = len(rows)
    lines = [f"{count} sewage overflow event(s) near {postcode} (within {radius_km}km):\n"]
    for r in rows:
        lines.append(
            f"- {r['company']} | {r['site_id']} | {r['watercourse']} | {r['distance_km']}km "
            f"| Started: {r['started']} | Ended: {r['ended']}"
        )
    lines.append("\nSource: England and Wales water companies via streamwaterdata.co.uk")
    if failures:
        failed_names = ", ".join(name for name, _ in failures)
        lines.append(
            f"\n⚠ The following companies could not be queried and may have "
            f"unreported events: {failed_names}"
        )
    return "\n".join(lines)
```

- [ ] **Step 5: Run email builder tests**

```bash
uv run pytest tests/test_check_spills.py::TestBuildHtmlEmail tests/test_check_spills.py::TestBuildTextEmail -v
```

Expected: `6 passed`

- [ ] **Step 6: Run full suite**

```bash
uv run pytest tests/ -v
```

Expected: `TestMain` tests fail with `TypeError` because `main()` still calls `query_spills` without `query_url` — fixed in Task 6. `TestFormatSpillRow` still passes (old 3-arg signature unchanged until Task 4). All other tests pass.

- [ ] **Step 7: Commit**

```bash
git add check_spills.py tests/test_check_spills.py
git commit -m "feat: add Company column to email output, add failure warning to email builders"
```

---

### Task 6: Update `main()` — query all companies, aggregate, handle failures

**Files:**
- Modify: `check_spills.py` — `main()` and `__main__` block
- Modify: `tests/test_check_spills.py` — `TestMain`

- [ ] **Step 1: Update `TestMain`**

Replace the entire `TestMain` class:

```python
class TestMain:
    BASE_CONFIG = {
        "postcode": "GL5 1HE",
        "radius_km": 20,
        "lookback_hours": 24,
        "notify_email": "user@example.com",
    }
    COMPANIES_YAML = (
        "companies:\n"
        "  - name: Severn Trent Water\n"
        "    query_url: https://fake1.arcgis.com/query\n"
        "  - name: Thames Water\n"
        "    query_url: https://fake2.arcgis.com/query\n"
    )

    def _write_config(self, tmp_path):
        import yaml
        config_file = tmp_path / "config.yml"
        config_file.write_text(yaml.dump(self.BASE_CONFIG))
        return str(config_file)

    def _write_companies(self, tmp_path, content=None):
        companies_file = tmp_path / "companies.yml"
        companies_file.write_text(content or self.COMPANIES_YAML)
        return str(companies_file)

    def test_no_email_when_no_spills(self, tmp_path):
        config_file = self._write_config(tmp_path)
        companies_file = self._write_companies(tmp_path)

        empty_features = {"type": "FeatureCollection", "features": []}
        postcode_payload = {"status": 200, "result": {"latitude": 51.745, "longitude": -2.216}}

        def fake_urlopen(url, **kwargs):
            if "postcodes.io" in url:
                return _mock_urlopen(postcode_payload)
            return _mock_urlopen(empty_features)

        with patch("urllib.request.urlopen", side_effect=fake_urlopen), \
             patch("smtplib.SMTP_SSL") as mock_smtp, \
             patch.dict("os.environ", {"GMAIL_ADDRESS": "sender@gmail.com", "GMAIL_APP_PASSWORD": "pw"}):
            check_spills.main(config_path=config_file, companies_path=companies_file)

        mock_smtp.assert_not_called()

    def test_sends_email_when_spills_found(self, tmp_path):
        config_file = self._write_config(tmp_path)
        companies_file = self._write_companies(tmp_path)

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
            check_spills.main(config_path=config_file, companies_path=companies_file)

        mock_server.sendmail.assert_called_once()

    def test_aggregates_spills_from_multiple_companies(self, tmp_path):
        config_file = self._write_config(tmp_path)
        companies_file = self._write_companies(tmp_path)

        spill_1 = {**SAMPLE_FEATURE, "properties": {**SAMPLE_FEATURE["properties"], "Id": "AAA001"}}
        spill_2 = {**SAMPLE_FEATURE, "properties": {**SAMPLE_FEATURE["properties"], "Id": "BBB001"}}
        postcode_payload = {"status": 200, "result": {"latitude": 51.745, "longitude": -2.216}}
        call_count = [0]

        def fake_urlopen(url, **kwargs):
            if "postcodes.io" in url:
                return _mock_urlopen(postcode_payload)
            call_count[0] += 1
            if call_count[0] == 1:
                return _mock_urlopen({"type": "FeatureCollection", "features": [spill_1]})
            return _mock_urlopen({"type": "FeatureCollection", "features": [spill_2]})

        mock_server = MagicMock()
        mock_smtp_cm = MagicMock()
        mock_smtp_cm.__enter__.return_value = mock_server
        mock_smtp_cm.__exit__.return_value = False

        with patch("urllib.request.urlopen", side_effect=fake_urlopen), \
             patch("smtplib.SMTP_SSL", return_value=mock_smtp_cm), \
             patch.dict("os.environ", {"GMAIL_ADDRESS": "sender@gmail.com", "GMAIL_APP_PASSWORD": "pw"}):
            check_spills.main(config_path=config_file, companies_path=companies_file)

        args = mock_server.sendmail.call_args[0]
        assert "AAA001" in args[2]
        assert "BBB001" in args[2]

    def test_continues_and_exits_nonzero_on_partial_failure(self, tmp_path):
        config_file = self._write_config(tmp_path)
        companies_file = self._write_companies(tmp_path)

        postcode_payload = {"status": 200, "result": {"latitude": 51.745, "longitude": -2.216}}
        call_count = [0]

        def fake_urlopen(url, **kwargs):
            if "postcodes.io" in url:
                return _mock_urlopen(postcode_payload)
            call_count[0] += 1
            if call_count[0] == 1:
                raise Exception("connection refused")
            return _mock_urlopen({"type": "FeatureCollection", "features": [SAMPLE_FEATURE]})

        mock_server = MagicMock()
        mock_smtp_cm = MagicMock()
        mock_smtp_cm.__enter__.return_value = mock_server
        mock_smtp_cm.__exit__.return_value = False

        with patch("urllib.request.urlopen", side_effect=fake_urlopen), \
             patch("smtplib.SMTP_SSL", return_value=mock_smtp_cm), \
             patch.dict("os.environ", {"GMAIL_ADDRESS": "sender@gmail.com", "GMAIL_APP_PASSWORD": "pw"}), \
             pytest.raises(SystemExit) as exc_info:
            check_spills.main(config_path=config_file, companies_path=companies_file)

        assert exc_info.value.code == 1
        mock_server.sendmail.assert_called_once()

    def test_sends_error_only_email_when_no_spills_but_failures(self, tmp_path):
        config_file = self._write_config(tmp_path)
        companies_file = self._write_companies(tmp_path)

        postcode_payload = {"status": 200, "result": {"latitude": 51.745, "longitude": -2.216}}

        def fake_urlopen(url, **kwargs):
            if "postcodes.io" in url:
                return _mock_urlopen(postcode_payload)
            raise Exception("timeout")

        mock_server = MagicMock()
        mock_smtp_cm = MagicMock()
        mock_smtp_cm.__enter__.return_value = mock_server
        mock_smtp_cm.__exit__.return_value = False

        with patch("urllib.request.urlopen", side_effect=fake_urlopen), \
             patch("smtplib.SMTP_SSL", return_value=mock_smtp_cm), \
             patch.dict("os.environ", {"GMAIL_ADDRESS": "sender@gmail.com", "GMAIL_APP_PASSWORD": "pw"}), \
             pytest.raises(SystemExit) as exc_info:
            check_spills.main(config_path=config_file, companies_path=companies_file)

        assert exc_info.value.code == 1
        mock_server.sendmail.assert_called_once()
        args = mock_server.sendmail.call_args[0]
        assert "could not be queried" in args[2]
```

- [ ] **Step 2: Run tests to confirm they fail**

```bash
uv run pytest tests/test_check_spills.py::TestMain -v
```

Expected: failures about `main()` missing `companies_path` argument or calling `query_spills` without `query_url`.

- [ ] **Step 3: Replace `main()` in `check_spills.py`**

Replace `main()` and the `__main__` block (lines 194–243):

```python
def main(config_path: str = "config.yml", companies_path: str = "companies.yml") -> None:
    log("Reading credentials from environment")
    from_addr = os.environ["GMAIL_ADDRESS"]
    password = os.environ["GMAIL_APP_PASSWORD"]

    log(f"Loading config from {config_path}")
    config = load_config(config_path)
    postcode = config["postcode"]
    radius_km = config["radius_km"]
    lookback_hours = config["lookback_hours"]
    notify_email = config["notify_email"]
    log(f"Config: postcode={postcode}, radius={radius_km}km, lookback={lookback_hours}h, notify={notify_email}")

    validate_lookback_hours(lookback_hours)

    log(f"Looking up coordinates for {postcode}")
    home_lat, home_lon = get_postcode_coords(postcode)
    log(f"Coordinates: lat={home_lat}, lon={home_lon}")

    companies = load_companies(companies_path)
    log(f"Querying {len(companies)} water companies")

    rows = []
    failures = []
    for company in companies:
        log(f"Querying {company['name']} for spills in last {lookback_hours}h within {radius_km}km")
        try:
            features = query_spills(home_lat, home_lon, radius_km, lookback_hours, company["query_url"])
            log(f"  {company['name']}: {len(features)} spill(s)")
            rows += [format_spill_row(f, home_lat, home_lon, company["name"]) for f in features]
        except Exception as exc:
            failures.append((company["name"], str(exc)))
            print(f"WARNING: {company['name']} query failed: {exc}", file=sys.stderr)

    for r in rows:
        log(f"  Spill: {r['company']} | {r['site_id']} | {r['watercourse']} | {r['distance_km']}km | {r['started']} → {r['ended']}")

    if rows:
        subject, html = build_html_email(rows, postcode, radius_km, failures=failures or None)
        text = build_text_email(rows, postcode, radius_km, failures=failures or None)
        log(f"Subject: {subject}")
        log(f"Sending from {from_addr} to {notify_email} via smtp.gmail.com:465")
        send_email(subject, html, text, notify_email, from_addr, password)
        log("SMTP connection closed cleanly")
        print(f"Alert sent: {subject}")
    elif failures:
        n = len(failures)
        subject = f"Sewage alert warning: {n} company/companies could not be queried near {postcode}"
        body_lines = [f"{n} company/companies could not be queried — results may be incomplete:\n"]
        body_lines += [f"- {name}: {err}" for name, err in failures]
        text = "\n".join(body_lines)
        html = (
            f"<html><body><p>{n} company/companies could not be queried — results may be incomplete:</p><ul>"
            + "".join(f"<li>{name}: {err}</li>" for name, err in failures)
            + "</ul></body></html>"
        )
        log(f"Sending error notification: {subject}")
        send_email(subject, html, text, notify_email, from_addr, password)
        print(f"Warning sent: {subject}")
    else:
        print(f"No spills found within {radius_km}km of {postcode} in the last {lookback_hours}h.")
        return

    if failures:
        sys.exit(1)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Check for nearby sewage spills and send alerts.")
    parser.add_argument("-v", "--verbose", action="store_true", help="Print progress to stdout")
    parser.add_argument("--config", default="config.yml", help="Path to config file")
    args = parser.parse_args()

    if args.verbose:
        _verbose = True

    main(config_path=args.config)
```

- [ ] **Step 4: Run `TestMain`**

```bash
uv run pytest tests/test_check_spills.py::TestMain -v
```

Expected: `5 passed`

- [ ] **Step 5: Run full suite**

```bash
uv run pytest tests/ -v
```

Expected: all tests pass.

- [ ] **Step 6: Commit**

```bash
git add check_spills.py tests/test_check_spills.py
git commit -m "feat: update main() to query all 9 companies, aggregate results, handle partial failures"
```

---

### Task 7: Update `README.md`

**Files:**
- Modify: `README.md` lines 5–5 (geographic note)

- [ ] **Step 1: Replace the geographic note**

Find the existing blockquote (line 5):

```markdown
> **Geographic note:** This tool uses Severn Trent Water's dataset and only covers their service area (broadly the Midlands and parts of the East of England). If your postcode is outside this area, the script will run without error but will never find events.
```

Replace with:

```markdown
> **Geographic coverage:** This tool covers all 9 water companies in England and Wales (Anglian, Northumbrian, Severn Trent, South West, Southern, Thames, United Utilities, Wessex, and Yorkshire Water). Data is sourced from [streamwaterdata.co.uk](https://www.streamwaterdata.co.uk/pages/storm-overflows-data). Scottish postcodes are not covered.
```

- [ ] **Step 2: Run tests to confirm nothing broken**

```bash
uv run pytest tests/ -v
```

Expected: all tests pass.

- [ ] **Step 3: Commit and push**

```bash
git add README.md
git commit -m "docs: update geographic coverage note — now covers all 9 England/Wales water companies"
git push -u origin main
```

---

## Verification

After all tasks, confirm the final state:

```bash
uv run pytest tests/ -v
```

Expected: 37+ tests passing (30 original + 7+ new).

```bash
python check_spills.py --help
```

Expected: shows `--config` and `--verbose` flags, no errors.

```bash
python -c "import check_spills; cs = check_spills.load_companies(); print(len(cs), 'companies')"
```

Expected: `9 companies`
