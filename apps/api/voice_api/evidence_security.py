"""Backend redaction boundary; adapters must additionally exclude action credentials."""

from voice_runtime.execution.redaction import redact

from voice_api.config import get_settings


def safe_evidence(value):
    settings = get_settings()
    return redact(
        value,
        (
            settings.cartesia_api_key,
            settings.sarvam_api_key,
            settings.groq_api_key,
            settings.gemini_api_key,
            settings.operator_token,
        ),
    )
