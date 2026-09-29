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
) -> Any:
    """Post once, reject HTTP errors before decoding, and return the success JSON."""
    response = await client.post(
        endpoint,
        json=payload,
        headers={"Authorization": f"Bearer {token}"},
    )
    if not response.is_success:
        raise CallbackHTTPError(response.status_code)
    return response.json()
