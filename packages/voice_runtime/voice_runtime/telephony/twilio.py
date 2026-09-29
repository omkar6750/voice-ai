"""Twilio Programmable Voice client adapter and TwiML builder."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from dataclasses import field as dataclass_field

from twilio.http.http_client import TwilioHttpClient
from twilio.rest import Client
from twilio.twiml.voice_response import VoiceResponse


@dataclass(frozen=True)
class TwilioCredentials:
    account_sid: str
    auth_token: str = dataclass_field(repr=False)
    api_key_sid: str | None = None
    api_key_secret: str | None = dataclass_field(default=None, repr=False)

    @property
    def rest_auth(self) -> tuple[str, str]:
        if not self.api_key_sid or not self.api_key_secret:
            raise ValueError("Twilio REST requires an API key SID and secret")
        return self.api_key_sid, self.api_key_secret


class TwilioCallLifecycle:
    def __init__(self) -> None:
        self._ended = False

    def mark_ended(self) -> None:
        self._ended = True

    @property
    def is_ended(self) -> bool:
        return self._ended

    async def __call__(self) -> bool:
        return not self._ended


class PublicTelephonyUrls:
    def __init__(self, public_base_url: str):
        self.base = public_base_url.rstrip("/")

    def twilio_call_status(self, correlation_id: str) -> str:
        return f"{self.base}/api/v1/telephony/twilio/call-status/{correlation_id}"

    def twilio_stream_status(self, correlation_id: str) -> str:
        return f"{self.base}/api/v1/telephony/twilio/stream-status/{correlation_id}"

    def twilio_media(self, correlation_id: str) -> str:
        if self.base.startswith("https://"):
            ws_base = "wss://" + self.base[len("https://") :]
        elif self.base.startswith("http://"):
            ws_base = "ws://" + self.base[len("http://") :]
        else:
            raise ValueError("PUBLIC_BASE_URL must use http:// or https://")
        return f"{ws_base}/api/v1/telephony/twilio/media/{correlation_id}"


def build_twilio_stream_twiml(
    *,
    media_ws_url: str,
    stream_status_callback_url: str,
    correlation_id: str,
    run_id: str,
) -> str:
    response = VoiceResponse()
    connect = response.connect()
    stream = connect.stream(
        url=media_ws_url,
        status_callback=stream_status_callback_url,
        status_callback_method="POST",
    )
    stream.parameter(name="correlation_id", value=correlation_id)
    stream.parameter(name="run_id", value=run_id)
    return str(response)


class TwilioCallController:
    def __init__(self, credentials: TwilioCredentials) -> None:
        self.credentials = credentials
        self.client = Client(
            *credentials.rest_auth,
            account_sid=credentials.account_sid,
            http_client=TwilioHttpClient(timeout=10, max_retries=0),
        )

    async def dial(
        self,
        *,
        to: str,
        from_number: str,
        media_ws_url: str,
        status_callback_url: str,
        stream_status_callback_url: str,
        correlation_id: str,
        run_id: str,
        ringing_timeout: int = 30,
    ) -> str:
        twiml = build_twilio_stream_twiml(
            media_ws_url=media_ws_url,
            stream_status_callback_url=stream_status_callback_url,
            correlation_id=correlation_id,
            run_id=run_id,
        )

        async with asyncio.timeout(12):
            call = await asyncio.to_thread(
                self.client.calls.create,
                to=to,
                from_=from_number,
                twiml=twiml,
                timeout=ringing_timeout,
                status_callback=status_callback_url,
                status_callback_method="POST",
                status_callback_event=[
                    "initiated",
                    "ringing",
                    "answered",
                    "completed",
                ],
            )

        return str(call.sid)

    async def hangup(self, call_sid: str) -> None:
        await asyncio.to_thread(
            self.client.calls(call_sid).update,
            status="completed",
        )
