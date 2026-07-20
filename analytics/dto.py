# analytics/dto.py

from dataclasses import dataclass
from typing import Optional

from Qr.models import QRCode
from analytics.models import Visitor, ScanEvent


@dataclass
class ScanContext:

    # Required
    qr: QRCode
    request_data: dict

    # Request
    ip_address: str = ""
    user_agent: str = ""
    referer: str = ""
    language: str = ""

    # Geo
    country: str = ""
    country_code: str = ""
    region: str = ""
    city: str = ""
    timezone: str = ""

    latitude: Optional[float] = None
    longitude: Optional[float] = None

    # Device
    browser: str = ""
    browser_version: str = ""

    os: str = ""
    os_version: str = ""

    device_type: str = ""
    device_brand: str = ""
    device_model: str = ""

    screen_width: Optional[int] = None
    screen_height: Optional[int] = None

    is_bot: bool = False

    # Visitor
    visitor: Optional[Visitor] = None
    fingerprint: str = ""
    is_unique_scan: bool = False

    #scan event
    scan_event: Optional[ScanEvent] = None