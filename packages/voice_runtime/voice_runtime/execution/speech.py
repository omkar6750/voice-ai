import io
import json
import wave

from pipecat.services.cartesia.tts import CartesiaTTSService, GenerationConfig
from pipecat.services.sarvam.stt import SarvamSTTService
from pipecat.services.sarvam.tts import SarvamTTSService

from voice_runtime.execution.credential_keys import stage_api_key
from voice_runtime.execution.gnani import build_gnani_stt, build_gnani_tts


class _WavChunkSarvamSTTService(SarvamSTTService):
    """Wrap Pipecat's raw PCM input in WAV before using its WAV-only SDK path."""

    _ERROR_PREFIX = "SARVAM_STT_PROVIDER_ERROR:"

    def _as_wav(self, pcm: bytes) -> bytes:
        buffer = io.BytesIO()
        with wave.open(buffer, "wb") as audio_file:
            audio_file.setnchannels(1)
            audio_file.setsampwidth(2)
            audio_file.setframerate(self.sample_rate)
            audio_file.writeframes(pcm)
        return buffer.getvalue()

    async def run_stt(self, audio: bytes):
        async for frame in super().run_stt(self._as_wav(audio)):
            yield frame

    async def _send_keepalive(self, silence: bytes):
        # Pipecat's default keepalive uses the same `audio/wav` label as speech.
        # Keep its silence packets valid too, so they cannot poison the stream.
        await super()._send_keepalive(self._as_wav(silence))

    async def _handle_message(self, message):
        if getattr(message, "type", None) == "error":
            data = getattr(message, "data", None)
            status = _safe_provider_status(data)
            code = _safe_provider_code(data)
            payload = json.dumps({"status_code": status, "code": code}, separators=(",", ":"))
            await self.push_error(error_msg=f"{self._ERROR_PREFIX}{payload}")
            return
        await super()._handle_message(message)


def _safe_provider_status(data) -> int | None:
    value = _provider_field(data, "status_code", "http_status", "status")
    return value if type(value) is int and 100 <= value <= 599 else None


def _safe_provider_code(data) -> str | None:
    value = _provider_field(data, "code", "error_code")
    if (
        type(value) is str
        and 0 < len(value) <= 80
        and all(char.isascii() and (char.isalnum() or char in "_.-") for char in value)
    ):
        return value
    return None


def _provider_field(data, *names):
    if isinstance(data, dict):
        for name in names:
            value = data.get(name)
            if value is not None:
                return value
        nested = data.get("error")
    else:
        for name in names:
            value = getattr(data, name, None)
            if value is not None:
                return value
        nested = getattr(data, "error", None)
    if nested is not None and nested is not data:
        return _provider_field(nested, *names)
    return None


def build_speech_services(settings, snapshot: dict, sample_rate: int):
    """Build STT/TTS services from the resolved snapshot's exact selections."""

    stt_config = snapshot["stt"]
    if stt_config["provider"] == "gnani":
        stt = build_gnani_stt(stage_api_key(settings, "stt", "gnani"), stt_config, sample_rate)
    elif stt_config["provider"] == "sarvam":
        stt = _WavChunkSarvamSTTService(
            api_key=stage_api_key(settings, "stt", "sarvam"),
            settings=SarvamSTTService.Settings(model=stt_config["model"]),
            sample_rate=sample_rate,
        )
    else:
        raise ValueError(f"Unsupported STT provider: {stt_config['provider']}")

    tts_config = snapshot["tts"]
    if tts_config["provider"] == "gnani":
        tts = build_gnani_tts(stage_api_key(settings, "tts", "gnani"), tts_config, sample_rate)
    elif tts_config["provider"] == "sarvam":
        tts = SarvamTTSService(
            api_key=stage_api_key(settings, "tts", "sarvam"),
            settings=SarvamTTSService.Settings(
                model=tts_config["model"],
                voice=tts_config["voice"],
                language=tts_config["language"],
                pace=tts_config["pace"],
            ),
            sample_rate=sample_rate,
        )
    elif tts_config["provider"] == "cartesia":
        cartesia = tts_config.get("cartesia") or {}
        cartesia_settings = {}
        if cartesia.get("generation_config"):
            cartesia_settings["generation_config"] = GenerationConfig(
                **cartesia["generation_config"]
            )
        if cartesia.get("pronunciation_dict_id"):
            cartesia_settings["pronunciation_dict_id"] = cartesia["pronunciation_dict_id"]
        tts = CartesiaTTSService(
            api_key=stage_api_key(settings, "tts", "cartesia"),
            settings=CartesiaTTSService.Settings(
                model=tts_config["model"],
                voice=tts_config["voice"],
                language=tts_config["language"],
                **cartesia_settings,
            ),
            sample_rate=sample_rate,
            encoding="pcm_s16le",
            container="raw",
        )
    else:
        raise ValueError(f"Unsupported TTS provider: {tts_config['provider']}")
    return stt, tts
