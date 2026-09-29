"""Reconciliation retains the runtime evidence that preceded recovery."""

from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastapi import HTTPException
from pydantic import ValidationError
from sqlalchemy.ext.asyncio import AsyncSession
from voice_api.api.v1.endpoints.reconciliation import ReconcileBody, reconcile


@pytest.mark.asyncio
async def test_reconciliation_preserves_run_history_and_adds_audit_facts():
    started_at = datetime(2026, 9, 1, tzinfo=UTC)
    ended_at = None
    original_state = {
        "last_node": "payment",
        "provider_result": {"attempt": 2, "status": "unknown"},
        "evidence_incomplete": False,
    }
    run = SimpleNamespace(
        id="run-1",
        endpoint_id="endpoint-1",
        status="uncertain",
        final_state=original_state.copy(),
        started_at=started_at,
        ended_at=ended_at,
        error="lease expired",
    )
    call = SimpleNamespace(id="call-1", status="uncertain", ended_at=None)
    callback = SimpleNamespace(status="uncertain")
    endpoint = SimpleNamespace(id="endpoint-1")
    session = AsyncMock(spec=AsyncSession)
    session.scalar.side_effect = ["endpoint-1", call, callback]
    session.get.side_effect = [endpoint, run]

    response = await reconcile(
        "run-1",
        ReconcileBody(
            transport_idle_verified=True,
            worker_stopped_verified=True,
            note="Worker stopped; modem idle",
        ),
        session,
    )

    assert response == {"status": "failed", "redialed": False}
    assert run.final_state["last_node"] == "payment"
    assert run.final_state["provider_result"] == {"attempt": 2, "status": "unknown"}
    assert run.final_state["evidence_incomplete"] is True
    audit = run.final_state
    assert audit["transport_idle_verified"] is True
    assert audit["worker_stopped_verified"] is True
    assert audit["operator_note"] == "Worker stopped; modem idle"
    assert datetime.fromisoformat(audit["reconciled_at"])
    assert run.status == call.status == callback.status == "failed"
    assert run.started_at == started_at
    assert run.ended_at is ended_at and call.ended_at is None
    assert run.error == "lease expired"
    session.commit.assert_awaited_once()
    assert session.get.await_args_list[0].kwargs == {"with_for_update": True}
    assert session.get.await_args_list[1].kwargs == {
        "with_for_update": True,
        "populate_existing": True,
    }
    assert original_state["evidence_incomplete"] is False


@pytest.mark.asyncio
async def test_reconciliation_rejects_non_uncertain_run_without_mutation():
    prior_state = {"result": "completed"}
    run = SimpleNamespace(status="completed", final_state=prior_state)
    session = AsyncMock(spec=AsyncSession)
    session.scalar.return_value = "endpoint-1"
    session.get.side_effect = [SimpleNamespace(id="endpoint-1"), run]

    with pytest.raises(HTTPException) as exc:
        await reconcile(
            "run-1",
            ReconcileBody(
                transport_idle_verified=True,
                worker_stopped_verified=True,
                note="verified",
            ),
            session,
        )

    assert exc.value.status_code == 409
    assert run.status == "completed"
    assert run.final_state == prior_state
    session.commit.assert_not_awaited()


@pytest.mark.parametrize("field", ["transport_idle_verified", "worker_stopped_verified"])
def test_unverified_recovery_cannot_construct_request(field):
    values = {
        "transport_idle_verified": True,
        "worker_stopped_verified": True,
        "note": "checked",
        field: False,
    }
    with pytest.raises(ValidationError):
        ReconcileBody(**values)


@pytest.mark.asyncio
async def test_missing_telephone_endpoint_does_not_release_or_mutate_anything():
    session = AsyncMock(spec=AsyncSession)
    session.scalar.return_value = None
    with pytest.raises(HTTPException) as error:
        await reconcile(
            "missing",
            ReconcileBody(
                transport_idle_verified=True, worker_stopped_verified=True, note="checked"
            ),
            session,
        )
    assert error.value.status_code == 404
    session.get.assert_not_awaited()
    session.commit.assert_not_awaited()
