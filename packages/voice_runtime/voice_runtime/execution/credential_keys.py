"""Select server-resolved stage keys without process environment fallback."""


def stage_api_key(settings, stage: str, provider: str) -> str | None:
    keys = getattr(settings, "provider_stage_keys", None)
    if keys is not None:
        return keys.get(stage)
    # Reference demo/direct offline callers explicitly own their settings.
    return getattr(settings, f"{provider}_api_key", None)
