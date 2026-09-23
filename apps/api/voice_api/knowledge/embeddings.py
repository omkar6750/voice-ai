"""HTTP adapter documented at https://ai.google.dev/api/embeddings.

Gemini embedding 001 reduced dimensions require explicit L2 normalization:
https://ai.google.dev/gemini-api/docs/embeddings#ensuring-quality-for-smaller-dimensions
"""

import math
from typing import Protocol

import httpx

MODEL = "gemini-embedding-001"
DIMENSIONS = 768


class Embedder(Protocol):
    async def embed(self, text: str, *, query: bool = False, title: str = "") -> list[float]: ...


def normalize(values: list[float]) -> list[float]:
    if len(values) != DIMENSIONS or not all(math.isfinite(x) for x in values):
        raise ValueError("Expected 768 finite embedding dimensions")
    norm = math.hypot(*values)
    if not norm or not math.isfinite(norm):
        raise ValueError("Embedding must have a finite nonzero norm")
    return [x / norm for x in values]


class GeminiEmbedder:
    def __init__(self, api_key: str, client: httpx.AsyncClient):
        if not api_key:
            raise ValueError("Gemini embedding API key is not configured")
        self._api_key = api_key
        self._client = client

    async def embed(self, text: str, *, query: bool = False, title: str = "") -> list[float]:
        config = {
            "taskType": "RETRIEVAL_QUERY" if query else "RETRIEVAL_DOCUMENT",
            "outputDimensionality": DIMENSIONS,
        }
        if title and not query:
            config["title"] = title
        response = await self._client.post(
            f"https://generativelanguage.googleapis.com/v1beta/models/{MODEL}:embedContent",
            headers={"x-goog-api-key": self._api_key},
            json={"content": {"parts": [{"text": text}]}, "embedContentConfig": config},
            timeout=10,
        )
        response.raise_for_status()
        return normalize(response.json()["embedding"]["values"])
