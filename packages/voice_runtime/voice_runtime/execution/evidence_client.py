"""Off-audio-path HTTP adapter for DurableSpool; acknowledgement follows API commit."""

import httpx
from pydantic import ValidationError

from voice_runtime.contracts.evidence import EvidenceBatch


class EvidenceDeliveryError(RuntimeError):
    """Sanitized failure; only transient, replay-safe ingestion may retry."""

    def __init__(
        self,
        *,
        retryable: bool,
        failure_kind: str | None = None,
        event_index: int | None = None,
        event_kind: str | None = None,
        validation_location: str | None = None,
    ):
        super().__init__("Evidence delivery failed; spool remains unacknowledged")
        self.retryable = retryable
        self.failure_kind = failure_kind
        self.event_index = event_index
        self.event_kind = event_kind
        self.validation_location = validation_location


class ApiEvidenceIngestor:
    def __init__(self, client: httpx.AsyncClient, run_id: str, runtime_service_token: str):
        self._client = client
        self._run_id = run_id
        self._token = runtime_service_token

    async def ingest(self, records: list[dict]) -> None:
        try:
            batch = EvidenceBatch(records=records)
        except ValidationError as exc:
            # Pydantic errors can contain transcript input; retain safe coordinates only.
            first = exc.errors(include_input=False)[0]
            event_index = _record_index(first["loc"])
            event_kind = _record_kind(records, event_index)
            location = ".".join(str(part) for part in first["loc"])
            raise EvidenceDeliveryError(
                retryable=False,
                failure_kind="invalid_record",
                event_index=event_index,
                event_kind=event_kind,
                validation_location=location,
            ) from None
        if any(record.run_id != self._run_id for record in batch.records):
            raise ValueError("Spool contains a different run")
        try:
            response = await self._client.post(
                f"/api/runs/{self._run_id}/evidence",
                headers={"X-Voice-Runtime-Token": self._token},
                json=batch.model_dump(mode="json"),
                follow_redirects=False,
                timeout=30,
            )
            response.raise_for_status()
            if response.json().get("accepted") != len(records):
                raise ValueError("Incomplete acknowledgement")
        except httpx.HTTPStatusError as exc:
            raise EvidenceDeliveryError(
                retryable=exc.response.status_code == 429 or exc.response.status_code >= 500
            ) from None
        except httpx.TransportError:
            raise EvidenceDeliveryError(retryable=True) from None
        except (httpx.HTTPError, ValueError):
            raise EvidenceDeliveryError(retryable=False) from None


def _record_index(location: tuple) -> int | None:
    return location[1] if len(location) > 1 and isinstance(location[1], int) else None


def _record_kind(records: list[dict], index: int | None) -> str | None:
    if index is None or index >= len(records):
        return None
    kind = records[index].get("kind")
    return kind if isinstance(kind, str) else None
