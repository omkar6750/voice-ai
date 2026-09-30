"""Twilio run ownership, teardown and evidence finalization.

Carrier release and business completion are distinct facts. Every accepted run
reaches the same session close owner, including provider startup/storage errors.
"""

from __future__ import annotations

import asyncio
from pathlib import Path
from uuid import NAMESPACE_URL, uuid5

import httpx
from loguru import logger
from voice_runtime.contracts.diagnostics import diagnostic_dict
from voice_runtime.execution.delivery import finalize_evidence, stream_evidence, supervise_execution
from voice_runtime.execution.evidence_client import ApiEvidenceIngestor
from voice_runtime.execution.exchange import ExchangeTracker
from voice_runtime.execution.spool import DurableSpool
from voice_runtime.telephony.twilio_session import TERMINAL_STATUSES, TwilioMediaSession

from voice_api.core.security import runtime_token_for_run
from voice_api.db.session import SessionFactory
from voice_api.db.tenant_scope import bind_run_organization
from voice_api.models import Call, Run
from voice_api.models.common import now
from voice_api.schemas.diagnostics import DiagnosticInput
from voice_api.services.call_service import TWILIO_STATUS_MAP
from voice_api.services.credential_runtime_host import CredentialRuntimeHost as NativePipelineHost
from voice_api.services.diagnostic_service import persist_diagnostic
from voice_api.services.provider_credentials import resolved_provider_secret_values


def _diagnostic(code: str, message: str, **metadata) -> dict:
    return diagnostic_dict(
        severity="error",
        category="runtime_failure",
        source="runtime",
        code=code,
        message=message,
        metadata=metadata,
    )


async def run_twilio_pipeline(
    *,
    call_id: str,
    run_id: str,
    snapshot: dict,
    transport,
    media: TwilioMediaSession,
    settings,
    auth_token: str,
) -> None:
    """Own the live run once claimed; do not retry external writes or redial."""
    termination = media.termination
    host = None
    spool = None
    delivery_task = None
    final_state: dict = {}
    diagnostics: list[dict] = []
    artifact_diagnostics: list[dict] = []
    cleanup_failed = False
    evidence_incomplete = False
    # In-process evidence avoids deployment-dependent callback host assumptions.
    from voice_api.main import app

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://runtime.local",
        timeout=20,
        follow_redirects=False,
    ) as client:
        runtime_token = runtime_token_for_run(settings.runtime_service_token or "", run_id)
        ingestor = ApiEvidenceIngestor(client, run_id, runtime_token)
        try:
            async with SessionFactory() as credential_session:
                organization_id = await bind_run_organization(credential_session, run_id)
                from voice_api.services.provider_credentials import settings_for_snapshot

                settings = await settings_for_snapshot(
                    credential_session, organization_id, snapshot, settings, run_id=run_id
                )
            host = NativePipelineHost(
                run_id=run_id,
                recordings_dir=Path(settings.recordings_dir),
                settings=settings,
                termination=termination,
            )
            spool_path = Path("data/evidence") / f"{run_id}.jsonl"
            spool_path.parent.mkdir(parents=True, exist_ok=True)
            spool = DurableSpool(spool_path)
            secrets = tuple(
                dict.fromkeys(
                    secret
                    for secret in (
                        *resolved_provider_secret_values(settings),
                        auth_token,
                        settings.runtime_service_token,
                    )
                    if secret
                )
            )
            tracker = ExchangeTracker(run_id, spool, secrets=secrets)
            delivery_task = asyncio.create_task(stream_evidence(spool, ingestor))

            async def execute_pipeline() -> dict:
                if not await media():
                    return {"termination": termination.snapshot()}
                await host.prepare(snapshot, tracker, transport=transport)
                return await host.converse(media)

            final_state = await supervise_execution(execute_pipeline(), delivery_task)
        except asyncio.CancelledError:
            termination.request("cancelled")
            raise
        except Exception as error:
            termination.request("pipeline_failure")
            # Do not log provider exception bodies, credential-bearing URLs or
            # request payloads. Native evidence already redacts known secrets.
            logger.warning("Twilio run {} failed ({})", run_id, type(error).__name__)
            diagnostics.append(
                _diagnostic(
                    "twilio_pipeline_failed",
                    "Twilio pipeline execution failed",
                    exception_type=type(error).__name__,
                )
            )
        finally:
            try:
                if host is not None:
                    await host.close()
            except Exception:
                cleanup_failed = True
                diagnostics.append(
                    _diagnostic(
                        "twilio_runtime_cleanup_failed",
                        "Twilio runtime cleanup failed",
                    )
                )
            finally:
                # Also runs when End/Cancel serialization was skipped because
                # Pipecat's socket was already disconnected, or prepare failed.
                await media.close()
                # Host resource cleanup is separate from carrier release. A
                # prior verified REST terminal state survives a capture error.
                termination.summary.cleanup_status = (
                    "confirmed" if media.provider_status in TERMINAL_STATUSES else "uncertain"
                )

            if host is not None and host.directory.exists():
                for kind in ("input", "output", "mixed", "pipeline_log"):
                    filename = "pipeline.log" if kind == "pipeline_log" else f"{kind}.wav"
                    if not (host.directory / filename).is_file():
                        continue
                    try:
                        # httpx timeouts do not bound an in-process ASGI call.
                        async with asyncio.timeout(20):
                            response = await client.post(
                                f"/api/runs/{run_id}/artifacts",
                                headers={"X-Voice-Runtime-Token": runtime_token},
                                json={
                                    "id": str(uuid5(NAMESPACE_URL, f"{run_id}/{kind}")),
                                    "kind": kind,
                                    "path": f"{run_id}/{filename}",
                                },
                            )
                            response.raise_for_status()
                    except Exception:
                        artifact_diagnostics.append(
                            diagnostic_dict(
                                severity="error",
                                category="artifact_failure",
                                source="runtime",
                                code="artifact_registration_failed",
                                message="Twilio call artifact could not be registered",
                                metadata={"kind": kind},
                            )
                        )
            if spool is not None:
                finalization = await finalize_evidence(spool, ingestor, delivery_task)
                evidence_incomplete = finalization.incomplete
                if finalization.diagnostic:
                    diagnostics.append(finalization.diagnostic)
            else:
                evidence_incomplete = True
            diagnostics.extend(media.diagnostics)
            diagnostics.extend(artifact_diagnostics)
            await _persist_twilio_outcome(
                call_id=call_id,
                run_id=run_id,
                media=media,
                final_state=final_state,
                diagnostics=diagnostics,
                evidence_incomplete=evidence_incomplete
                or cleanup_failed
                or bool(artifact_diagnostics),
                artifacts_incomplete=bool(artifact_diagnostics),
            )


