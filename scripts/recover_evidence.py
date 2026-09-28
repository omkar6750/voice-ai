"""Validate or replay one run's pending evidence spool without rewriting its source."""

from __future__ import annotations

import argparse
import asyncio
import json
import os
from pathlib import Path

import httpx
from pydantic import ValidationError
from voice_api.core.config import get_settings
from voice_runtime.contracts.evidence import EvidenceBatch
from voice_runtime.execution.recovery import normalize_known_diagnostic

MAX_BATCH_SIZE = 100


def read_pending(path: Path) -> tuple[int, list[tuple[int, dict]]]:
    cursor = path.with_suffix(".ack")
    offset = int(cursor.read_text(encoding="ascii")) if cursor.exists() else 0
    size = path.stat().st_size
    if offset < 0 or offset > size:
        raise ValueError("Acknowledgement offset is outside the spool")
    if offset and not path.read_bytes()[offset - 1 : offset] == b"\n":
        raise ValueError("Acknowledgement offset is not at a record boundary")
    pending = []
    with path.open("rb") as stream:
        stream.seek(offset)
        while line := stream.readline():
            if not line.endswith(b"\n"):
                raise ValueError("Spool ends with a partial record")
            pending.append((stream.tell(), json.loads(line)))
    return offset, pending


def _write_ack(path: Path, offset: int) -> None:
    cursor = path.with_suffix(".ack")
    temporary = cursor.with_suffix(".ack.tmp")
    with temporary.open("w", encoding="ascii", newline="") as stream:
        stream.write(str(offset))
        stream.flush()
        os.fsync(stream.fileno())
    os.replace(temporary, cursor)


def _fully_acknowledged(path: Path) -> bool:
    return int(path.with_suffix(".ack").read_text(encoding="ascii")) >= path.stat().st_size


async def recover(run_id: str, spool_path: Path, api_url: str, apply: bool) -> dict:
    original_offset, pending = read_pending(spool_path)
    normalized: list[dict] = []
    correction_indexes: list[int] = []
    for index, (_, record) in enumerate(pending, start=1):
        value, corrected = normalize_known_diagnostic(record)
        normalized.append(value)
        if corrected:
            correction_indexes.append(index)

    # Validate all pending records before any API write, so dry-run and apply share
    # the same all-spool gate and no partial recovery starts with a later poison row.
    batches = []
    for start in range(0, len(normalized), MAX_BATCH_SIZE):
        try:
            batches.append(EvidenceBatch(records=normalized[start : start + MAX_BATCH_SIZE]))
        except ValidationError as exc:
            first = exc.errors(include_input=False)[0]
            local_index = first["loc"][1] if len(first["loc"]) > 1 else None
            global_index = start + local_index + 1 if isinstance(local_index, int) else None
            kind = (
                normalized[start + local_index].get("kind")
                if isinstance(local_index, int)
                else None
            )
            location = ".".join(str(part) for part in first["loc"])
            raise ValueError(
                f"Pending record {global_index} ({kind}) is invalid at {location}"
            ) from None
    summary = {
        "run_id": run_id,
        "mode": "apply" if apply else "dry-run",
        "ack_offset": original_offset,
        "pending_records": len(pending),
        "corrected_diagnostics": correction_indexes,
        "pending_exchanges": sum(r.get("kind") == "exchange" for r in normalized),
        "pending_messages": sum(r.get("kind") == "message" for r in normalized),
    }
    if not apply:
        return summary
    if not batches:
        summary["replayed_records"] = 0
        return summary

    token = get_settings().operator_token
    if not token:
        raise RuntimeError("VOICE_OPERATOR_TOKEN is not configured")
    async with httpx.AsyncClient(base_url=api_url, timeout=30) as client:
        replayed = 0
        for batch_index, batch in enumerate(batches):
            response = await client.post(
                f"/api/runs/{run_id}/evidence",
                headers={"Authorization": f"Bearer {token}"},
                json=batch.model_dump(mode="json"),
            )
            if not 200 <= response.status_code < 300:
                raise RuntimeError(
                    f"Evidence API rejected a batch with HTTP {response.status_code}"
                )
            if response.json().get("accepted") != len(batch.records):
                raise RuntimeError("API did not confirm the full evidence batch")
            last_record_index = min((batch_index + 1) * MAX_BATCH_SIZE, len(pending)) - 1
            _write_ack(spool_path, pending[last_record_index][0])
            replayed += len(batch.records)

        response = await client.get(
            f"/api/runs/{run_id}/timeline",
            headers={"Authorization": f"Bearer {token}"},
        )
        if not 200 <= response.status_code < 300:
            raise RuntimeError(
                f"Evidence timeline verification returned HTTP {response.status_code}"
            )
        timeline = response.json()
        summary["persisted_exchanges"] = len(timeline["exchanges"])
        summary["persisted_messages"] = len(timeline["messages"])
        summary["replayed_records"] = replayed
        if not await asyncio.to_thread(_fully_acknowledged, spool_path):
            raise RuntimeError("Replay ended before the spool was fully acknowledged")
    return summary


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--spool", type=Path)
    parser.add_argument("--api-url", default="http://127.0.0.1:8000")
    parser.add_argument(
        "--apply", action="store_true", help="Persist and acknowledge validated records"
    )
    args = parser.parse_args()
    spool_path = args.spool or Path("data/evidence") / f"{args.run_id}.jsonl"
    print(
        json.dumps(
            asyncio.run(recover(args.run_id, spool_path, args.api_url, args.apply)), indent=2
        )
    )


if __name__ == "__main__":
    main()
