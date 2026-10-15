"""Payload-free telemetry around pinned Pipecat's realtime Sarvam service."""

import re
from datetime import UTC, datetime

from pipecat.services.sarvam.stt import SarvamRealtimeSTTService
from voice_shared.dev_visibility import redact_api_keys


def safe_identifier(value):
    return (
        value
        if isinstance(value, str)
        and re.fullmatch(r"[A-Za-z0-9_.:-]{1,128}", value)
        and redact_api_keys(value) == value
        else None
    )


class DiagnosticSarvamRealtimeSTTService(SarvamRealtimeSTTService):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.diagnostic_state = {
            "audio_bytes_sent": 0,
            "audio_chunks_sent": 0,
            "final_transcripts": 0,
        }
        self.diagnostic_event = None

    def _event(self, event):
        self.diagnostic_state[f"{event}_at"] = datetime.now(UTC).isoformat()
        if self.diagnostic_event:
            self.diagnostic_event(event, dict(self.diagnostic_state))

    async def _connect_websocket(self):
        self._event("connection_opening")
        await super()._connect_websocket()
        if self._websocket:
            self._event("connection_opened")
        else:
            await self.set_usable(False)

    async def _disconnect_websocket(self):
        if self._websocket:
            code = getattr(self._websocket, "close_code", None)
            if isinstance(code, int):
                self.diagnostic_state["websocket_close_code"] = code
        self._event("connection_closing")
        await super()._disconnect_websocket()
        self._event("connection_closed")

    async def _send_audio_chunk(self, chunk):
        before = self._audio_position_bytes
        await super()._send_audio_chunk(chunk)
        if self._audio_position_bytes > before:
            self.diagnostic_state["audio_bytes_sent"] += len(chunk)
            self.diagnostic_state["audio_chunks_sent"] += 1
            self.diagnostic_state["last_audio_sent_at"] = datetime.now(UTC).isoformat()
            if self.diagnostic_state["audio_chunks_sent"] == 1:
                self._event("first_audio_sent")

    async def _handle_message(self, message):
        event = message.get("event")
        request_id = safe_identifier(message.get("request_id"))
        if request_id:
            self.diagnostic_state["provider_request_id"] = request_id
        if event == "session.begin":
            self._event("session_begin")
        if event in {"vad.speech_start", "vad.speech_end", "transcript.final", "session.end"}:
            if event == "transcript.final":
                self.diagnostic_state["final_transcripts"] += 1
            self._event(event.replace(".", "_"))
        if event == "error":
            error = message.get("error")
            error = error if isinstance(error, dict) else message
            raw_code = error.get("code")
            code = safe_identifier(raw_code) or (str(raw_code) if type(raw_code) is int else None)
            if code:
                self.diagnostic_state["provider_error_code"] = code
            status = error.get("status_code")
            if type(status) is int and 100 <= status <= 599:
                self.diagnostic_state["http_status"] = status
            elif type(raw_code) is int and 100 <= raw_code <= 599:
                self.diagnostic_state["http_status"] = raw_code
        await super()._handle_message(message)
        if event in {"session.end", "error"} and not self._disconnecting:
            await self.set_usable(False)

    async def push_error(self, error_msg, exception=None, **kwargs):
        self._capture_exception(exception)
        await super().push_error(error_msg, exception=exception, **kwargs)

    async def push_error_frame(self, error, force_treat_as_permanent=False):
        self._capture_exception(getattr(error, "exception", None))
        code = getattr(self._websocket, "close_code", None)
        if isinstance(code, int):
            self.diagnostic_state["websocket_close_code"] = code
            self.diagnostic_state["websocket_close_reason"] = "provider_connection_closed"
        await super().push_error_frame(error, force_treat_as_permanent=force_treat_as_permanent)

    def _capture_exception(self, exception):
        if exception is not None:
            self.diagnostic_state["exception_type"] = safe_identifier(type(exception).__name__)
            response = getattr(exception, "response", None)
            status = getattr(response, "status_code", None)
            if type(status) is int and 100 <= status <= 599:
                self.diagnostic_state["http_status"] = status
            code = getattr(getattr(exception, "rcvd", None), "code", None)
            if isinstance(code, int):
                self.diagnostic_state["websocket_close_code"] = code
            # Never retain raw close text: it can echo caller data or credentials.
            self.diagnostic_state["websocket_close_reason"] = (
                "provider_connection_closed" if code else None
            )
