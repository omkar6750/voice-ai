"""Recover expired ownership on authorized reads, without polling or redial."""

from datetime import timedelta

from sqlalchemy import select

from voice_api.models import Call, Run, RuntimeAssignment
from voice_api.models.common import now


async def recover_expired_assignments(session, run_id=None):
    # Grace allows a terminal batch in flight to arrive after the execution lease.
    query = select(RuntimeAssignment).where(
        RuntimeAssignment.state.in_(["starting", "active", "stopping"]),
        RuntimeAssignment.lease_expires_at < now() - timedelta(seconds=5),
    )
    if run_id:
        query = query.where(RuntimeAssignment.run_id == run_id)
    assignments = (await session.scalars(query)).all()
    changed = 0
    for candidate in assignments:
        # Match synchronization's lock order: call, assignment, then run.
        call = await session.scalar(
            select(Call).where(Call.run_id == candidate.run_id).with_for_update()
        )
        assignment = await session.get(
            RuntimeAssignment, candidate.run_id, with_for_update=True, populate_existing=True
        )
        if assignment.state not in {
            "starting",
            "active",
            "stopping",
        } or assignment.lease_expires_at >= now() - timedelta(seconds=5):
            continue
        run = await session.get(Run, assignment.run_id, with_for_update=True)
        if run is None or run.status not in {"queued", "claimed", "running"}:
            continue
        assignment.state = "uncertain"
        run.status = "uncertain"
        run.ended_at = None
        run.error = "Runtime lease expired; execution and transport release are unconfirmed"
        run.final_state = {
            **(run.final_state or {}),
            "diagnostic": {
                "code": "runtime_lease_expired",
                "generation": assignment.generation,
                "boot_id": assignment.boot_id,
                "uncertain": True,
            },
        }
        if call and call.status not in {"completed", "failed", "cancelled"}:
            call.status = "uncertain"
            call.ended_at = None
        changed += 1
    if changed:
        await session.commit()
    return changed
