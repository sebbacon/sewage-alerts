# Multi-Company Support Design

## Goal

Allow any UK postcode to work with the sewage alerts tool by querying all 9 water companies in England and Wales, not just Severn Trent.

## Endpoint Discovery

All 9 FeatureServer endpoints were discovered on 2026-03-18 using the ArcGIS Online public search API:

```
https://www.arcgis.com/sharing/rest/search?q=Storm_Overflow_Activity&f=json&num=20
```

All endpoints confirmed working with the existing `INTERVAL` SQL time filter and ArcGIS spatial distance filter. ArcGIS SQL is case-insensitive for field names in `where` clauses — confirmed by testing `LatestEventStart >= CURRENT_TIMESTAMP - INTERVAL '24' HOUR` against South West Water whose actual field is named `latestEventStart`; it returned correct results.

Scottish Water (`services3.arcgis.com/Bb8lfThdhugyc4G3/...`) appeared in the search results but is excluded — it is not part of the England/Wales streamwaterdata.co.uk data hub and serves a different regulatory area.

### The 9 Endpoints

| Company | Query URL |
|---|---|
| Anglian Water | `https://services3.arcgis.com/VCOY1atHWVcDlvlJ/arcgis/rest/services/stream_service_outfall_locations_view/FeatureServer/0/query` |
| Northumbrian Water | `https://services-eu1.arcgis.com/MSNNjkZ51iVh8yBj/arcgis/rest/services/Northumbrian_Water_Storm_Overflow_Activity_2_view/FeatureServer/0/query` |
| Severn Trent Water | `https://services1.arcgis.com/NO7lTIlnxRMMG9Gw/arcgis/rest/services/Severn_Trent_Water_Storm_Overflow_Activity/FeatureServer/0/query` |
| South West Water | `https://services-eu1.arcgis.com/OMdMOtfhATJPcHe3/arcgis/rest/services/NEH_outlets_PROD/FeatureServer/0/query` |
| Southern Water | `https://services-eu1.arcgis.com/XxS6FebPX29TRGDJ/arcgis/rest/services/Southern_Water_Storm_Overflow_Activity/FeatureServer/0/query` |
| Thames Water | `https://services2.arcgis.com/g6o32ZDQ33GpCIu3/arcgis/rest/services/Thames_Water_Storm_Overflow_Activity_(Production)_view/FeatureServer/0/query` |
| United Utilities | `https://services5.arcgis.com/5eoLvR0f8HKb7HWP/arcgis/rest/services/United_Utilities_Storm_Overflow_Activity/FeatureServer/0/query` |
| Wessex Water | `https://services.arcgis.com/3SZ6e0uCvPROr4mS/arcgis/rest/services/Wessex_Water_Storm_Overflow_Activity/FeatureServer/0/query` |
| Yorkshire Water | `https://services-eu1.arcgis.com/1WqkK5cDKUbF0CkH/arcgis/rest/services/Yorkshire_Water_Storm_Overflow_Activity/FeatureServer/0/query` |

## Architecture

### Routing Strategy

**Query all 9 companies.** The ArcGIS spatial distance filter is applied server-side, so each company's API returns only events near the user's coordinates. No postcode-to-company routing, boundary data, or caching is needed. Each run makes 9 requests: at 3 ArcGIS request units each against a 28,800 units/minute org limit, there is no practical rate-limiting concern.

### New File: `companies.yml`

Committed to the repo. Lists all 9 companies with their `query_url`. Field normalisation is handled in code, not in YAML. The file includes a comment noting that Scottish Water was found but excluded.

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

### Path Resolution for `companies.yml`

`load_companies()` defaults to `companies.yml` as a relative path (same as `load_config()` defaults to `config.yml`). `main()` passes the default. No `--companies` CLI flag is added — this file is not user-facing config, it is part of the application code.

### Field Normalisation

All companies share the same logical fields but South West Water uses camelCase in responses instead of PascalCase:

All 9 company response schemas were verified during endpoint discovery (2026-03-18). 8 companies return PascalCase; South West Water returns camelCase. `Id` is `Id` (capital I) on all 9 including South West Water — no normalisation needed for site ID.

| Field | Standard (8 companies) | South West Water |
|---|---|---|
| Site ID | `Id` | `Id` (identical) |
| Event start | `LatestEventStart` | `latestEventStart` |
| Event end | `LatestEventEnd` | `latestEventEnd` |
| Watercourse | `ReceivingWaterCourse` | `receivingWaterCourse` |

**Strategy in `format_spill_row`:**

