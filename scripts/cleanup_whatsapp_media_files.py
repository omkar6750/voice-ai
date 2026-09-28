"""Dry-run-first removal of legacy locally retained WhatsApp media files."""

import argparse
import asyncio
from pathlib import Path

from sqlalchemy import text
from voice_api.db.session import SessionFactory


def _resolved_path(path: str | Path) -> Path:
    return Path(path).resolve()


def _is_symlink(path: str | Path) -> bool:
    return Path(path).is_symlink()


async def cleanup(*, apply: bool) -> int:
    repository = _resolved_path(__file__).parents[1]
    managed_root = _resolved_path(repository / "data" / "integration-media")
    unsafe = 0
    async with SessionFactory() as session:
        rows = (
            (await session.execute(text("SELECT id, source_path FROM integration_media")))
            .mappings()
            .all()
        )
        for row in rows:
            if not row["source_path"]:
                continue
            source_path = Path(row["source_path"])
            if _is_symlink(source_path):
                print(f"UNSAFE (left untouched): {row['id']} -> symlink {source_path}")
                unsafe += 1
                continue
            target = _resolved_path(source_path)
            if target == managed_root or not target.is_relative_to(managed_root):
                print(f"UNSAFE (left untouched): {row['id']} -> {target}")
                unsafe += 1
                continue
            if target.is_file():
                print(f"{'DELETE' if apply else 'WOULD DELETE'}: {target}")
                if apply:
                    target.unlink()
            else:
                print(f"MISSING: {row['id']} -> {target}")
            if apply:
                await session.execute(
                    text("UPDATE integration_media SET source_path = NULL WHERE id = :id"),
                    {"id": row["id"]},
                )
        if apply:
            await session.commit()
    print(f"Mode: {'apply' if apply else 'dry-run'}; unsafe paths: {unsafe}")
    return unsafe


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply", action="store_true", help="Delete only verified in-root files")
    args = parser.parse_args()
    unsafe = asyncio.run(cleanup(apply=args.apply))
    if unsafe:
        raise SystemExit(2)


if __name__ == "__main__":
    main()
