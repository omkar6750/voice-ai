"""Off-audio-path HTTP adapter for DurableSpool; acknowledgement follows API commit."""

import httpx

from voice_runtime.contracts.evidence import EvidenceBatch


class EvidenceDeliveryError(RuntimeError):
    """Sanitized failure; only transient, replay-safe ingestion may retry."""

    def __init__(self, *, retryable: bool):
        super().__init__("Evidence delivery failed; spool remains unacknowledged")
        self.retryable = retryable


class ApiEvidenceIngestor:
    def __init__(self, client: httpx.AsyncClient, run_id: str, operator_token: str):
        self._client = client
        self._run_id = run_id
        self._token = operator_token

    async def ingest(self, records: list[dict]) -> None:
        batch = EvidenceBatch(records=records)
        if any(record.run_id != self._run_id for record in batch.records):
            raise ValueError("Spool contains a different run")
        try:
            response = await self._client.post(
                f"/api/runs/{self._run_id}/evidence",
                headers={"Authorization": f"Bearer {self._token}"},
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
