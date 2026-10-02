"""Twilio execution belongs to the separate runtime service."""

from urllib.parse import urlsplit

from fastapi import HTTPException

from voice_api.services.runtime_dispatch import dispatch


def validate_twilio_dispatch_settings(settings):
    for value in (settings.public_base_url, settings.runtime_public_base_url):
        url = urlsplit(value or "")
        if (
            url.scheme != "https"
            or not url.hostname
            or url.username
            or url.password
            or url.query
            or url.fragment
            or url.path not in {"", "/"}
        ):
            raise HTTPException(422, "Twilio requires canonical HTTPS API and runtime URLs")
    if not settings.runtime_control_token or not settings.runtime_service_token:
        raise HTTPException(422, "Runtime authentication is not configured")
    return settings.public_base_url


async def dispatch_twilio_call(session, call, run, settings):
    validate_twilio_dispatch_settings(settings)
    await dispatch(session, run)
    return call, run
