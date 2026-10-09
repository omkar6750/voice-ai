from pipecat.services.cartesia.tts import CartesiaTTSService, GenerationConfig
from pipecat.services.sarvam.stt import SarvamRealtimeSTTService
from pipecat.services.sarvam.tts import SarvamTTSService
from voice_shared.dev_visibility import register_api_keys

from voice_runtime.execution.credential_keys import stage_api_key
from voice_runtime.execution.gnani import build_gnani_stt, build_gnani_tts


def build_speech_services(settings, snapshot: dict, sample_rate: int):
    """Use Sarvam realtime PCM and server endpointing for both supported models."""
    register_api_keys((getattr(settings, "provider_stage_keys", None) or {}).values())
    register_api_keys(
        [getattr(settings, "sarvam_api_key", None), getattr(settings, "cartesia_api_key", None)]
    )
    stt_config = snapshot["stt"]
    if stt_config["provider"] == "gnani":
        stt = build_gnani_stt(stage_api_key(settings, "stt", "gnani"), stt_config, sample_rate)
    elif stt_config["provider"] == "sarvam":
        if stt_config["model"] not in {"saaras:v3-realtime", "saaras:v4"}:
            raise ValueError(
                "Legacy Sarvam STT is unsupported; select saaras:v3-realtime or saaras:v4 in a new configuration revision"
            )
        realtime = stt_config.get("realtime") or {}
        stt = SarvamRealtimeSTTService(
            api_key=stage_api_key(settings, "stt", "sarvam"),
            settings=SarvamRealtimeSTTService.Settings(
                model=stt_config["model"],
                language_code=realtime.get("language_code", "auto"),
                mode=realtime.get("mode", "codemix"),
                stream_type=realtime.get("stream_type", "fast"),
                threshold=realtime.get("threshold", 0.3),
                silence_duration_ms=realtime.get("silence_duration_ms", 500),
                min_speech_duration_ms=realtime.get("min_speech_duration_ms", 250),
            ),
            sample_rate=sample_rate,
            endpointing="vad",
            prefix_padding_ms=realtime.get("prefix_padding_ms"),
            should_interrupt=snapshot.get("call_limits", {}).get("interruptions_enabled", True),
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
