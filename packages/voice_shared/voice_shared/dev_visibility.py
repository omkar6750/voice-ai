"""Development diagnostics preserve content while hiding API authentication keys."""

import os
import re

_environment = "prod"
_api_keys: set[str] = set()
_key_field = re.compile(
    r"(?:^|_)(?:api_?keys?|api_subscription_key|subscription_key|authorization|"
    r"x_api_key|integration_keys|private_key|password|client_secret|access_token|"
    r"refresh_token|service_token|control_token|cookie|set_cookie|x_voice_runtime_token)$",
    re.I,
)
_inline_key = re.compile(
    r"(?i)(\b(?:api[_-]?key|api[_-]?subscription[_-]?key|subscription[_-]?key)"
    r"\s*[=:]\s*[\"']?)([^\s\"'&,;}]+)"
)
_bearer = re.compile(r"(?i)(\bBearer\s+)[A-Za-z0-9._~+/=-]+")


def configure(environment: str, api_keys=()):
    global _environment
    _environment = environment
    register_api_keys(api_keys)


def is_development() -> bool:
    return os.getenv("VOICE_ENV", _environment).casefold() in {"dev", "development", "local"}


def register_api_keys(values):
    _api_keys.update(value for value in values if isinstance(value, str) and value)


def redact_api_keys(value, key="", api_keys=()):
    if _key_field.search(str(key).replace("-", "_")):
        return "[REDACTED]"
    if isinstance(value, dict):
        return {str(k): redact_api_keys(v, str(k), api_keys) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [redact_api_keys(v, api_keys=api_keys) for v in value]
    if isinstance(value, str):
        keys = _api_keys.union(k for k in api_keys if isinstance(k, str) and k)
        for secret in sorted(keys, key=len, reverse=True):
            if secret:
                value = value.replace(secret, "[REDACTED]")
        value = _inline_key.sub(r"\1[REDACTED]", value)
        return _bearer.sub(r"\1[REDACTED]", value)
    if value is None or isinstance(value, (bool, int, float)):
        return value
    return redact_api_keys(str(value), api_keys=api_keys)
