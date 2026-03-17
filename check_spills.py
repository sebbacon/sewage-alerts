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


def validate_lookback_hours(hours: int) -> None:
    """Warn to stderr if lookback_hours is not a recognised standard value."""
    if hours not in STANDARD_LOOKBACK_HOURS:
        print(
            f"WARNING: lookback_hours={hours} is non-standard (expected 6, 12, or 24). "
            "Ensure your cron schedule matches.",
            file=sys.stderr,
        )


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


def main(config_path: str = "config.yml") -> None:
    from_addr = os.environ["GMAIL_ADDRESS"]
    password = os.environ["GMAIL_APP_PASSWORD"]

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

    send_email(subject, html, text, notify_email, from_addr, password)
    print(f"Alert sent: {subject}")


if __name__ == "__main__":
    main()
