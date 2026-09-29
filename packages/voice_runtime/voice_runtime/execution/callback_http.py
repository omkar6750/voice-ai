"""HTTP response handling for callback scheduling requests."""

from typing import Any

import httpx


class CallbackHTTPError(Exception):
    """A callback endpoint returned a non-success HTTP status."""

    def __init__(self, status_code: int) -> None:
        self.status_code = status_code
        super().__init__(f"Callback scheduling service returned HTTP {status_code}")


async def post_callback_json(
    client: httpx.AsyncClient,
    endpoint: str,
    payload: dict[str, Any],
    token: str,
) -> dict[str, Any]:
    """Post once and require a successful JSON object response."""
    response = await client.post(
        endpoint,
        json=payload,
        headers={"Authorization": f"Bearer {token}"},
    )
    if not response.is_success:
        raise CallbackHTTPError(response.status_code)
    result = response.json()
    if not isinstance(result, dict):
        raise ValueError("Callback API returned an invalid result")
    return result
