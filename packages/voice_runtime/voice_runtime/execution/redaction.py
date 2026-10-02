"""Remove credential fields and known secret values before persisting evidence."""

import re
from collections.abc import Iterable

_SECRET_FIELD = re.compile(
    r"(?:^|_)(?:api_key|access_token|refresh_token|authorization|password|"
    r"app_secret|client_secret|verify_token|operator_token|runtime_service_token|integration_keys|ciphertext|"
    r"cookie|set_cookie|ticket|grant|upload_grant|signed_url|auth_token|api_key_secret|decrypted_byok)$",
    re.IGNORECASE,
)


def redact(value, secrets: Iterable[str] = ()):
    known = tuple(
        sorted({s for s in secrets if isinstance(s, str) and len(s) >= 6}, key=len, reverse=True)
    )

    def clean(item):
        if isinstance(item, dict):
            return {
                key: "<redacted>"
                if _SECRET_FIELD.search(str(key).replace("-", "_"))
                else clean(val)
                for key, val in item.items()
            }
        if isinstance(item, (list, tuple)):
            return [clean(val) for val in item]
        if isinstance(item, str):
            for secret in known:
                item = item.replace(secret, "<redacted>")
        return item

    return clean(value)
