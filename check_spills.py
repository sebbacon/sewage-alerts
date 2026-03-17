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


if __name__ == "__main__":
    pass
