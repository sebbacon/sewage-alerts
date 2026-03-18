# Multi-Company Support Design

## Goal

Allow any UK postcode to work with the sewage alerts tool by querying all 9 water companies in England and Wales, not just Severn Trent.

## Endpoint Discovery

All 9 FeatureServer endpoints were discovered on 2026-03-18 using the ArcGIS Online public search API:

```
https://www.arcgis.com/sharing/rest/search?q=Storm_Overflow_Activity&f=json&num=20
```

All endpoints confirmed working with the existing `INTERVAL` SQL time filter and ArcGIS spatial distance filter. Scottish Water (`services3.arcgis.com/Bb8lfThdhugyc4G3/...`) appeared in results but is excluded — it is not part of the England/Wales streamwaterdata.co.uk data hub.

### The 9 Endpoints

| Company | Query URL |
|---|---|
| Anglian Water | `https://services3.arcgis.com/VCOY1atHWVcDlvlJ/arcgis/rest/services/stream_service_outfall_locations_view/FeatureServer/0/query` |
| Northumbrian Water | `https://services-eu1.arcgis.com/MSNNjkZ51iVh8yBj/arcgis/rest/services/Northumbrian_Water_Storm_Overflow_Activity_2_view/FeatureServer/0/query` |
| Severn Trent Water | `https://services1.arcgis.com/NO7lTIlnxRMMG9Gw/arcgis/rest/services/Severn_Trent_Water_Storm_Overflow_Activity/FeatureServer/0/query` |
| South West Water | `https://services-eu1.arcgis.com/OMdMOtfhATJPcHe3/arcgis/rest/services/NEH_outlets_PROD/FeatureServer/0/query` |
| Southern Water | `https://services-eu1.arcgis.com/XxS6FebPX29TRGDJ/arcgis/rest/services/Southern_Water_Storm_Overflow_Activity/FeatureServer/0/query` |
| Thames Water | `https://services2.arcgis.com/g6o32ZDQ33GpCIu3/arcgis/rest/services/Thames_Water_Storm_Overflow_Activity_(Production)_view/FeatureServer/0/query` |
| United Utilities | `https://services5.arcgis.com/5eoLvR0f8HWP/arcgis/rest/services/United_Utilities_Storm_Overflow_Activity/FeatureServer/0/query` |
| Wessex Water | `https://services.arcgis.com/3SZ6e0uCvPROr4mS/arcgis/rest/services/Wessex_Water_Storm_Overflow_Activity/FeatureServer/0/query` |
| Yorkshire Water | `https://services-eu1.arcgis.com/1WqkK5cDKUbF0CkH/arcgis/rest/services/Yorkshire_Water_Storm_Overflow_Activity/FeatureServer/0/query` |

## Architecture

### Routing Strategy

**Query all 9 companies.** The ArcGIS spatial distance filter is applied server-side, so each company's API returns only events near the user's coordinates. No postcode-to-company routing, boundary data, or caching is needed. Each run makes 9 requests: at 3 ArcGIS request units each against a 28,800 units/minute limit, there is no practical rate-limiting concern.

### New File: `companies.yml`

Committed to the repo. Lists all 9 companies with their `query_url`. Field normalisation is handled in code, not in YAML.

```yaml
# Endpoints discovered 2026-03-18 via ArcGIS Online public search API.
# All use the same REST API and INTERVAL SQL syntax.
# South West Water uses camelCase field names; all others use PascalCase.
companies:
  - name: Anglian Water
    query_url: https://...
  - name: Northumbrian Water
    query_url: https://...
  ...
```

### Field Normalisation

All companies share the same logical fields but South West Water uses camelCase instead of PascalCase:

| Field | Standard | South West Water |
|---|---|---|
| Event start | `LatestEventStart` | `latestEventStart` |
| Event end | `LatestEventEnd` | `latestEventEnd` |
| Watercourse | `ReceivingWaterCourse` | `receivingWaterCourse` |
| Coordinates | `Latitude`, `Longitude` | `latitude`, `longitude` |

**Strategy:**
- Distance calculation uses `feature["geometry"]["coordinates"]` (`[lon, lat]`) — present in all GeoJSON responses, no property field needed
- Event timestamps and watercourse name use `props.get("LatestEventStart") or props.get("latestEventStart")` — handles both variants without per-company config

### `check_spills.py` Changes

- `load_companies(path)` — reads `companies.yml`, returns list of `{name, query_url}` dicts
- `query_spills(lat, lon, radius_km, lookback_hours, query_url)` — `query_url` replaces the hardcoded Severn Trent URL
- `format_spill_row(feature, home_lat, home_lon, company)` — adds `company` field, uses geometry coordinates, normalises field name case
- `main()` — iterates all companies, aggregates rows, tracks failures

### Error Handling

Each company query is wrapped in try/except. On failure the company name and error message are appended to a `failures` list and execution continues.

After all 9 queries:

| Spills found | Failures | Action |
|---|---|---|
| Yes | None | Send spill email (unchanged) |
| Yes | Some | Send spill email with warning section appended listing failed companies |
| No | Some | Send short error-only email: "N companies could not be queried — results may be incomplete" |
| No | None | Silent (unchanged) |

If any failures occurred, exit with code 1 after sending any email, so the GitHub Action marks the run as failed and triggers GitHub's built-in failure notification.

### Email Changes

- Add **Company** column to the HTML table and plain-text output
- Failure warning appended to spill email body, or sent as standalone error email

## Files Changed

| File | Change |
|---|---|
| `companies.yml` | New — lists all 9 endpoints |
| `check_spills.py` | `load_companies()`, parameterised `query_spills()`, updated `format_spill_row()`, updated `main()` |
| `tests/test_check_spills.py` | `SAMPLE_FEATURE_SOUTH_WEST` fixture (camelCase), multi-company mocks, partial/full failure tests |
| `README.md` | Replace Severn Trent–only geographic note with England/Wales coverage note |

`configure.py` and the GitHub Actions workflow require no changes.