- **Coordinates**: Replace `props["Latitude"]` / `props["Longitude"]` with `feature["geometry"]["coordinates"]` which is `[lon, lat]`. This is present in all GeoJSON responses and is the authoritative source for all companies. The property-based lat/lon fields are no longer read.
- **Event timestamps**: `props.get("LatestEventStart") or props.get("latestEventStart")`
- **Watercourse**: `props.get("ReceivingWaterCourse") or props.get("receivingWaterCourse")`

### `check_spills.py` Changes

**`load_companies(path="companies.yml") -> list[dict]`**
Reads `companies.yml`, returns list of `{"name": ..., "query_url": ...}` dicts.

**`query_spills(lat, lon, radius_km, lookback_hours, query_url) -> list`**
- `query_url` is a required 5th parameter (no default). The `ARCGIS_URL` constant is removed. It may be passed positionally or as a keyword argument.
- **Change from existing**: on failure, `raise RuntimeError(...)` instead of `sys.exit(1)`. This allows `main()` to catch per-company failures without aborting the whole run.
- **Existing `TestQuerySpills` tests** must be updated to pass a `query_url` argument (e.g. `query_spills(51.745, -2.216, 20, 24, "https://fake.arcgis.com/query")`).

**`format_spill_row(feature, home_lat, home_lon, company) -> dict`**
- `company` is a required positional argument (4th parameter).
- Adds `"company": company` to the returned dict.
- Uses `feature["geometry"]["coordinates"]` (`[lon, lat]`) for distance (replaces `props["Latitude"]`/`props["Longitude"]`). ArcGIS GeoJSON always includes a `geometry` object — no fallback needed, but all test fixtures must include a `geometry` key.
- Normalises field names with case-fallback as described above.
- **Existing tests** `TestFormatSpillRow.*` must be updated to:
  1. Pass `company="Test Company"` as the 4th argument.
  2. Add `"geometry": {"type": "Point", "coordinates": [-2.449, 51.752]}` to any feature fixtures that only have `{"properties": {...}}` (specifically the `test_ongoing_when_end_is_none` and `test_ongoing_when_end_is_zero` fixtures).

**`main()`**
```
companies = load_companies()
failures = []
rows = []
for company in companies:
    try:
        features = query_spills(..., query_url=company["query_url"])
        rows += [format_spill_row(f, lat, lon, company["name"]) for f in features]
    except Exception as exc:
        failures.append((company["name"], str(exc)))
        print(f"WARNING: {company['name']} query failed: {exc}", file=sys.stderr)

# Send email / exit
```

### Error Handling and Notification

| Spills found | Failures | Action |
|---|---|---|
| Yes | None | Send spill email (unchanged) |
| Yes | Some | Send spill email with warning section appended |
| No | Some | Send error-only email (see below) |
| No | None | Silent (unchanged) |

If any failures: `sys.exit(1)` after sending any email. If no spills and no failures: `return` (implicit exit 0, unchanged from existing behaviour). If `send_email()` itself fails (SMTP error), it calls `sys.exit(1)` as before — this behaviour is unchanged and applies to all email paths including the new error-only email.

**Error-only email (no spills, some failures):**
- Subject: `"Sewage alert warning: N company/companies could not be queried near {postcode}"`
- Body: Plain paragraph listing each failed company and its error message. No new builder function needed — use `send_email()` with a simple inline subject/html/text.

**Failure warning appended to spill email:**
- Extra paragraph after the spill table: `"⚠ The following companies could not be queried and may have unreported events: [list]"`

### Email Changes

- Add **Company** column as the first column in the HTML table and plain-text output.
- New error-only email and warning appendix as described above.

## Files Changed

| File | Change |
|---|---|
| `companies.yml` | New — lists all 9 endpoints with discovery provenance comment |
| `check_spills.py` | `load_companies()`, `query_url` param on `query_spills()`, `query_spills()` raises instead of exits, updated `format_spill_row()` (geometry coords, field normalisation, company arg), updated `main()` |
| `tests/test_check_spills.py` | Update `TestFormatSpillRow` to pass `company` arg and add `geometry` to property-only fixtures; update `TestQuerySpills` to pass `query_url`; add `SAMPLE_FEATURE_SOUTH_WEST` with camelCase fields; add raise-on-error test to `TestQuerySpills`; add multi-company and partial-failure tests to `TestMain` |
| `README.md` | Replace Severn Trent–only geographic note with "covers all 9 water companies in England and Wales" and a link to streamwaterdata.co.uk |

`configure.py` and the GitHub Actions workflow require no changes.
