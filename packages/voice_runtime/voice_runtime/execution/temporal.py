"""Temporal context and 24-hour clock resolution for dynamic greetings and signoffs."""

from __future__ import annotations

from datetime import datetime
from functools import lru_cache
from pathlib import Path
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import tzdata

ISO_COUNTRY_NAMES = {
    "AF": "Afghanistan",
    "AL": "Albania",
    "DZ": "Algeria",
    "AR": "Argentina",
    "AM": "Armenia",
    "AU": "Australia",
    "AT": "Austria",
    "AZ": "Azerbaijan",
    "BH": "Bahrain",
    "BD": "Bangladesh",
    "BY": "Belarus",
    "BE": "Belgium",
    "BR": "Brazil",
    "BG": "Bulgaria",
    "CA": "Canada",
    "CL": "Chile",
    "CN": "China",
    "CO": "Colombia",
    "CR": "Costa Rica",
    "HR": "Croatia",
    "CY": "Cyprus",
    "CZ": "Czech Republic",
    "DK": "Denmark",
    "DO": "Dominican Republic",
    "EG": "Egypt",
    "EE": "Estonia",
    "ET": "Ethiopia",
    "FI": "Finland",
    "FR": "France",
    "GE": "Georgia",
    "DE": "Germany",
    "GH": "Ghana",
    "GR": "Greece",
    "GT": "Guatemala",
    "HK": "Hong Kong",
    "HU": "Hungary",
    "IS": "Iceland",
    "IN": "India",
    "ID": "Indonesia",
    "IR": "Iran",
    "IQ": "Iraq",
    "IE": "Ireland",
    "IL": "Israel",
    "IT": "Italy",
    "JP": "Japan",
    "JO": "Jordan",
    "KZ": "Kazakhstan",
    "KE": "Kenya",
    "KW": "Kuwait",
    "LV": "Latvia",
    "LB": "Lebanon",
    "LT": "Lithuania",
    "LU": "Luxembourg",
    "MY": "Malaysia",
    "MX": "Mexico",
    "MA": "Morocco",
    "NP": "Nepal",
    "NL": "Netherlands",
    "NZ": "New Zealand",
    "NG": "Nigeria",
    "NO": "Norway",
    "OM": "Oman",
    "PK": "Pakistan",
    "PA": "Panama",
    "PE": "Peru",
    "PH": "Philippines",
    "PL": "Poland",
    "PT": "Portugal",
    "QA": "Qatar",
    "RO": "Romania",
    "RU": "Russia",
    "SA": "Saudi Arabia",
    "RS": "Serbia",
    "SG": "Singapore",
    "ZA": "South Africa",
    "KR": "South Korea",
    "ES": "Spain",
    "LK": "Sri Lanka",
    "SE": "Sweden",
    "CH": "Switzerland",
    "TW": "Taiwan",
    "TH": "Thailand",
    "TR": "Turkey",
    "UA": "Ukraine",
    "AE": "United Arab Emirates",
    "GB": "United Kingdom",
    "US": "United States",
    "UY": "Uruguay",
    "VN": "Vietnam",
}


@lru_cache(maxsize=1)
def _load_tz_country_map() -> dict[str, str]:
    mapping: dict[str, str] = {}
    try:
        tab = Path(tzdata.__file__).parent / "zoneinfo" / "zone1970.tab"
        if tab.exists():
            for line in tab.read_text(encoding="utf-8").splitlines():
                stripped = line.strip()
                if not stripped or stripped.startswith("#"):
                    continue
                parts = stripped.split("\t")
                if len(parts) >= 3:
                    cc = parts[0].split(",")[0].strip()
                    tz = parts[2].strip()
                    mapping[tz] = cc
    except Exception:
        pass
    defaults = {
        "Asia/Kolkata": "IN",
        "Asia/Calcutta": "IN",
        "America/New_York": "US",
        "America/Chicago": "US",
        "America/Denver": "US",
        "America/Los_Angeles": "US",
        "Europe/London": "GB",
        "Asia/Dubai": "AE",
        "Australia/Sydney": "AU",
        "America/Toronto": "CA",
    }
    for k, v in defaults.items():
        mapping.setdefault(k, v)
    return mapping


def resolve_country_from_timezone(timezone_str: str | None) -> tuple[str, str]:
    """Return (country_name, country_code) for given timezone."""
    if not timezone_str:
        return "", ""
    tz_map = _load_tz_country_map()
    cc = tz_map.get(timezone_str, "")
    if not cc and "/" in timezone_str:
        for tz_key, code in tz_map.items():
            if tz_key.endswith(timezone_str.split("/")[-1]):
                cc = code
                break
    name = ISO_COUNTRY_NAMES.get(cc, cc)
    return name, cc


def resolve_local_time_context(
    timezone_str: str | None,
    fallback: str = "Asia/Kolkata",
    reference_dt: datetime | None = None,
) -> dict[str, str]:
    """Convert contact timezone to 24-hour time, daypart, country, and greeting/signoff phrases."""
    tz_name = timezone_str or fallback
    try:
        zone = ZoneInfo(tz_name)
    except ZoneInfoNotFoundError:
        zone = ZoneInfo(fallback)
        tz_name = fallback

    now = (reference_dt or datetime.now()).astimezone(zone)
    hour = now.hour  # 0 to 23

    # Categorize dayparts based on 24-hour clock
    if 5 <= hour < 12:
        daypart = "morning"
        greeting = "Good morning"
        signoff = "Have a great day ahead"
    elif 12 <= hour < 17:
        daypart = "afternoon"
        greeting = "Good afternoon"
        signoff = "Have a wonderful afternoon"
    elif 17 <= hour < 22:
        daypart = "evening"
        greeting = "Good evening"
        signoff = "Have a pleasant evening"
    else:
        daypart = "night"
        greeting = "Good evening"
        signoff = "Goodnight and take care"

    country, country_code = resolve_country_from_timezone(tz_name)

    return {
        "timezone": str(zone),
        "local_time_24h": now.strftime("%H:%M"),
        "local_time_12h": now.strftime("%I:%M %p").lstrip("0"),
        "daypart": daypart,
        "greeting_phrase": greeting,
        "signoff_phrase": signoff,
        "day_of_week": now.strftime("%A"),
        "country": country,
        "country_code": country_code,
    }