async def _persist_twilio_outcome(
    *,
    call_id: str,
    run_id: str,
    media: TwilioMediaSession,
    final_state: dict,
    diagnostics: list[dict],
    evidence_incomplete: bool,
    artifacts_incomplete: bool,
    only_active: bool = False,
) -> None:
    termination = media.termination
    async with SessionFactory() as db:
        await bind_run_organization(db, run_id)
        # Match callback lock order so finalization cannot overwrite a
        # concurrent provider-terminal event or deadlock Call/Run locks.
        call = await db.get(Call, call_id, with_for_update=True, populate_existing=True)
        run = await db.get(Run, run_id, with_for_update=True, populate_existing=True)
        if only_active and (run is None or run.status not in {"queued", "claimed", "running"}):
            # The normal supervisor already persisted cancellation/completion.
            # Startup fallback must not duplicate or relabel that finalized run.
            return
        if run:
            for diagnostic in diagnostics:
                await persist_diagnostic(db, run_id, DiagnosticInput.model_validate(diagnostic))
            was_active = run.status in {"queued", "claimed", "running"}
            previous = run.final_state or {}
            if was_active:
                run.status = termination.summary.execution_status
                if run.status == "failed" and not run.error:
                    run.error = (
                        f"Twilio call ended before normal completion: {termination.summary.cause}"
                    )
                run.ended_at = run.ended_at or now()
            run.final_state = {
                **(run.final_state or {}),
                **final_state,
                "termination": termination.snapshot()
                if was_active
                else previous.get("termination", termination.snapshot()),
                "evidence_incomplete": bool((run.final_state or {}).get("evidence_incomplete"))
                or evidence_incomplete
                or artifacts_incomplete,
                "artifacts_incomplete": bool((run.final_state or {}).get("artifacts_incomplete"))
                or artifacts_incomplete,
            }
        if call:
            call.provider_metadata = {
                **(call.provider_metadata or {}),
                "release_status": termination.summary.cleanup_status,
                "rest_status": media.provider_status,
            }
            provider_status = TWILIO_STATUS_MAP.get(media.provider_status)
            if call.status not in {
                "completed",
                "failed",
                "canceled",
            } and provider_status in {"completed", "failed", "canceled"}:
                call.status = provider_status
                call.ended_at = call.ended_at or now()
        await db.commit()


async def finalize_twilio_startup_failure(
    *,
    call_id: str,
    run_id: str,
    media: TwilioMediaSession,
    cancelled: bool = False,
) -> None:
    """Cover failures outside the host/client startup guard after media claim."""
    media.termination.request("cancelled" if cancelled else "pipeline_failure")
    await media.close()
    await _persist_twilio_outcome(
        call_id=call_id,
        run_id=run_id,
        media=media,
        final_state={},
        diagnostics=[
            _diagnostic("twilio_startup_failed", "Twilio runtime startup failed"),
            *media.diagnostics,
        ],
        evidence_incomplete=True,
        artifacts_incomplete=False,
        only_active=True,
    )
