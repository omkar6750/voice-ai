"""Bulbul v4 compatibility for pinned Pipecat 1.11.0.

Only construction/configuration differs. Streaming, completion, interruption and
socket lifecycle remain owned by Pipecat. No global upstream tables are changed.
"""

import json
from dataclasses import replace

from pipecat.services.sarvam.tts import SarvamTTSService

from voice_runtime.execution.sarvam_stt import safe_identifier


class DiagnosticSarvamTTSService(SarvamTTSService):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.diagnostic_state = {}

    def _get_websocket(self):
        websocket = super()._get_websocket()

        async def observed_messages():
            async for raw in websocket:
                if isinstance(raw, str):
                    try:
                        message = json.loads(raw)
                    except ValueError:
                        message = {}
                    data = message.get("data") or {}
                    if isinstance(data, dict):
                        request_id = safe_identifier(
                            data.get("request_id") or message.get("request_id")
                        )
                        if request_id:
                            self.diagnostic_state["provider_request_id"] = request_id
                        if message.get("type") == "error":
                            code = data.get("code")
                            safe_code = safe_identifier(code) or (
                                str(code) if type(code) is int else None
                            )
                            if safe_code:
                                self.diagnostic_state["provider_error_code"] = safe_code
                            if type(code) is int and 100 <= code <= 599:
                                self.diagnostic_state["http_status"] = code
                yield raw

        return observed_messages()


class BulbulV4TTSService(DiagnosticSarvamTTSService):
    def __init__(self, *, api_key, settings, sample_rate, **kwargs):
        if settings.model != "bulbul:v4-flash" or sample_rate not in {8000, 16000}:
            raise ValueError("Bulbul v4 requires an explicit model and supported run PCM rate")
        # The pinned constructor rejects unknown models and clears v3-only fields.
        # Bootstrap its unchanged streaming machinery, then restore v4 settings.
        original = replace(settings)
        compatible = replace(
            settings, model="bulbul:v3", pitch=None, loudness=None, temperature=None
        )
        super().__init__(
            api_key=api_key,
            settings=compatible,
            sample_rate=sample_rate,
            output_audio_codec="linear16",
            **kwargs,
        )
        self._settings.model = original.model
        self._settings.pitch = original.pitch if isinstance(original.pitch, (int, float)) else 0.0
        self._settings.loudness = (
            original.loudness if isinstance(original.loudness, (int, float)) else 1.0
        )
        self._settings.temperature = None
        self._settings.enable_preprocessing = (
            original.enable_preprocessing
            if isinstance(original.enable_preprocessing, bool)
            else True
        )
        self._websocket_url = self._websocket_url.replace(
            "model=bulbul:v3", "model=bulbul:v4-flash"
        )

    async def _send_config(self):
        if not self._websocket:
            raise RuntimeError("WebSocket not connected")
        await self._websocket.send(
            json.dumps(
                {
                    "type": "config",
                    "data": {
                        "target_language_code": self._settings.language,
                        "speaker": self._settings.voice,
                        "speech_sample_rate": self._speech_sample_rate,
                        "output_audio_codec": "linear16",
                        "pace": self._settings.pace,
                        "pitch": self._settings.pitch,
                        "loudness": self._settings.loudness,
                        "enable_preprocessing": self._settings.enable_preprocessing,
                        "min_buffer_size": self._settings.min_buffer_size,
                        "max_chunk_length": self._settings.max_chunk_length,
                    },
                }
            )
        )
