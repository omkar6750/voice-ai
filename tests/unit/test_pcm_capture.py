import asyncio
import wave
from unittest.mock import AsyncMock

import numpy as np
import pytest
from pipecat.frames.frames import OutputAudioRawFrame
from voice_runtime.call_capture import CallCapture
from voice_runtime.telephony.usb_audio import Sim7600UsbAudioParams, _Sim7600AudioOutput


def test_recordings_share_timeline_and_mix_with_clipping(tmp_path):
    now = [0.0]
    capture = CallCapture(tmp_path, clock=lambda: now[0])
    samples = np.full(160, 20000, dtype="<i2").tobytes()
    now[0] = 0.1
    capture.pcm("output", samples)
    now[0] = 0.12
    capture.pcm("input", samples)
    now[0] = 0.2
    capture.close()
    capture.close()
    for name in ("input", "output", "mixed"):
        with wave.open(str(tmp_path / f"{name}.wav")) as wav:
            assert (wav.getframerate(), wav.getsampwidth(), wav.getnchannels()) == (8000, 2, 1)
            assert wav.getnframes() == 1600
            values = np.frombuffer(wav.readframes(1600), "<i2")
            assert not values[:800].any()
            assert (values[800:960] == (32767 if name == "mixed" else 20000)).all()
            assert not values[960:].any()


@pytest.mark.asyncio
async def test_serial_output_is_paced_and_cancellation_stops_remaining_audio():
    owner = AsyncMock()
    params = Sim7600UsbAudioParams(
        audio_port="fake", audio_out_enabled=True, audio_out_sample_rate=8000
    )
    output = _Sim7600AudioOutput(owner, params)
    output._sample_rate = 8000
    frame = OutputAudioRawFrame(b"\0" * 3200, 8000, 1)
    job = asyncio.create_task(output.write_audio_frame(frame))
    await asyncio.sleep(0.005)
    job.cancel()
    await asyncio.gather(job, return_exceptions=True)
    assert owner.write.await_count == 1
    assert len(owner.write.call_args.args[0]) == 320


@pytest.mark.asyncio
async def test_wrong_modem_rate_is_rejected():
    owner = AsyncMock()
    output = _Sim7600AudioOutput(owner, Sim7600UsbAudioParams(audio_port="fake"))
    with pytest.raises(ValueError, match="16 kHz"):
        await output.write_audio_frame(OutputAudioRawFrame(b"\0" * 320, 8000, 1))
    owner.write.assert_not_awaited()


@pytest.mark.asyncio
async def test_frame_pushed_capture_for_injected_transport(tmp_path):
    from types import SimpleNamespace

    from pipecat.frames.frames import InputAudioRawFrame, OutputAudioRawFrame
    from pipecat.observers.base_observer import FramePushed
    from pipecat.transports.base_input import BaseInputTransport
    from pipecat.transports.base_output import BaseOutputTransport

    capture = CallCapture(tmp_path, sample_rate=8000)

    from unittest.mock import MagicMock

    input_transport = MagicMock(spec=BaseInputTransport)
    input_transport.name = "input_transport"
    input_frame = InputAudioRawFrame(b"\x10\x20" * 80, 8000, 1)
    await capture.on_push_frame(
        FramePushed(
            source=input_transport,
            destination=SimpleNamespace(name="stt"),
            frame=input_frame,
            direction=SimpleNamespace(name="UPSTREAM"),
            timestamp=0,
        )
    )

    # Simulate frame pushed to BaseOutputTransport
    output_transport = MagicMock(spec=BaseOutputTransport)
    output_transport.name = "output_transport"
    output_frame = OutputAudioRawFrame(b"\x30\x40" * 80, 8000, 1)
    await capture.on_push_frame(
        FramePushed(
            source=SimpleNamespace(name="tts"),
            destination=output_transport,
            frame=output_frame,
            direction=SimpleNamespace(name="DOWNSTREAM"),
            timestamp=0,
        )
    )

    capture.close()
    assert (tmp_path / "input.wav").is_file()
    assert (tmp_path / "output.wav").is_file()
    assert (tmp_path / "mixed.wav").is_file()
