"""Reuse official Clerk clients; signing-key validation/cache stays in its SDK."""

import asyncio
from functools import lru_cache

import httpx
from clerk_backend_api import Clerk

from voice_api.core.config import get_settings


class ClerkClients:
    def __init__(self, secret: str):
        self.http = httpx.AsyncClient(
            timeout=3,
            follow_redirects=False,
            limits=httpx.Limits(max_connections=20, max_keepalive_connections=10),
        )
        self.sync_http = httpx.Client(
            timeout=3,
            follow_redirects=False,
            limits=httpx.Limits(max_connections=20, max_keepalive_connections=10),
        )
        self.sdk = Clerk(
            bearer_auth=secret, client=self.sync_http, async_client=self.http, timeout_ms=3000
        )
        # The SDK already caches keys and handles rotation. Avoid concurrent
        # cold-cache fetches without replacing its verification implementation.
        self.verification_lock = asyncio.Lock()

    async def close(self):
        await self.http.aclose()
        self.sync_http.close()


@lru_cache(maxsize=1)
def get_clerk_clients() -> ClerkClients:
    return ClerkClients(get_settings().clerk_secret_key)


async def close_clerk_clients():
    if get_clerk_clients.cache_info().currsize:
        await get_clerk_clients().close()
        get_clerk_clients.cache_clear()
