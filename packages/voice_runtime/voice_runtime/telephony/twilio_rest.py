"""Small asynchronous REST adapter for inspecting and ending Twilio calls."""

from __future__ import annotations

import asyncio
import math
import re
from typing import Any

import httpx

from voice_runtime.telephony.twilio import TwilioCredentials

_CALL_SID = re.compile(r"CA[0-9a-fA-F]{32}\Z")
_ACCOUNT_SID = re.compile(r"AC[0-9a-fA-F]{32}\Z")
_CALL_STATUSES = frozenset(
    {"queued", "ringing", "in-progress", "completed", "busy", "failed", "no-answer", "canceled"}
)
_API_ROOT = "https://api.twilio.com/2010-04-01/Accounts"


class TwilioCallApiError(Exception):
    """Sanitized Twilio API failure; never includes response bodies or credentials."""

    def __init__(
        self,
        message: str = "Twilio call API request failed",
        *,
        http_status: int | None = None,
        write_uncertain: bool = False,
    ) -> None:
        super().__init__(message)
        self.http_status = http_status
        self.write_uncertain = write_uncertain


class TwilioRestCall:
    def __init__(
        self,
        credentials: TwilioCredentials,
        call_sid: str,
        *,
        client: httpx.AsyncClient | None = None,
        timeout_secs: float = 5,
    ) -> None:
        if (
            not isinstance(credentials.account_sid, str)
            or _ACCOUNT_SID.fullmatch(credentials.account_sid) is None
        ):
            raise ValueError("account_sid must be a Twilio Account SID")
        if not isinstance(call_sid, str) or _CALL_SID.fullmatch(call_sid) is None:
            raise ValueError("call_sid must be a Twilio Call SID")
        if not math.isfinite(timeout_secs) or timeout_secs <= 0:
            raise ValueError("timeout_secs must be finite and positive")

        self._credentials = credentials
        self._call_sid = call_sid
        self._timeout_secs = timeout_secs
        self._owned_client = client is None
        self._client = client or httpx.AsyncClient(
            timeout=httpx.Timeout(timeout_secs), follow_redirects=False
        )
        self._url = f"{_API_ROOT}/{credentials.account_sid}/Calls/{call_sid}.json"

    async def complete(self) -> str:
        return await self._request("POST", data={"Status": "completed"})

    async def status(self) -> str:
        return await self._request("GET")

    async def aclose(self) -> None:
        if self._owned_client:
            await self._client.aclose()

    async def _request(self, method: str, *, data: dict[str, str] | None = None) -> str:
        is_write = method == "POST"
        try:
            async with asyncio.timeout(self._timeout_secs):
                response = await self._client.request(
                    method,
                    self._url,
                    auth=httpx.BasicAuth(
                        *self._credentials.rest_auth
                    ),
                    data=data,
                    follow_redirects=False,
                )
        except TimeoutError:
            raise TwilioCallApiError(
                "Twilio call API request timed out", write_uncertain=is_write
            ) from None
        except httpx.HTTPError:
            raise TwilioCallApiError(write_uncertain=is_write) from None

        try:
            response.raise_for_status()
        except httpx.HTTPStatusError:
            raise TwilioCallApiError(
                http_status=response.status_code,
                write_uncertain=is_write and response.status_code >= 500,
            ) from None

        try:
            payload: Any = response.json()
        except (ValueError, UnicodeDecodeError):
            raise TwilioCallApiError(
                "Twilio call API returned malformed JSON",
                http_status=response.status_code,
                write_uncertain=is_write,
            ) from None
        if not isinstance(payload, dict):
            raise TwilioCallApiError(
                "Twilio call API returned malformed data",
                http_status=response.status_code,
                write_uncertain=is_write,
            )
        if (
            payload.get("sid") != self._call_sid
            or payload.get("account_sid") != self._credentials.account_sid
        ):
            raise TwilioCallApiError(
                "Twilio call API returned a mismatched call identity",
                http_status=response.status_code,
                write_uncertain=is_write,
            )
        result = payload.get("status")
        if not isinstance(result, str) or result not in _CALL_STATUSES:
            raise TwilioCallApiError(
                "Twilio call API returned an unknown call status",
                http_status=response.status_code,
                write_uncertain=is_write,
            )
        return result
