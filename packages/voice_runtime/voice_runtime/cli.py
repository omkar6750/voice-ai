import argparse
import asyncio

from pipecat.pipeline.worker import PipelineParams, PipelineWorker
from pipecat.workers.runner import WorkerRunner

from voice_runtime.config import default_agent_config
from voice_runtime.pipeline.build import build_pipeline, initial_frame
from voice_runtime.providers.demo import DemoProviderSettings, create_demo_services
from voice_runtime.telephony.session import TelephonySession
from voice_runtime.telephony.sim7600 import Sim7600Modem
from voice_runtime.telephony.usb_audio import Sim7600UsbAudioBridge

SAMPLE_RATE = 16000


async def run_agent(phone_number: str, modem_port: str, audio_port: str, baudrate: int) -> None:
    config = default_agent_config()
    services = create_demo_services(DemoProviderSettings(), config)
    modem = Sim7600Modem(modem_port, baudrate)
    session = TelephonySession(modem)
    audio = Sim7600UsbAudioBridge(audio_port, baudrate, sample_rate=SAMPLE_RATE).transport()
    pipeline, _context = build_pipeline(audio, services.stt, services.llm, services.tts, config)
    worker = PipelineWorker(
        pipeline,
        params=PipelineParams(
            enable_metrics=True,
            audio_in_sample_rate=SAMPLE_RATE,
            audio_out_sample_rate=SAMPLE_RATE,
        ),
    )
    runner = WorkerRunner(handle_sigint=True)
    await runner.add_workers(worker)
    await modem.ensure_pcm_format(SAMPLE_RATE)
    await session.start_call(phone_number)
    await worker.queue_frames([initial_frame()])
    try:
        await runner.run()
    finally:
        await session.end_call()
        await session.close()


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the local SIM7600 voice agent")
    parser.add_argument("--number", required=True)
    parser.add_argument("--modem-port", default="COM16")
    parser.add_argument("--audio-port", default="COM17")
    parser.add_argument("--baudrate", type=int, default=115200)
    args = parser.parse_args()
    asyncio.run(run_agent(args.number, args.modem_port, args.audio_port, args.baudrate))
