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


def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Return great-circle distance in km between two lat/lon points."""
    R = 6371
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2) ** 2
    return 2 * R * math.asin(math.sqrt(a))


def load_config(path: str = "config.yml") -> dict:
    """Load configuration from a YAML file."""
    with open(path) as f:
        return yaml.safe_load(f)


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


def validate_lookback_hours(hours: int) -> None:
    """Warn to stderr if lookback_hours is not a recognised standard value."""
    if hours not in STANDARD_LOOKBACK_HOURS:
        print(
            f"WARNING: lookback_hours={hours} is non-standard (expected 6, 12, or 24). "
            "Ensure your cron schedule matches.",
            file=sys.stderr,
        )


if __name__ == "__main__":
    pass
