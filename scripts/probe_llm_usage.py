"""Probe live streaming LLM usage without printing credentials or generated text.

Run with ``uv run python scripts/probe_llm_usage.py``. Each provider receives one
short prompt. The output contains only usage metadata and Groq rate-limit headers.
"""

import asyncio
import json
import sys

import httpx
from voice_api.core.config import get_settings


async def _stream_usage(
    client: httpx.AsyncClient, url: str, headers: dict[str, str], payload: dict
) -> dict:
    usage = None
    rate_headers = {}
    async with client.stream("POST", url, headers=headers, json=payload) as response:
        rate_headers = {
            key: value
            for key, value in response.headers.items()
            if key.lower().startswith("x-ratelimit-") or key.lower() == "retry-after"
        }
        if response.status_code != 200:
            try:
                body = await response.aread()
                message = json.loads(body).get("error", {}).get("message", "")
            except (ValueError, AttributeError):
                message = ""
            for secret in headers.values():
                if secret:
                    message = message.replace(secret, "[REDACTED]")
            return {
                "status": response.status_code,
                "error": message[:300],
                "rate_headers": rate_headers,
            }
        async for line in response.aiter_lines():
            if not line.startswith("data: ") or line == "data: [DONE]":
                continue
            try:
                chunk = json.loads(line[6:])
            except json.JSONDecodeError:
                continue
            latest = chunk.get("usage") or chunk.get("usageMetadata")
            if latest:
                usage = latest
    return {"status": 200, "usage": usage, "rate_headers": rate_headers}


async def main() -> None:
    settings = get_settings()
    selected = set(sys.argv[1:]) or {"groq", "gemini"}
    async with httpx.AsyncClient(timeout=30) as client:
        if "groq" in selected and settings.groq_api_key:
            groq = await _stream_usage(
                client,
                "https://api.groq.com/openai/v1/chat/completions",
                {"Authorization": f"Bearer {settings.groq_api_key}"},
                {
                    "model": "qwen/qwen3.8-27b",
                    "messages": [{"role": "user", "content": "Reply with the word hello."}],
                    "stream": True,
                    "stream_options": {"include_usage": True},
                    "max_completion_tokens": 16,
                },
            )
            print(json.dumps({"provider": "groq", **groq}))
        elif "groq" in selected:
            print(json.dumps({"provider": "groq", "status": "key_missing"}))

        if "gemini" in selected and settings.gemini_api_key:
            models_response = await client.get(
                "https://generativelanguage.googleapis.com/v1beta/models",
                headers={"x-goog-api-key": settings.gemini_api_key},
            )
            if models_response.status_code != 200:
                print(
                    json.dumps(
                        {"provider": "gemini", "status": models_response.status_code,
                         "stage": "list_models"}
                    )
                )
                return
            models = [
                row["name"]
                for row in models_response.json().get("models", [])
                if "generateContent" in row.get("supportedGenerationMethods", [])
                and "flash" in row.get("name", "")
            ]
            preferred = (
                "models/gemini-3.5-flash-lite",
                "models/gemini-3-flash",
                "models/gemini-2.5-flash-lite",
                "models/gemini-2.5-flash",
            )
            model = next((name for name in preferred if name in models), None)
            if model is None:
                model = next((name for name in models if "lite" in name), None)
            if model is None:
                model = next(iter(models), None)
            if model is None:
                print(json.dumps({"provider": "gemini", "status": "no_flash_model"}))
                return
            gemini = await _stream_usage(
                client,
                f"https://generativelanguage.googleapis.com/v1beta/{model}:streamGenerateContent?alt=sse",
                {"x-goog-api-key": settings.gemini_api_key},
                {
                    "contents": [{"parts": [{"text": "Reply with the word hello."}]}],
                    "generationConfig": {"maxOutputTokens": 16},
                },
            )
            print(json.dumps({"provider": "gemini", "model": model, **gemini}))
        elif "gemini" in selected:
            print(json.dumps({"provider": "gemini", "status": "key_missing"}))


if __name__ == "__main__":
    asyncio.run(main())
