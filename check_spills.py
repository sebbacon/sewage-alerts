#!/usr/bin/env python3
"""Check for sewage overflow events near a configured postcode and send email alerts."""

import argparse
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


_verbose = False


def log(msg: str) -> None:
    """Print a progress message when verbose mode is on."""
    if _verbose:
        print(f"  {msg}")


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
    config: dict = {}
    with open(path) as f:
        for line in f:
            line = line.strip()
            if ":" in line and not line.startswith("#"):
                key, _, value = line.partition(":")
                config[key.strip()] = value.strip().strip('"').strip("'")
    for int_key in ("radius_km", "lookback_hours"):
        if int_key in config:
            config[int_key] = int(config[int_key])
    return config


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


def _fmt_epoch_ms(epoch_ms) -> str:
    """Format an epoch-millisecond timestamp as a UTC string, or 'Ongoing' if falsy."""
    if not epoch_ms:
        return "Ongoing"
    dt = datetime.fromtimestamp(epoch_ms / 1000, tz=timezone.utc)
    return dt.strftime("%Y-%m-%d %H:%M UTC")


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
        log("Connecting to smtp.gmail.com:465")
        with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
            log(f"Logging in as {from_addr}")
            server.login(from_addr, password)
            log("Login successful, sending message")
            server.sendmail(from_addr, to_addr, msg.as_string())
            log("sendmail() returned without error")
    except Exception as exc:
        print(f"ERROR: Could not send email: {exc}", file=sys.stderr)
        sys.exit(1)


def main(
    config_path: str = "config.yml",
    companies_path: str = "companies.yml",
    postcode_override: str | None = None,
    radius_km_override: int | None = None,
    notify_email_override: str | None = None,
) -> None:
    log("Reading credentials from environment")
    from_addr = os.environ["GMAIL_ADDRESS"]
    password = os.environ["GMAIL_APP_PASSWORD"]

    log(f"Loading config from {config_path}")
    config = load_config(config_path)
    postcode = postcode_override or config["postcode"]
    radius_km = radius_km_override if radius_km_override is not None else config["radius_km"]
    lookback_hours = config["lookback_hours"]
    notify_email = notify_email_override or config["notify_email"]
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
        if failures:
            sys.exit(1)
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
        sys.exit(1)
    else:
        print(f"No spills found within {radius_km}km of {postcode} in the last {lookback_hours}h.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Check for nearby sewage spills and send alerts.")
    parser.add_argument("-v", "--verbose", action="store_true", help="Print progress to stdout")
    parser.add_argument("--config", default="config.yml", help="Path to config file")
    parser.add_argument("--postcode", default=None, help="Override postcode from config")
    parser.add_argument("--radius", type=int, default=None, help="Override radius_km from config")
    parser.add_argument("--email", default=None, help="Override notify_email from config")
    args = parser.parse_args()

    if args.verbose:
        _verbose = True

    main(
        config_path=args.config,
        postcode_override=args.postcode,
        radius_km_override=args.radius,
        notify_email_override=args.email,
    )
