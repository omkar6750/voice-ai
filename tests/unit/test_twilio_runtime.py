from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import httpx
import pytest
from sqlalchemy.ext.asyncio import AsyncSession
from voice_api.models import Call, Run
from voice_api.services import twilio_runtime_service as service
from voice_runtime.execution.delivery import EvidenceFinalization
from voice_runtime.execution.termination import CallTermination
from voice_runtime.telephony.twilio_session import TwilioMediaSession


class FakeResponse:
    def __init__(self, status_code: int) -> None:
        self.status_code = status_code

    def raise_for_status(self) -> None:
        if not 200 <= self.status_code < 300:
            request = httpx.Request("POST", "http://runtime.local/artifact")
            response = httpx.Response(self.status_code, request=request)
            raise httpx.HTTPStatusError(
                "secret response detail", request=request, response=response
            )


@pytest.fixture
def runtime(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    call = Call(
        id="call-id",
        run_id="run-id",
        contact_id="contact-id",
        agent_version_id="agent-id",
        provider="twilio",
        status="active",
        provider_metadata={"history": ["kept"]},
    )
    run = Run(
        id="run-id",
        status="running",
        error=None,
        final_state={"history": ["kept"], "evidence_incomplete": False},
    )
    db = AsyncMock(spec=AsyncSession)
    lock_order: list[type] = []

    async def get(model, _identity, **_kwargs):
        lock_order.append(model)
        return {Call: call, Run: run}.get(model)

    db.get.side_effect = get

    @asynccontextmanager
    async def session_factory():
        yield db

    monkeypatch.setattr(service, "SessionFactory", session_factory)
    monkeypatch.setattr(service, "bind_run_organization", AsyncMock(return_value="org-test"))
    from voice_api.services import provider_credentials

    monkeypatch.setattr(provider_credentials, "settings_for_snapshot", AsyncMock(side_effect=lambda _session, _org, _snapshot, base, **_kwargs: base))
    persist = AsyncMock()
    monkeypatch.setattr(service, "persist_diagnostic", persist)
    spool = MagicMock()
    monkeypatch.setattr(service, "DurableSpool", MagicMock(return_value=spool))
    monkeypatch.setattr(service, "ExchangeTracker", MagicMock())
    monkeypatch.setattr(service, "ApiEvidenceIngestor", MagicMock())

    async def stream(_spool, _ingestor):
        await asyncio.Event().wait()

    async def finalize(_spool, _ingestor, delivery_task):
        delivery_task.cancel()
        await asyncio.gather(delivery_task, return_exceptions=True)
        return EvidenceFinalization(incomplete=False, diagnostic=None)

    monkeypatch.setattr(service, "stream_evidence", stream)
    monkeypatch.setattr(service, "finalize_evidence", finalize)

    host = SimpleNamespace(
        directory=tmp_path / "recordings" / "run-id",
        prepare=AsyncMock(),
        converse=AsyncMock(),
        close=AsyncMock(),
    )
    monkeypatch.setattr(service, "NativePipelineHost", MagicMock(return_value=host))

    http_client = SimpleNamespace(post=AsyncMock(return_value=FakeResponse(201)))

    class FakeAsyncClient:
        def __init__(self, **_kwargs):
            self.post = http_client.post

        async def __aenter__(self):
            return self

        async def __aexit__(self, *_args):
            return False

    monkeypatch.setattr(service.httpx, "AsyncClient", FakeAsyncClient)

    rest = SimpleNamespace(
        complete=AsyncMock(return_value="completed"),
        status=AsyncMock(return_value="completed"),
        aclose=AsyncMock(),
    )
    termination = CallTermination()
    media = TwilioMediaSession("stream-id", termination, AsyncMock(), rest)
    settings = SimpleNamespace(
        recordings_dir=str(tmp_path / "recordings"),
        runtime_service_token="runtime-secret",
        groq_api_key="provider-secret",
        jev_api_key="",
        sarvam_api_key="",
        cartesia_api_key="",
        gemini_api_key="",
    )

    async def execute():
        await service.run_twilio_pipeline(
            call_id=call.id,
            run_id=run.id,
            snapshot={"_resolved": {}},
            transport=None,
            media=media,
            settings=settings,
            auth_token="twilio-secret",
        )

    return SimpleNamespace(
        call=call,
        run=run,
        db=db,
        lock_order=lock_order,
        persist=persist,
        host=host,
        media=media,
        rest=rest,
        settings=settings,
        http_client=http_client,
        execute=execute,
    )


@pytest.mark.parametrize(
    ("cause", "expected"),
    [
        ("terminal_completed", "completed"),
        ("agent_hangup", "completed"),
        ("unknown", "failed"),
        ("disconnect_unknown", "failed"),
    ],
)
async def test_pipeline_maps_execution_termination(runtime, cause, expected):
    async def converse(_media):
        if cause != "unknown":
            runtime.media.termination.request(
                cause, graceful=cause in {"terminal_completed", "agent_hangup"}
            )
        runtime.media.termination.pipeline_finished()
        return {"flow_node": "end"}

    runtime.host.converse.side_effect = converse
    if cause == "disconnect_unknown":
        runtime.media.disconnected()
    await runtime.execute()

    assert runtime.run.status == expected
    assert runtime.run.final_state["termination"]["cause"] == cause
    assert runtime.run.final_state["history"] == ["kept"]
    assert (
        runtime.run.final_state["flow_node"] == "end"
        if cause != "disconnect_unknown"
        else "flow_node" not in runtime.run.final_state
    )
    runtime.rest.complete.assert_awaited_once()
    runtime.host.close.assert_awaited_once()


@pytest.mark.parametrize("failure_point", ["prepare", "converse"])
async def test_pipeline_errors_are_generic_and_secrets_are_not_persisted(runtime, failure_point):
    failure = RuntimeError("unsafe provider-secret twilio-secret operator-secret")
    getattr(runtime.host, failure_point).side_effect = failure

    await runtime.execute()

    assert runtime.run.status == "failed"
    assert runtime.run.error == "Twilio call ended before normal completion: pipeline_failure"
    assert runtime.run.final_state["termination"]["cause"] == "pipeline_failure"
    assert "unsafe provider-secret" not in repr(runtime.run.final_state)
    assert all(
        secret not in repr((args, kwargs))
        for secret in ("unsafe provider-secret", "twilio-secret", "operator-secret")
        for args, kwargs in runtime.persist.await_args_list
    )
    runtime.rest.complete.assert_awaited_once()


async def test_cancellation_still_releases_carrier_and_finalizes_as_failed(runtime):
    runtime.host.converse.side_effect = asyncio.CancelledError()

    with pytest.raises(asyncio.CancelledError):
        await runtime.execute()

    assert runtime.run.status == "failed"
    assert runtime.run.final_state["termination"]["cause"] == "cancelled"
    runtime.rest.complete.assert_awaited_once()
    runtime.rest.aclose.assert_awaited_once()


async def test_host_close_failure_does_not_skip_single_media_hangup(runtime):
    runtime.host.close.side_effect = RuntimeError("unsafe cleanup-secret")

    async def converse(_media):
        runtime.media.termination.request("agent_hangup", graceful=True)
        runtime.media.termination.pipeline_finished()
        return {}

    runtime.host.converse.side_effect = converse
    await runtime.execute()

    runtime.rest.complete.assert_awaited_once()
    assert runtime.run.status == "completed"
    assert runtime.run.final_state["evidence_incomplete"]


async def test_host_cleanup_uncertainty_does_not_erase_confirmed_carrier_release(runtime):
    async def converse(_media):
        runtime.media.termination.request("agent_hangup", graceful=True)
        runtime.media.termination.pipeline_finished()
        await runtime.media.close(graceful=True)
        return {}

    async def close_host():
        runtime.media.termination.summary.cleanup_status = "uncertain"
        raise RuntimeError("native host cleanup failed")

    runtime.host.converse.side_effect = converse
    runtime.host.close.side_effect = close_host
    await runtime.execute()

    assert runtime.rest.complete.await_count == 1
    assert runtime.rest.status.await_count == 1
    assert runtime.media.provider_status == "completed"
    assert runtime.media.termination.summary.cleanup_status == "confirmed"
    assert runtime.call.provider_metadata["release_status"] == "confirmed"
    assert runtime.run.status == "completed"
    assert runtime.run.final_state["evidence_incomplete"]


async def test_existing_run_error_and_history_are_preserved(runtime):
    runtime.run.error = "prior diagnostic"

    async def converse(_media):
        runtime.media.termination.request("agent_hangup", graceful=True)
        runtime.media.termination.pipeline_finished()
        return {"new": "state"}

    runtime.host.converse.side_effect = converse
    await runtime.execute()

    assert runtime.run.error == "prior diagnostic"
    assert runtime.run.final_state["history"] == ["kept"]
    assert runtime.run.final_state["new"] == "state"


async def test_completed_carrier_call_does_not_complete_failed_run(runtime):
    runtime.run.status = "failed"
    runtime.run.error = "business failure"
    runtime.rest.status.return_value = "completed"

    async def converse(_media):
        runtime.media.termination.request("pipeline_failure")
        raise RuntimeError("failure")

    runtime.host.converse.side_effect = converse
    await runtime.execute()

    assert runtime.call.status == "completed"
    assert runtime.run.status == "failed"
    assert runtime.run.error == "business failure"


@pytest.mark.parametrize(
    ("failure", "expected_code"),
    [
        (503, "artifact_registration_failed"),
        (302, "artifact_registration_failed"),
        ("timeout", "artifact_registration_failed"),
    ],
)
@pytest.mark.parametrize("pipeline_failed", [False, True])
async def test_artifact_registration_failure_is_independent_and_sanitized(
    runtime, failure, expected_code, pipeline_failed
):
    runtime.host.directory.mkdir(parents=True)
    (runtime.host.directory / "input.wav").write_bytes(b"fixture")
    if failure == "timeout":
        runtime.http_client.post.side_effect = httpx.ReadTimeout("unsafe artifact-secret")
    else:
        runtime.http_client.post.return_value = FakeResponse(failure)

    async def converse(_media):
        if pipeline_failed:
            raise RuntimeError("unsafe pipeline-secret")
        runtime.media.termination.request("terminal_completed", graceful=True)
        runtime.media.termination.pipeline_finished()
        return {}

    runtime.host.converse.side_effect = converse
    await runtime.execute()

    assert runtime.run.status == ("failed" if pipeline_failed else "completed")
    assert runtime.run.final_state["artifacts_incomplete"]
    assert runtime.run.final_state["evidence_incomplete"]
    diagnostics = [
        args[2]
        for args, _kwargs in runtime.persist.await_args_list
        if args[2].code == expected_code
    ]
    assert len(diagnostics) == 1
    serialized = diagnostics[0].model_dump_json()
    assert "unsafe" not in serialized
    assert "secret" not in serialized
    if pipeline_failed:
        assert runtime.run.error == "Twilio call ended before normal completion: pipeline_failure"
    else:
        assert runtime.run.status == "completed"


async def test_uncertain_rest_status_keeps_active_call_and_records_uncertain_release(runtime):
    runtime.rest.status.return_value = "in-progress"

    async def converse(_media):
        runtime.media.termination.request("agent_hangup", graceful=True)
        runtime.media.termination.pipeline_finished()
        return {}

    runtime.host.converse.side_effect = converse
    await runtime.execute()

    assert runtime.call.status == "active"
    assert runtime.call.provider_metadata["release_status"] == "uncertain"
    assert runtime.call.provider_metadata["rest_status"] == "in-progress"
    assert runtime.run.status == "completed"


async def test_finalizer_locks_call_before_run(runtime):
    async def converse(_media):
        runtime.media.termination.request("agent_hangup", graceful=True)
        runtime.media.termination.pipeline_finished()
        return {}

    runtime.host.converse.side_effect = converse
    await runtime.execute()

    assert runtime.lock_order[:2] == [Call, Run]


async def test_startup_failure_fallback_persists_generic_failure_and_release(runtime):
    await service.finalize_twilio_startup_failure(
        call_id=runtime.call.id,
        run_id=runtime.run.id,
        media=runtime.media,
    )

    assert runtime.run.status == "failed"
    assert runtime.run.error == "Twilio call ended before normal completion: pipeline_failure"
    assert runtime.run.final_state["history"] == ["kept"]
    assert runtime.run.final_state["termination"]["cause"] == "pipeline_failure"
    assert runtime.call.provider_metadata["release_status"] == "confirmed"
    runtime.rest.complete.assert_awaited_once()
    diagnostic = runtime.persist.await_args.args[2]
    assert diagnostic.code == "twilio_startup_failed"
    assert diagnostic.message == "Twilio runtime startup failed"
    assert diagnostic.detail is None
    assert diagnostic.metadata == {}


async def test_canceled_startup_fallback_persists_cancel_termination(runtime):
    await service.finalize_twilio_startup_failure(
        call_id=runtime.call.id,
        run_id=runtime.run.id,
        media=runtime.media,
        cancelled=True,
    )

    assert runtime.run.status == "failed"
    termination = runtime.run.final_state["termination"]
    assert termination["cause"] == "cancelled"
    assert termination["requested_cause"] == "cancelled"
    assert runtime.call.provider_metadata["release_status"] == "confirmed"
    diagnostic = runtime.persist.await_args.args[2]
    assert diagnostic.code == "twilio_startup_failed"
    runtime.rest.complete.assert_awaited_once()


async def test_startup_fallback_cannot_overwrite_completed_run_snapshot(runtime):
    termination_history = {
        "cause": "terminal_completed",
        "requested_cause": "terminal_completed",
        "pipeline_finished_at_ns": 123,
    }
    runtime.run.status = "completed"
    runtime.run.error = None
    runtime.run.final_state = {
        "history": ["successful result"],
        "termination": termination_history,
        "business_result": {"qualified": True},
        "evidence_incomplete": False,
    }

    await service.finalize_twilio_startup_failure(
        call_id=runtime.call.id,
        run_id=runtime.run.id,
        media=runtime.media,
    )

    assert runtime.run.status == "completed"
    assert runtime.run.error is None
    assert runtime.run.final_state["history"] == ["successful result"]
    assert runtime.run.final_state["termination"] == termination_history
    assert runtime.run.final_state["business_result"] == {"qualified": True}
    runtime.persist.assert_not_awaited()
    runtime.db.commit.assert_not_awaited()


async def test_endpoint_fallback_does_not_persist_supervisor_cancellation_twice(runtime):
    runtime.host.converse.side_effect = asyncio.CancelledError()
    with pytest.raises(asyncio.CancelledError):
        await runtime.execute()
    commits = runtime.db.commit.await_count
    diagnoses = runtime.persist.await_count
    snapshot = dict(runtime.run.final_state)
    await service.finalize_twilio_startup_failure(
        call_id=runtime.call.id,
        run_id=runtime.run.id,
        media=runtime.media,
        cancelled=True,
    )
    assert runtime.db.commit.await_count == commits
    assert runtime.persist.await_count == diagnoses
    assert runtime.run.final_state == snapshot
    runtime.rest.complete.assert_awaited_once()
