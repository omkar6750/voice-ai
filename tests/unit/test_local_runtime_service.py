"""Same-process runtime operations do not depend on HTTP or worker credentials."""

from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastapi import HTTPException
from voice_api.api.v1.endpoints import artifacts, calendar, evidence, execution
from voice_api.services import calendar_service
from voice_api.services import local_runtime_service as local
from voice_runtime.execution.evidence_client import EvidenceDeliveryError


@pytest.fixture(autouse=True)
def scoped_run(monkeypatch):
    bind = AsyncMock(return_value="org-test")
    monkeypatch.setattr(local, "bind_run_organization", bind)
    return bind


@asynccontextmanager
async def fake_session():
    yield object()


def exchange_record():
    return {
        "kind": "exchange",
        "id": "record-1",
        "run_id": "run-1",
        "timestamp_ns": 1,
        "exchange_id": "exchange-1",
        "sequence": 1,
        "origin": "caller",
    }


@pytest.mark.asyncio
async def test_local_evidence_acknowledges_after_ingest(monkeypatch, scoped_run):
    ingest = AsyncMock(return_value={"accepted": 1})
    monkeypatch.setattr(local, "SessionFactory", fake_session)
    monkeypatch.setattr(evidence, "ingest", ingest)

    await local.LocalEvidenceIngestor("run-1").ingest([exchange_record()])

    assert ingest.await_args.args[0] == "run-1"
    assert len(ingest.await_args.args[1].records) == 1
    scoped_run.assert_awaited_once()


@pytest.mark.asyncio
async def test_local_evidence_classifies_retryable_error(monkeypatch):
    monkeypatch.setattr(local, "SessionFactory", fake_session)
    monkeypatch.setattr(evidence, "ingest", AsyncMock(side_effect=HTTPException(503)))

    with pytest.raises(EvidenceDeliveryError) as exc:
        await local.LocalEvidenceIngestor("run-1").ingest([exchange_record()])
    assert exc.value.retryable


@pytest.mark.asyncio
async def test_local_control_preserves_claim_and_progress_validation(monkeypatch):
    claim = AsyncMock(return_value={"status": "claimed"})
    progress = AsyncMock(return_value={"status": "running"})
    monkeypatch.setattr(local, "SessionFactory", fake_session)
    monkeypatch.setattr(execution, "claim", claim)
    monkeypatch.setattr(execution, "progress", progress)

    assert (
        await local.local_claim(
            "run-1", {"token": "token-1", "endpoint_id": "endpoint-1", "lease_seconds": 60}
        )
    )["status"] == "claimed"
    assert (await local.local_progress("run-1", {"token": "token-1", "status": "running"}))[
        "status"
    ] == "running"
    assert claim.await_args.args[0] == progress.await_args.args[0] == "run-1"


@pytest.mark.asyncio
async def test_local_artifact_registration_uses_existing_validation(tmp_path, monkeypatch):
    directory = tmp_path / "run-1"
    directory.mkdir()
    (directory / "pipeline.log").write_text("pipeline")
    register = AsyncMock(return_value={"id": "artifact-1"})
    monkeypatch.setattr(local, "SessionFactory", fake_session)
    monkeypatch.setattr(artifacts, "register", register)

    await local.register_local_artifacts("run-1", directory, strict=True)

    body = register.await_args.args[1]
    assert body.kind == "pipeline_log"
    assert body.path == "run-1/pipeline.log"


@pytest.mark.asyncio
async def test_local_artifacts_continue_after_one_registration_fails(tmp_path, monkeypatch):
    directory = tmp_path / "run-1"
    directory.mkdir()
    (directory / "input.wav").write_bytes(b"input")
    (directory / "output.wav").write_bytes(b"output")
    register = AsyncMock(side_effect=[HTTPException(503), {"id": "output-artifact"}])
    monkeypatch.setattr(local, "SessionFactory", fake_session)
    monkeypatch.setattr(artifacts, "register", register)

    failed = await local.register_local_artifacts("run-1", directory)

    assert failed == ["input"]
    assert [call.args[1].kind for call in register.await_args_list] == ["input", "output"]


@pytest.mark.asyncio
async def test_local_callback_invokes_calendar_without_service_token(monkeypatch):
    available = AsyncMock(return_value={"status": "no_availability"})
    monkeypatch.setattr(local, "SessionFactory", fake_session)
    monkeypatch.setattr(calendar, "availability", available)

    result = await local.local_callback(
        "check_callback_availability",
        "run-1",
        {"agent_version_id": "version-1", "timeframe": "tomorrow", "role": "sales"},
    )

    assert result == {"status": "no_availability"}
    assert available.await_args.args[2] is None


def test_callback_slot_uses_dedicated_key_not_runtime_token(monkeypatch):
    payload = {"expires_at": (datetime.now(UTC) + timedelta(minutes=1)).isoformat()}
    monkeypatch.setattr(
        calendar_service,
        "get_settings",
        lambda: SimpleNamespace(callback_slot_signing_key="dedicated-test-key"),
    )
    signed = calendar_service.sign_slot(payload)
    assert calendar_service.verify_slot(signed) == payload

    monkeypatch.setattr(
        calendar_service,
        "get_settings",
        lambda: SimpleNamespace(callback_slot_signing_key=None, runtime_service_token="worker-key"),
    )
    with pytest.raises(calendar_service.SchedulingError):
        calendar_service.sign_slot(payload)
