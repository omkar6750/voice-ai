"""Meta Cloud API adapter. URLs are fixed; redirects and automatic retries are disabled."""

import copy
import hashlib
import hmac
import re
from urllib.parse import urlparse

import httpx
from voice_runtime.execution.whatsapp import (
    InboundWindow,
    recipient,
    shared_inbound_window,
)

_inbound_window = shared_inbound_window


class ProviderError(RuntimeError):
    def __init__(self, status_code: int | None = None, *, uncertain: bool = False):
        super().__init__(
            "WhatsApp request outcome is uncertain" if uncertain else "WhatsApp request failed"
        )
        self.status_code = status_code
        self.uncertain = uncertain


def graph_id(value: str) -> str:
    if not re.fullmatch(r"[0-9]+", value):
        raise ValueError("Expected a numeric Meta resource ID")
    return value


def verify_signature(body: bytes, signature: str | None, app_secret: str) -> bool:
    if not app_secret or not signature:
        return False
    expected = "sha256=" + hmac.new(app_secret.encode(), body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected.encode(), signature.encode())


def message_payload(to: str, *, template: dict | None = None, text: str | None = None) -> dict:
    payload = {"messaging_product": "whatsapp", "recipient_type": "individual", "to": recipient(to)}
    if template is not None and text is None:
        if not template.get("name") or not template.get("language", {}).get("code"):
            raise ValueError("Template name and language code are required")
        payload.update(type="template", template=copy.deepcopy(template))
    elif text and template is None:
        if len(text) > 4096:
            raise ValueError("Text exceeds WhatsApp length limit")
        payload.update(type="text", text={"body": text, "preview_url": False})
    else:
        raise ValueError("Provide either a template or nonempty text")
    return payload


class WhatsAppAdapter:
    def __init__(
        self,
        token: str,
        phone_number_id: str,
        waba_id: str,
        api_version: str,
        *,
        transport: httpx.AsyncBaseTransport | None = None,
    ):
        if not token or not re.fullmatch(r"v[0-9]+\.0", api_version):
            raise ValueError("WhatsApp token and explicit Graph API version are required")
        self.phone_number_id = graph_id(phone_number_id)
        self.waba_id = graph_id(waba_id)
        self.client = httpx.AsyncClient(
            base_url=f"https://graph.facebook.com/{api_version}/",
            headers={"Authorization": f"Bearer {token}"},
            timeout=30,
            follow_redirects=False,
            trust_env=False,
            transport=transport,
        )

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_):
        await self.client.aclose()

    async def _request(self, method: str, path: str, **kwargs) -> dict:
        try:
            response = await self.client.request(method, path, **kwargs)
        except httpx.RequestError:
            raise ProviderError(uncertain=method == "POST") from None
        if not response.is_success:
            raise ProviderError(
                response.status_code, uncertain=method == "POST" and response.status_code >= 500
            )
        try:
            data = response.json()
            if not isinstance(data, dict) or "error" in data:
                raise ValueError
            return data
        except ValueError:
            raise ProviderError(uncertain=method == "POST") from None

    async def template_catalog(self) -> list[dict]:
        templates, seen = [], set()
        params = {"fields": "id,name,status,language,category,components", "limit": "100"}
        for _ in range(100):
            page = await self._request("GET", f"{self.waba_id}/message_templates", params=params)
            templates.extend(page.get("data", []))
            paging = page.get("paging", {})
            if not paging.get("next"):
                return templates
            after = paging.get("cursors", {}).get("after")
            if not isinstance(after, str) or after in seen:
                raise ProviderError()
            seen.add(after)
            params["after"] = after  # Never follow provider-supplied URLs containing credentials.
        raise ProviderError()

    async def upload_media(self, filename: str, mime_type: str, content: bytes) -> dict:
        return await self._request(
            "POST",
            f"{self.phone_number_id}/media",
            data={"messaging_product": "whatsapp", "type": mime_type},
            files={"file": (filename, content, mime_type)},
        )

    async def check_media(self, media_id: str) -> dict:
        return await self._request(
            "GET", graph_id(media_id), params={"phone_number_id": self.phone_number_id}
        )

    async def delete_media(self, media_id: str) -> None:
        """Delete provider media; absence is idempotent success."""
        try:
            response = await self.client.delete(
                graph_id(media_id), params={"phone_number_id": self.phone_number_id}
            )
        except httpx.RequestError:
            raise ProviderError(uncertain=True) from None
        if response.status_code == 404:
            return
        if not response.is_success:
            raise ProviderError(response.status_code)
        if response.status_code != 204:
            try:
                result = response.json()
            except ValueError:
                raise ProviderError(response.status_code) from None
            if not isinstance(result, dict) or result.get("success") is not True:
                raise ProviderError(response.status_code)

    async def preview_image(self, media_id: str, *, max_bytes: int) -> tuple[bytes, str]:
        """Fetch a short-lived Meta media URL without persisting bytes or URL."""
        metadata = await self.check_media(media_id)
        url = metadata.get("url")
        mime_type = metadata.get("mime_type")
        if mime_type not in {"image/png", "image/jpeg"} or not isinstance(url, str):
            raise ProviderError()
        parsed = urlparse(url)
        host = (parsed.hostname or "").lower().rstrip(".")
        allowed_host = (
            host == "facebook.com"
            or host.endswith(".facebook.com")
            or host == "fbsbx.com"
            or host.endswith(".fbsbx.com")
        )
        if (
            parsed.scheme != "https"
            or not allowed_host
            or not parsed.path
            or parsed.username is not None
            or parsed.password is not None
            or parsed.port not in (None, 443)
            or parsed.fragment
        ):
            raise ProviderError()
        try:
            async with self.client.stream("GET", url) as response:
                if not response.is_success:
                    raise ProviderError(response.status_code)
                response_type = response.headers.get("content-type", "").split(";", 1)[0].lower()
                if response_type not in {"image/png", "image/jpeg"} or response_type != mime_type:
                    raise ProviderError()
                length = response.headers.get("content-length")
                if length and int(length) > max_bytes:
                    raise ProviderError()
                chunks = bytearray()
                async for chunk in response.aiter_bytes():
                    if len(chunks) + len(chunk) > max_bytes:
                        raise ProviderError()
                    chunks.extend(chunk)
                if not chunks:
                    raise ProviderError()
                return bytes(chunks), response_type
        except (httpx.RequestError, ValueError):
            raise ProviderError(uncertain=True) from None

    async def send(self, payload: dict) -> str:
        result = await self._request("POST", f"{self.phone_number_id}/messages", json=payload)
        try:
            message_id = result["messages"][0]["id"]
            if not isinstance(message_id, str) or not message_id:
                raise ValueError
            return message_id
        except (KeyError, IndexError, TypeError, ValueError):
            raise ProviderError(uncertain=True) from None


__all__ = [
    "InboundWindow",
    "ProviderError",
    "WhatsAppAdapter",
    "_inbound_window",
    "graph_id",
    "message_payload",
    "recipient",
    "verify_signature",
]
