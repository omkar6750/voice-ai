from datetime import datetime
from zoneinfo import ZoneInfo

from voice_runtime.execution.contact_context import sanitize_contact_variables
from voice_runtime.execution.temporal import resolve_local_time_context


def test_temporal_dayparts_and_greetings():
    tz = "Asia/Kolkata"
    zone = ZoneInfo(tz)

    # 09:15 AM -> morning
    morning_dt = datetime(2026, 9, 26, 9, 15, tzinfo=zone)
    res_morning = resolve_local_time_context(tz, reference_dt=morning_dt)
    assert res_morning["daypart"] == "morning"
    assert res_morning["greeting_phrase"] == "Good morning"
    assert res_morning["local_time_24h"] == "09:15"
    assert res_morning["local_time_12h"] == "9:15 AM"
    assert res_morning["day_of_week"] == "Saturday"
    assert res_morning["country"] == "India"
    assert res_morning["country_code"] == "IN"

    # Test other countries (US, UK)
    res_us = resolve_local_time_context("America/New_York", reference_dt=morning_dt)
    assert res_us["country"] == "United States"
    assert res_us["country_code"] == "US"

    res_gb = resolve_local_time_context("Europe/London", reference_dt=morning_dt)
    assert res_gb["country"] == "United Kingdom"
    assert res_gb["country_code"] == "GB"

    # 14:45 -> afternoon
    afternoon_dt = datetime(2026, 9, 26, 14, 45, tzinfo=zone)
    res_afternoon = resolve_local_time_context(tz, reference_dt=afternoon_dt)
    assert res_afternoon["daypart"] == "afternoon"
    assert res_afternoon["greeting_phrase"] == "Good afternoon"
    assert res_afternoon["local_time_24h"] == "14:45"
    assert res_afternoon["local_time_12h"] == "2:45 PM"

    # 19:30 -> evening
    evening_dt = datetime(2026, 9, 26, 19, 30, tzinfo=zone)
    res_evening = resolve_local_time_context(tz, reference_dt=evening_dt)
    assert res_evening["daypart"] == "evening"
    assert res_evening["greeting_phrase"] == "Good evening"
    assert res_evening["local_time_24h"] == "19:30"
    assert res_evening["local_time_12h"] == "7:30 PM"

    # 23:10 -> night
    night_dt = datetime(2026, 9, 26, 23, 10, tzinfo=zone)
    res_night = resolve_local_time_context(tz, reference_dt=night_dt)
    assert res_night["daypart"] == "night"
    assert res_night["signoff_phrase"] == "Goodnight and take care"


def test_temporal_fallback_for_invalid_timezone():
    res = resolve_local_time_context("Invalid/TimeZone", fallback="Asia/Kolkata")
    assert res["timezone"] == "Asia/Kolkata"
    assert res["local_time_24h"]


def test_sanitize_contact_variables_allowlist_filtering():
    contact = {
        "id": "c-123",
        "name": "Jane Doe",
        "phone_number": "+15551234567",
        "business": "Acme Widgets",
        "source": "facebook_ads",
        "language": "en-US",
        "metadata_json": {
            "campaign": "mvp_sprint_q3",
            "ad_headline": "Custom SaaS Engineering",
            "internal_secret_tag": "do-not-expose",
        },
    }

    # Whitelist only business, source, and campaign
    allowed = ["business", "source", "campaign"]
    sanitized = sanitize_contact_variables(contact, allowed)

    assert sanitized == {
        "business": "Acme Widgets",
        "source": "facebook_ads",
        "campaign": "mvp_sprint_q3",
    }
    # Sensitive or unlisted fields are strictly excluded
    assert "phone_number" not in sanitized
    assert "id" not in sanitized
    assert "name" not in sanitized
    assert "internal_secret_tag" not in sanitized


def test_sanitize_contact_variables_empty():
    assert sanitize_contact_variables(None, ["business"]) == {}
    assert sanitize_contact_variables({"business": "Test"}, []) == {}


def test_sanitize_contact_variables_security_exclusion():
    contact = {
        "id": "c-sensitive-999",
        "name": "Jane Doe",
        "phone_number": "+15551234567",
        "timezone": "Europe/London",
        "custom_column_lead_score": 95,
        "metadata_json": {
            "campaign": "mvp_sprint",
            "utm_medium": "cpc",
        },
    }

    # Requesting sensitive fields must strictly be ignored
    dangerous_allowed = [
        "id",
        "phone_number",
        "metadata_json",
        "created_at",
        "timezone",
        "custom_column_lead_score",
        "metadata.utm_medium",
    ]
    sanitized = sanitize_contact_variables(contact, dangerous_allowed)

    # Sensitive fields are NEVER exposed
    assert "id" not in sanitized
    assert "phone_number" not in sanitized
    assert "metadata_json" not in sanitized
    assert "created_at" not in sanitized

    # Safe dynamic fields and metadata are properly extracted
    assert sanitized["timezone"] == "Europe/London"
    assert sanitized["custom_column_lead_score"] == 95
    assert sanitized["utm_medium"] == "cpc"
