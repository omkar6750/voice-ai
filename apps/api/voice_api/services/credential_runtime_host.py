"""Lease lifecycle around the native host without changing its logging or teardown."""

import asyncio

from voice_runtime.execution.native import NativePipelineHost

from voice_api.services.credential_lease_service import (
    CLEANUP_SECONDS,
    HANDSHAKE_SECONDS,
    call_seconds,
    guard,
    release,
)


class CredentialRuntimeHost(NativePipelineHost):
    async def prepare(self, snapshot, tracker, **kwargs):
        return await guard(self.run_id, lambda: super(CredentialRuntimeHost, self).prepare(snapshot, tracker, **kwargs),
                           timeout_secs=HANDSHAKE_SECONDS)

    async def converse(self, modem_or_check=None):
        return await guard(self.run_id, lambda: super(CredentialRuntimeHost, self).converse(modem_or_check),
                           timeout_secs=call_seconds(self.settings, self._snapshot))

    async def close(self):
        try:
            async with asyncio.timeout(CLEANUP_SECONDS):
                return await super().close()
        finally:
            await release(self.run_id)
            # Best-effort drop of the host's references; Python cannot promise memory erasure.
            self.settings = None
