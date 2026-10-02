"""Gnani SDK adapters for the supported Pipecat version.

Vendor plugin 0.5.12 imports a removed private Pipecat settings symbol. Keep
the SDK behind these local services, using public Pipecat service contracts.
"""

import asyncio
import logging
from contextlib import suppress

from gnani.stt import GnaniSTTStreamClient, StreamErrorEvent, StreamTranscriptEvent
from gnani.tts import AudioConfig, GnaniTTSRealtimeClient, TTSAudioChunkEvent, TTSCompletedEvent
from pipecat.frames.frames import (
    InterimTranscriptionFrame,
    TranscriptionFrame,
    TTSAudioRawFrame,
    TTSStoppedFrame,
)
from pipecat.services.settings import STTSettings, TTSSettings
from pipecat.services.stt_service import STTService
from pipecat.services.tts_service import TTSService
from pipecat.transcriptions.language import Language
from pipecat.utils.time import time_now_iso8601
from pipecat.utils.tracing.service_decorators import traced_stt, traced_tts

from voice_runtime.contracts.providers import STTConfig, TTSConfig

# The SDK installs a raw stderr handler at import. Runtime evidence supplies
# metrics/errors; suppress vendor logs so payloads cannot bypass safe logging.
logging.getLogger("gnani").disabled = True


def _require_key(api_key):
    if not api_key:
        raise ValueError("Select a stored Gnani credential for the speech stage")
    return api_key


class RuntimeGnaniSTTService(STTService):
    Settings = STTSettings

    def __init__(self, *, api_key, config, sample_rate):
        self.config = STTConfig.model_validate(config)
        super().__init__(
            sample_rate=sample_rate,
            settings=self.Settings(
                model=self.config.model, language=Language(self.config.language)
            ),
        )
        self._client = GnaniSTTStreamClient(
            api_key=_require_key(api_key),
            language_code=self.config.language,
            sample_rate=sample_rate,
        )
        self._receive_task = None
        self._pcm_pending = bytearray()
        self._closing = False

    def can_generate_metrics(self):
        return True

    async def _fail(self, exception=None):
        await self.push_error(
            "Gnani STT failed", exception=exception, force_treat_as_permanent=True
        )

    async def start(self, frame):
        await super().start(frame)
        try:
            async with asyncio.timeout(15):
                await self._client.connect()
            self._receive_task = asyncio.create_task(self._receive_messages())
            await self._call_event_handler("on_connected")
        except Exception as exc:
            await self._client.close()
            await self._fail(exc)

    @traced_stt
    async def _handle_transcription(self, transcript, is_final, language=None):
        pass

    async def _receive_messages(self):
        try:
            async for event in self._client:
                if isinstance(event, StreamTranscriptEvent) and event.text:
                    final = event.raw.get("is_final", True)
                    await self._handle_transcription(event.text, final, self._settings.language)
                    frame_type = TranscriptionFrame if final else InterimTranscriptionFrame
                    await self.push_frame(
                        frame_type(
                            text=event.text,
                            user_id="",
                            timestamp=event.timestamp or time_now_iso8601(),
                            language=self._settings.language,
                        )
                    )
                elif isinstance(event, StreamErrorEvent):
                    await self._fail()
                    return
            if not self._closing:
                await self._fail(ConnectionError("Gnani STT stream closed"))
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            await self._fail(exc)

    async def run_stt(self, audio):
        # Input is paced by the transport. Hold only a sub-frame remainder.
        self._pcm_pending.extend(audio)
        try:
            while len(self._pcm_pending) >= 1024:
                chunk = bytes(self._pcm_pending[:1024])
                del self._pcm_pending[:1024]
                await self._client.send_audio(chunk)
        except Exception as exc:
            self._pcm_pending.clear()
            # Replaying an uncertain send could duplicate speech. Stop instead.
            await self._fail(exc)
        yield None

    async def _close(self):
        self._closing = True
        self._pcm_pending.clear()
        if self._receive_task:
            self._receive_task.cancel()
            with suppress(asyncio.CancelledError):
                await self._receive_task
            self._receive_task = None
        await self._client.close()

    async def stop(self, frame):
        await self._close()
        await super().stop(frame)

    async def cancel(self, frame):
        await self._close()
        await super().cancel(frame)

    async def cleanup(self):
        await self._close()
        await super().cleanup()


class RuntimeGnaniTTSService(TTSService):
    Settings = TTSSettings

    def __init__(self, *, api_key, config, sample_rate):
        self.config = TTSConfig.model_validate(config)
        super().__init__(
            sample_rate=sample_rate,
            push_start_frame=True,
            settings=self.Settings(
                model=self.config.model, voice=self.config.voice, language=self.config.language
            ),
        )
        self._client = GnaniTTSRealtimeClient(api_key=_require_key(api_key))
        self._audio_config = AudioConfig(
            sample_rate=sample_rate,
            encoding="linear_pcm",
            container="raw",
            num_channels=1,
            sample_width=2,
        )

    def can_generate_metrics(self):
        return True

    @traced_tts
    async def run_tts(self, text, context_id):
        stream = self._client.synthesize_events(
            text,
            voice=self._settings.voice,
            model=self._settings.model,
            language=self._settings.language,
            speed=self.config.pace,
            audio_config=self._audio_config,
        )
        completed = False
        pending = b""
        try:
            await self.start_ttfb_metrics()
            await self.start_tts_usage_metrics(text)
            # A missing terminal event or an idle socket cannot leave the
            # conversation waiting forever. Cancellation closes the SDK socket.
            async with asyncio.timeout(30):
                async for event in stream:
                    if isinstance(event, TTSAudioChunkEvent):
                        audio = pending + event.data
                        length = len(audio) - len(audio) % 2
                        pending = audio[length:]
                        if length:
                            await self.stop_ttfb_metrics()
                            yield TTSAudioRawFrame(
                                audio=audio[:length],
                                sample_rate=self._audio_config.sample_rate,
                                num_channels=1,
                                context_id=context_id,
                            )
                    elif isinstance(event, TTSCompletedEvent):
                        completed = True
            if not completed or pending:
                raise ConnectionError("Gnani TTS stream ended before complete PCM output")
            yield TTSStoppedFrame(context_id=context_id)
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            await self.push_error("Gnani TTS failed", exception=exc, force_treat_as_permanent=True)
        finally:
            await stream.aclose()
            await self.stop_ttfb_metrics()


def build_gnani_stt(api_key, config, sample_rate):
    return RuntimeGnaniSTTService(api_key=api_key, config=config, sample_rate=sample_rate)


def build_gnani_tts(api_key, config, sample_rate):
    return RuntimeGnaniTTSService(api_key=api_key, config=config, sample_rate=sample_rate)
