"""Runtime delivery with fake control plane: no hardware, database or provider calls."""

import asyncio
import json
import threading

import httpx
import pytest
from voice_runtime.execution.delivery import (
    finalize_evidence,
    stream_evidence,
    supervise_execution,
)
from voice_runtime.execution.evidence_client import ApiEvidenceIngestor, EvidenceDeliveryError
from voice_runtime.execution.runner import execute_call
from voice_runtime.execution.spool import DurableSpool


def valid_record(record_id="stable"):
    return {
        "id": record_id,
        "run_id": "run",
        "kind": "exchange",
        "exchange_id": "exchange",
        "timestamp_ns": 1,
        "origin": "greeting",
        "sequence": 1,
    }


class FakeControl:
    def __init__(self):
        self.received = asyncio.Event()
        self.records = []
        self.batches = 0
        self.progress = []
        self.evidence_status = 200

    def request(self, request):
        body = json.loads(request.content)
        if request.url.path.endswith("/claim"):
            return httpx.Response(
                200,
                json={
                    "status": "claimed",
                    "destination": "+15551234567",
                    "resolved_config": {"call_limits": {"max_duration_secs": 10}},
                },
            )
        if request.url.path.endswith("/progress"):
            self.progress.append(body)
            return httpx.Response(200, json={})
        if request.url.path.endswith("/evidence"):
            self.batches += 1
            self.records.extend(body["records"])
            self.received.set()
            return httpx.Response(self.evidence_status, json={"accepted": len(body["records"])})
        raise AssertionError(request.url)


class WaitingDriver:
    def __init__(self, control):
        self.control = control
        self.closed = False
        self.started = asyncio.Event()

    async def prepare(self, snapshot, tracker):
        tracker.assistant_message("Hello", "2026-09-23T00:00:00Z")

    async def call(self, destination):
        self.started.set()
        async with asyncio.timeout(3):
            await self.control.received.wait()
        assert not self.closed
        return {"heard": True}

    async def close(self):
        self.closed = True


async def run(control, driver, path):
    async with httpx.AsyncClient(
        transport=httpx.MockTransport(control.request), base_url="http://test"
    ) as client:
        return await execute_call(client, "test-token", "run", "endpoint", driver, path)


async def test_evidence_reaches_api_before_hangup(tmp_path):
    control = FakeControl()
    driver = WaitingDriver(control)
    assert await run(control, driver, tmp_path / "call.jsonl") == "completed"
    assert driver.closed
    assert {record["kind"] for record in control.records} == {"exchange", "message"}
    assert len(control.records) == 2
    assert control.progress[-1]["final_state"]["evidence_incomplete"] is False


async def test_local_runner_delivers_without_http_or_service_token(tmp_path):
    control = FakeControl()
    driver = WaitingDriver(control)

    async def post(suffix, body):
        if suffix == "claim":
            return {
                "status": "claimed",
                "destination": "+15551234567",
                "resolved_config": {"call_limits": {"max_duration_secs": 10}},
            }
        assert suffix == "progress"
        control.progress.append(body)
        return {"status": body["status"]}

    class LocalIngestor:
        async def ingest(self, records):
            control.records.extend(records)
            control.received.set()

    outcome = await execute_call(
        None,
        "",
        "run",
        "endpoint",
        driver,
        tmp_path / "local-call.jsonl",
        local_post=post,
        local_ingestor=LocalIngestor(),
    )
    assert outcome == "completed"
    assert driver.closed
    assert {record["kind"] for record in control.records} == {"exchange", "message"}
    assert control.progress[-1]["final_state"]["evidence_incomplete"] is False


async def test_spool_close_failure_reports_terminal_failure(tmp_path, monkeypatch):
    original = DurableSpool.close

    async def broken_close(self):
        await original(self)
        raise OSError("sensitive disk path")

    monkeypatch.setattr(DurableSpool, "close", broken_close)
    control = FakeControl()
    driver = WaitingDriver(control)
    assert await run(control, driver, tmp_path / "call.jsonl") == "completed"
    assert driver.closed
    terminal = control.progress[-1]
    assert terminal["transport_released"]
    assert terminal["final_state"]["evidence_incomplete"]
    assert "sensitive" not in json.dumps(terminal)


