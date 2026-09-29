"""Browser supervisor outcomes use the same facts as the native pipeline."""

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import httpx
import pytest
from sqlalchemy.ext.asyncio import AsyncSession
from voice_api.models import BrowserSession, Run
from voice_api.services import browser_session_service as service
from voice_runtime.execution.delivery import EvidenceFinalization
from voice_runtime.execution.native import NativePipelineHost


@pytest.fixture
def browser_runtime(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    ctx = service.BrowserSessionContext("session", "run", {})
    ctx.request_handler = AsyncMock()
    run = Run(id="run", status="running", resolved_config={}, final_state={"prior": "kept"})
    browser = BrowserSession(id="session", run_id="run", status="connected")
    db = AsyncMock(spec=AsyncSession)

    async def get(model, _id, **_kwargs):
        return {Run: run, BrowserSession: browser}.get(model)

    db.get.side_effect = get
    factory = MagicMock()
    factory.return_value.__aenter__ = AsyncMock(return_value=db)
    factory.return_value.__aexit__ = AsyncMock(return_value=False)
    monkeypatch.setattr(service, "SessionFactory", factory)
    monkeypatch.setattr(service, "persist_diagnostic", AsyncMock())
    monkeypatch.setattr(service, "DurableSpool", MagicMock())
    monkeypatch.setattr(service, "ExchangeTracker", MagicMock())
    monkeypatch.setattr(service, "ApiEvidenceIngestor", MagicMock())
    manager = service.BrowserSessionManager()
    manager._sessions[ctx.session_id] = ctx
    monkeypatch.setattr(service, "browser_session_manager", manager)
    host = SimpleNamespace(
        directory=tmp_path / "absent-artifacts",
        prepare=AsyncMock(),
        converse=AsyncMock(),
        close=AsyncMock(),
        termination=ctx.termination,
    )
    host_factory = MagicMock(return_value=host)
    monkeypatch.setattr(service, "NativePipelineHost", host_factory)

    async def stream(*_args):
        await asyncio.Event().wait()

    async def finalize(_spool, _ingestor, delivery):
        delivery.cancel()
        await asyncio.gather(delivery, return_exceptions=True)
        return EvidenceFinalization(incomplete=False, diagnostic=None)

    monkeypatch.setattr(service, "stream_evidence", stream)
    monkeypatch.setattr(service, "finalize_evidence", finalize)
    settings = SimpleNamespace(
        recordings_dir=str(tmp_path),
        operator_token="test-token",
        groq_api_key="",
        jev_api_key="",
        sarvam_api_key="",
        cartesia_api_key="",
        gemini_api_key="",
    )

    async def execute():
        ctx.pipeline_task = asyncio.create_task(service._run_browser_pipeline(ctx, None, settings))
        await ctx.pipeline_task

    return SimpleNamespace(
        ctx=ctx,
        run=run,
        browser=browser,
        host=host,
        host_factory=host_factory,
        manager=manager,
        execute=execute,
        db=db,
        settings=settings,
    )


def test_native_host_can_share_browser_termination(tmp_path):
    ctx = service.BrowserSessionContext("session", "run", {})
    host = NativePipelineHost("run", tmp_path, None, termination=ctx.termination)
    assert host.termination is ctx.termination
    ctx.request_end("caller_hangup")
    assert host.termination.summary.cause == "caller_hangup"


@pytest.mark.parametrize(
    ("cause", "expected"),
    [
        ("terminal_completed", "completed"),
        ("agent_hangup", "completed"),
        ("disconnect_unknown", "failed"),
        ("unknown", "failed"),
    ],
)
async def test_browser_pipeline_uses_native_termination(browser_runtime, cause, expected):
    runtime = browser_runtime

    async def converse(_check):
        if cause != "unknown":
            runtime.ctx.termination.request(
                cause, graceful=cause in {"terminal_completed", "agent_hangup"}
            )
        runtime.ctx.termination.pipeline_finished()
        return {"flow_node": "finish", "termination": runtime.ctx.termination.snapshot()}

    runtime.host.converse.side_effect = converse
    await runtime.execute()

    assert runtime.run.status == expected
    assert runtime.run.final_state["termination"]["cause"] == cause
    assert runtime.run.final_state["termination"]["cleanup_status"] == "confirmed"
    assert runtime.run.final_state["termination"]["playback_status"] == "unknown"
    assert runtime.run.final_state["prior"] == "kept"
    assert runtime.run.final_state["flow_node"] == "finish"
    assert not runtime.run.final_state["evidence_incomplete"]
    assert runtime.manager.get_context("session") is None
    assert runtime.host_factory.call_args.kwargs["termination"] is runtime.ctx.termination


async def test_pipeline_error_overrides_agent_intent(browser_runtime):
    runtime = browser_runtime

    async def converse(_check):
        runtime.ctx.termination.request("agent_hangup", graceful=True)
        raise RuntimeError("provider stopped")

    runtime.host.converse.side_effect = converse
    await runtime.execute()
    assert runtime.run.status == "failed"
    assert runtime.run.final_state["termination"]["cause"] == "pipeline_failure"
    assert runtime.run.final_state["termination"]["requested_cause"] == "agent_hangup"
    assert runtime.browser.status == "failed"


@pytest.mark.parametrize(
    ("reason", "cause"),
    [("operator_stop", "caller_hangup"), ("browser_disconnect", "disconnect_unknown")],
)
async def test_external_stop_joins_pipeline_and_preserves_cause(browser_runtime, reason, cause):
    runtime = browser_runtime
    started = asyncio.Event()
    stopped = asyncio.Event()

    async def converse(_check):
        started.set()
        try:
            await asyncio.Event().wait()
        finally:
            stopped.set()

    runtime.host.converse.side_effect = converse
    runtime.ctx.pipeline_task = asyncio.create_task(
        service._run_browser_pipeline(runtime.ctx, None, runtime.settings)
    )
    await asyncio.wait_for(started.wait(), 2)
    await asyncio.wait_for(service.end_browser_session("session", runtime.db, reason=reason), 2)

    assert stopped.is_set()
    assert runtime.ctx.pipeline_task.done()
    assert runtime.run.status == "failed"
    assert runtime.run.final_state["termination"]["cause"] == cause
    assert runtime.run.final_state["termination"]["cleanup_status"] == "confirmed"
    runtime.host.close.assert_awaited_once()
    runtime.ctx.request_handler.close.assert_awaited_once()


async def test_cleanup_failure_is_separate_from_completed_call(browser_runtime):
    runtime = browser_runtime

    async def converse(_check):
        runtime.ctx.termination.request("terminal_completed", graceful=True)
        runtime.ctx.termination.pipeline_finished()
        return {"termination": runtime.ctx.termination.snapshot()}

    runtime.host.converse.side_effect = converse
    runtime.host.close.side_effect = RuntimeError("cleanup failed")
    await runtime.execute()
    assert runtime.run.status == "completed"
    assert runtime.run.final_state["termination"]["cleanup_status"] == "uncertain"
    assert runtime.run.final_state["evidence_incomplete"]
    runtime.ctx.request_handler.close.assert_awaited_once()
    assert runtime.manager.get_context("session") is runtime.ctx


async def test_repeated_stop_cannot_rewrite_completed_call(browser_runtime):
    runtime = browser_runtime
    runtime.run.status = "completed"
    runtime.run.final_state = {"termination": {"cause": "terminal_completed"}}
    runtime.ctx.termination.request("terminal_completed", graceful=True)
    runtime.ctx.termination.pipeline_finished()

    await service.end_browser_session("session", runtime.db)
    await service.end_browser_session("session", runtime.db)
    assert runtime.run.status == "completed"
    assert runtime.run.final_state["termination"]["cause"] == "terminal_completed"


async def test_stop_without_live_context_does_not_invent_completion(browser_runtime):
    runtime = browser_runtime
    await runtime.manager.remove_context("session")
    await service.end_browser_session("session", runtime.db)
    assert runtime.run.status == "failed"
    assert runtime.run.final_state["termination"]["cause"] == "caller_hangup"
    assert runtime.run.final_state["termination"]["cleanup_status"] == "unknown"
    assert runtime.run.final_state["evidence_incomplete"]


async def test_stop_before_pipeline_start_does_not_initialize_providers(browser_runtime):
    runtime = browser_runtime
    runtime.ctx.request_end("caller_hangup")
    await runtime.execute()
    runtime.host.prepare.assert_not_awaited()
    runtime.host.converse.assert_not_awaited()
    assert runtime.run.status == "failed"
    assert runtime.run.final_state["termination"]["cause"] == "caller_hangup"


@pytest.mark.parametrize("call_failed", [False, True])
@pytest.mark.parametrize("registration", [201, 302, 500, "timeout"])
async def test_artifact_registration_reports_failure_without_changing_call_outcome(
    browser_runtime, monkeypatch, call_failed, registration
):
    runtime = browser_runtime
    runtime.host.directory.mkdir()
    (runtime.host.directory / "input.wav").write_bytes(b"test input")
    (runtime.host.directory / "output.wav").write_bytes(b"test output")
    request = httpx.Request("POST", "http://runtime.local/api/runs/run/artifacts")
    first = (
        httpx.ReadTimeout("unsafe-secret-value")
        if registration == "timeout"
        else httpx.Response(registration, text="unsafe-secret-value", request=request)
    )
    post = AsyncMock(side_effect=[first, httpx.Response(201, request=request)])
    monkeypatch.setattr(httpx.AsyncClient, "post", post)

    async def converse(_check):
        if call_failed:
            raise RuntimeError("original pipeline failure")
        runtime.ctx.termination.request("terminal_completed", graceful=True)
        runtime.ctx.termination.pipeline_finished()
        return {"termination": runtime.ctx.termination.snapshot()}

    runtime.host.converse.side_effect = converse
    await runtime.execute()

    assert runtime.run.status == ("failed" if call_failed else "completed")
    if call_failed:
        assert "original pipeline failure" in runtime.run.error
    failed_registration = registration != 201
    assert runtime.run.final_state["artifacts_incomplete"] is failed_registration
    assert runtime.run.final_state["evidence_incomplete"] is failed_registration
    assert post.await_count == 2  # Independent files continue; failed writes are not retried.
    assert [call.kwargs["json"]["kind"] for call in post.await_args_list] == ["input", "output"]
    diagnostics = [
        call.args[2]
        for call in service.persist_diagnostic.await_args_list
        if call.args[2].code == "artifact_registration_failed"
    ]
    assert len(diagnostics) == int(failed_registration)
    if diagnostics:
        assert diagnostics[0].metadata == {"kind": "input"}
        assert "unsafe-secret-value" not in diagnostics[0].model_dump_json()
