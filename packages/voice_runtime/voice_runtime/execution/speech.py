from pipecat.services.cartesia.tts import CartesiaTTSService, GenerationConfig
from pipecat.services.sarvam.stt import SarvamSTTService
from pipecat.services.sarvam.tts import SarvamTTSService


def build_speech_services(settings, snapshot: dict, sample_rate: int):
    """Build STT/TTS services from the resolved snapshot's exact selections."""

    stt_config = snapshot["stt"]
    if stt_config["provider"] != "sarvam":
        raise ValueError(f"Unsupported STT provider: {stt_config['provider']}")
    stt = SarvamSTTService(
        api_key=settings.sarvam_api_key,
        settings=SarvamSTTService.Settings(model=stt_config["model"]),
        sample_rate=sample_rate,
    )

    tts_config = snapshot["tts"]
    if tts_config["provider"] == "sarvam":
        tts = SarvamTTSService(
            api_key=settings.sarvam_api_key,
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
            api_key=settings.cartesia_api_key,
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
