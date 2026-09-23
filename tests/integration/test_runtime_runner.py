"""Real API/database with fake call driver; never touches hardware or providers."""

from datetime import UTC, datetime

import pytest
from test_execution_safety import setup_call
from voice_api.models import Run
from voice_runtime.execution.runner import execute_call


class FakeDriver:
    def __init__(self, fail=False):
        self.events = []
        self.fail = fail

    async def prepare(self, snapshot, tracker):
        self.events.append("prepare")
        assert snapshot["_resolved"]["endpoint"]["at_port"] == "COM16"
        tracker.assistant_message("Hello", datetime.now(UTC).isoformat())

    async def call(self, destination):
        self.events.append("call")
        if self.fail:
            raise RuntimeError("provider exception with sensitive body")
        return {"node": "closing"}

    async def close(self):
        self.events.append("close")


async def test_runtime_driver_evidence_and_cleanup(client, database, tmp_path):
    body = await setup_call(client)
    run_id = (await client.post("/api/calls", json=body)).json()["run_id"]
    driver = FakeDriver()
    assert (
        await execute_call(
            client,
            "operator-test",
            run_id,
            body["endpoint_id"],
            driver,
            tmp_path / "evidence.jsonl",
        )
        == "completed"
    )
    assert driver.events == ["prepare", "call", "close"]
    run = await database.get(Run, run_id)
    assert run.status == "completed" and run.final_state["evidence_incomplete"] is False
    assert (await client.get(f"/api/runs/{run_id}/timeline")).json()["messages"][0][
        "content"
    ] == "Hello"


async def test_failure_still_cleans_up_and_records_truth(client, database, tmp_path):
    body = await setup_call(client)
    run_id = (await client.post("/api/calls", json=body)).json()["run_id"]
    driver = FakeDriver(fail=True)
    assert (
        await execute_call(
            client,
            "operator-test",
            run_id,
            body["endpoint_id"],
            driver,
            tmp_path / "evidence.jsonl",
        )
        == "failed"
    )
    assert driver.events[-1] == "close"
    run = await database.get(Run, run_id)
    assert run.status == "failed" and "sensitive" not in run.error


async def test_cleanup_failure_keeps_endpoint_reserved(client, database, tmp_path):
    body = await setup_call(client)
    run_id = (await client.post("/api/calls", json=body)).json()["run_id"]

    class UncertainDriver(FakeDriver):
        async def close(self):
            raise OSError("modem cannot confirm hangup")

    with pytest.raises(RuntimeError, match="cleanup uncertain"):
        await execute_call(
            client,
            "operator-test",
            run_id,
            body["endpoint_id"],
            UncertainDriver(),
            tmp_path / "evidence.jsonl",
        )
    run = await database.get(Run, run_id)
    assert run.status == "running" and run.ended_at is None