async def test_spool_creation_failure_still_closes_driver(tmp_path, monkeypatch):
    def broken_spool(path):
        raise OSError("sensitive disk path")

    monkeypatch.setattr("voice_runtime.execution.runner.DurableSpool", broken_spool)
    control = FakeControl()
    driver = WaitingDriver(control)
    assert await run(control, driver, tmp_path / "call.jsonl") == "failed"
    assert driver.closed and not driver.started.is_set()
    assert control.progress[-1]["final_state"]["evidence_incomplete"]


async def test_cancellation_closes_transport_and_reports_failed(tmp_path):
    control = FakeControl()

    class LongCall(WaitingDriver):
        async def call(self, destination):
            self.started.set()
            await asyncio.Event().wait()

    driver = LongCall(control)
    task = asyncio.create_task(run(control, driver, tmp_path / "call.jsonl"))
    await driver.started.wait()
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert driver.closed
    assert control.progress[-1]["status"] == "failed"
    assert control.progress[-1]["error"] == "Call execution cancelled"


@pytest.mark.parametrize("status,retryable", [(429, True), (503, True), (401, False), (422, False)])
async def test_http_failures_have_explicit_retry_policy(status, retryable):
    control = FakeControl()
    control.evidence_status = status
    async with httpx.AsyncClient(
        transport=httpx.MockTransport(control.request), base_url="http://test"
    ) as client:
        with pytest.raises(EvidenceDeliveryError) as caught:
            await ApiEvidenceIngestor(client, "run", "secret").ingest(
                [
                    {
                        "id": "record",
                        "run_id": "run",
                        "kind": "exchange",
                        "exchange_id": "exchange",
                        "timestamp_ns": 1,
                        "origin": "greeting",
                        "sequence": 1,
                    }
                ]
            )
    assert caught.value.retryable is retryable
    assert "secret" not in str(caught.value)


async def test_invalid_legacy_event_fails_locally_with_safe_coordinates():
    requests = []

    def receive(request):
        requests.append(request)
        return httpx.Response(200, json={"accepted": 1})

    invalid = {**valid_record(), "occurred_at": "2026-09-27T13:00:00Z"}
    async with httpx.AsyncClient(
        transport=httpx.MockTransport(receive), base_url="http://test"
    ) as client:
        with pytest.raises(EvidenceDeliveryError) as caught:
            await ApiEvidenceIngestor(client, "run", "secret").ingest([invalid])

    assert not requests
    assert caught.value.failure_kind == "invalid_record"
    assert caught.value.event_index == 0
    assert caught.value.event_kind == "exchange"
    assert caught.value.validation_location == "records.0.exchange.occurred_at"
    assert "secret" not in str(caught.value)


async def test_transient_failure_replays_same_batch(tmp_path):
    spool = DurableSpool(tmp_path / "call.jsonl")
    spool.submit(valid_record())
    await spool.flush()
    seen = []
    delivered = asyncio.Event()

    class Ingestor:
        async def ingest(self, records):
            seen.append(records)
            if len(seen) == 1:
                raise EvidenceDeliveryError(retryable=True)
            delivered.set()

    task = asyncio.create_task(
        stream_evidence(spool, Ingestor(), poll_seconds=0.01, retry_seconds=0.01)
    )
    try:
        async with asyncio.timeout(3):
            await delivered.wait()
        task.cancel()
        await asyncio.gather(task, return_exceptions=True)
        # Cancellation may precede acknowledgement. Replaying remains safe.
        assert seen[:2] == [[valid_record()], [valid_record()]]
    finally:
        task.cancel()
        await asyncio.gather(task, return_exceptions=True)
        await spool.close()


async def test_final_drain_reports_permanent_failure_without_acknowledging(tmp_path):
    spool = DurableSpool(tmp_path / "call.jsonl")
    spool.submit(valid_record())
    await spool.flush()

    class Ingestor:
        async def ingest(self, records):
            failed.set()
            raise EvidenceDeliveryError(
                retryable=False,
                failure_kind="invalid_record",
                event_index=0,
                event_kind="diagnostic",
                validation_location="records.0.occurred_at",
            )

    failed = asyncio.Event()
    delivery_task = asyncio.create_task(stream_evidence(spool, Ingestor(), poll_seconds=0.01))
    async with asyncio.timeout(3):
        await failed.wait()
        await asyncio.gather(delivery_task, return_exceptions=True)
    finalized = await finalize_evidence(spool, Ingestor(), delivery_task)

    assert finalized.incomplete
    assert finalized.diagnostic["metadata"] == {
        "failure_kind": "invalid_record",
        "event_index": 0,
        "event_kind": "diagnostic",
        "validation_location": "records.0.occurred_at",
    }
    assert not (tmp_path / "call.ack").exists()


