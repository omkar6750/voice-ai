import argparse
import asyncio

from pipecat.pipeline.worker import PipelineParams, PipelineWorker
from pipecat.transports.local.audio import LocalAudioTransport, LocalAudioTransportParams
from pipecat.workers.runner import WorkerRunner

from voice_runtime.config import default_agent_config
from voice_runtime.pipeline.build import build_pipeline, initial_frame
from voice_runtime.providers.openai import OpenAISettings, create_openai_services
from voice_runtime.telephony.sim7600 import Sim7600Transport


async def run_agent(phone_number: str, modem_port: str, baudrate: int, api_key: str) -> None:
    config = default_agent_config()
    modem = Sim7600Transport(modem_port, baudrate)
    await modem.dial(phone_number)
    audio = LocalAudioTransport(LocalAudioTransportParams())
    stt, llm, tts = create_openai_services(OpenAISettings(api_key=api_key), config)
    pipeline, _context = build_pipeline(audio, stt, llm, tts, config)
    worker = PipelineWorker(pipeline, params=PipelineParams(enable_metrics=True))
    runner = WorkerRunner(handle_sigint=True)
    await runner.add_workers(worker)
    await worker.queue_frames([initial_frame()])
    try:
        await runner.run()
    finally:
        await modem.hangup()
        await modem.close()


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the local SIM7600 voice agent")
    parser.add_argument("--number", required=True)
    parser.add_argument("--modem-port", required=True)
    parser.add_argument("--baudrate", type=int, default=115200)
    parser.add_argument("--openai-api-key", required=True)
    args = parser.parse_args()
    asyncio.run(run_agent(args.number, args.modem_port, args.baudrate, args.openai_api_key))