async def test_invalid_producer_record_is_not_appended_and_marks_evidence_incomplete(tmp_path):
    spool = DurableSpool(tmp_path / "call.jsonl")
    spool.submit(valid_record())
    await spool.flush()
    size_before = spool.path.stat().st_size
    invalid = {**valid_record("bad-record"), "occurred_at": "wrong-envelope"}

    with pytest.raises(ValueError):
        spool.submit(invalid)

    assert spool.path.stat().st_size == size_before
    assert spool.error is not None

    class Ingestor:
        async def ingest(self, records):
            pytest.fail("A latched producer validation failure must not upload")

    finalized = await finalize_evidence(spool, Ingestor(), None)

    assert finalized.incomplete
    assert finalized.diagnostic["metadata"] == {
        "failure_kind": "invalid_record",
        "event_kind": "exchange",
        "validation_location": "exchange.occurred_at",
    }
    assert not (tmp_path / "call.ack").exists()


async def test_delivery_failure_cancels_active_execution():
    stopped = asyncio.Event()

    async def live_execution():
        try:
            await asyncio.Event().wait()
        finally:
            stopped.set()

    async def failed_delivery():
        raise EvidenceDeliveryError(retryable=False, failure_kind="invalid_record")

    delivery = asyncio.create_task(failed_delivery())
    with pytest.raises(EvidenceDeliveryError):
        await asyncio.wait_for(supervise_execution(live_execution(), delivery), timeout=3)
    assert stopped.is_set()


async def test_disk_failure_detected_while_http_is_blocked(tmp_path):
    spool = DurableSpool(tmp_path / "call.jsonl")
    spool.submit(valid_record())
    await spool.flush()
    started = asyncio.Event()
    cancelled = asyncio.Event()

    class Ingestor:
        async def ingest(self, records):
            started.set()
            try:
                await asyncio.Event().wait()
            finally:
                cancelled.set()

    task = asyncio.create_task(stream_evidence(spool, Ingestor(), poll_seconds=0.01))
    try:
        async with asyncio.timeout(3):
            await started.wait()
            spool.error = OSError("disk failed")
            with pytest.raises(ExceptionGroup):
                await task
        assert cancelled.is_set()
        assert not spool.cursor_path.exists()
    finally:
        task.cancel()
        await asyncio.gather(task, return_exceptions=True)
        # Synthetic failure did not terminate writer; clear it for actual shutdown.
        spool.error = None
        await spool.close()


async def test_permanent_rejection_stops_call_without_retry(tmp_path):
    control = FakeControl()
    control.evidence_status = 422

    class LongCall(WaitingDriver):
        async def call(self, destination):
            self.started.set()
            await asyncio.Event().wait()

    driver = LongCall(control)
    async with asyncio.timeout(3):
        assert await run(control, driver, tmp_path / "call.jsonl") == "failed"
    assert driver.closed
    assert control.batches == 1  # One rejected batch, no cleanup retry.
    assert not (tmp_path / "call.ack").exists()
    assert control.progress[-1]["final_state"]["evidence_incomplete"]


async def test_cancellation_waits_for_cursor_thread(tmp_path, monkeypatch):
    spool = DurableSpool(tmp_path / "call.jsonl")
    spool.submit(valid_record())
    await spool.flush()
    started = threading.Event()
    release = threading.Event()
    original = spool._ack

    def delayed_ack(offset):
        started.set()
        if not release.wait(3):
            raise TimeoutError("test acknowledgement not released")
        original(offset)

    monkeypatch.setattr(spool, "_ack", delayed_ack)

    class Ingestor:
        async def ingest(self, records):
            pass

    task = asyncio.create_task(spool.deliver_once(Ingestor()))
    try:
        assert await asyncio.to_thread(started.wait, 3)
        task.cancel()
        await asyncio.sleep(0)
        assert not task.done()
        release.set()
        with pytest.raises(asyncio.CancelledError):
            await task
        assert await spool.deliver_once(Ingestor()) == 0
    finally:
        release.set()
        await asyncio.gather(task, return_exceptions=True)
        await spool.close()
