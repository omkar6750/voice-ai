"""Store Meta media references in template config and remove local media paths."""

import hashlib
import json
import re

import sqlalchemy as sa
from alembic import op

revision = "0026_meta_hosted_whatsapp_media"
down_revision = "0025_llm_usage_counts"
branch_labels = None
depends_on = None


def _resolve_header(connection, config: dict) -> dict | None:
    whatsapp = config.get("whatsapp")
    if not isinstance(whatsapp, dict):
        return None
    old_id = whatsapp.pop("header_media_id", None)
    if old_id is None:
        return None
    media = (
        connection.execute(
            sa.text(
                """SELECT id, provider_media_id, media_type, status, connection_id
               FROM integration_media WHERE id = :id OR provider_media_id = :id"""
            ),
            {"id": str(old_id)},
        )
        .mappings()
        .all()
    )
    media = [row for row in media if row["connection_id"] == whatsapp.get("connection_id")]
    if len(media) != 1 or media[0]["status"] != "available":
        raise RuntimeError(f"Cannot safely resolve WhatsApp media reference {old_id!r}")
    format_by_type = {"image": "IMAGE", "video": "VIDEO", "document": "DOCUMENT"}
    media_format = format_by_type.get(media[0]["media_type"])
    if media_format is None:
        raise RuntimeError(f"Unsupported template media type for reference {old_id!r}")
    if not re.fullmatch(r"[0-9]{1,120}", media[0]["provider_media_id"]):
        raise RuntimeError(f"Invalid Meta media ID for reference {old_id!r}")
    whatsapp["header"] = {"format": media_format, "media_id": media[0]["provider_media_id"]}
    return whatsapp["header"]


def _fingerprint(config: dict) -> str:
    payload = json.dumps(
        config, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False
    ).encode()
    return hashlib.sha256(payload).hexdigest()


def upgrade() -> None:
    connection = op.get_bind()
    paths_to_clean = connection.scalar(
        sa.text("SELECT count(*) FROM integration_media WHERE source_path IS NOT NULL")
    )
    if paths_to_clean:
        raise RuntimeError(
            "Run scripts/cleanup_whatsapp_media_files.py --apply before migrating media storage"
        )
    changed_tool_configs: dict[str, dict] = {}
    for row in connection.execute(
        sa.text(
            "SELECT id, config FROM tool_versions WHERE config->>'handler' = 'send_whatsapp_template'"
        )
    ).mappings():
        config = dict(row["config"])
        if "header_media_id" not in config.get("whatsapp", {}):
            continue
        _resolve_header(connection, config)
        changed_tool_configs[row["id"]] = config

    # Development data migration intentionally rewrites existing published configs;
    # ordinary API edits continue to enforce the published-version guard.
    connection.execute(sa.text("ALTER TABLE public.tool_versions DISABLE TRIGGER guard_published"))
    try:
        for version_id, config in changed_tool_configs.items():
            connection.execute(
                sa.text("UPDATE tool_versions SET config = CAST(:config AS jsonb) WHERE id = :id"),
                {"id": version_id, "config": json.dumps(config)},
            )
    finally:
        connection.execute(
            sa.text("ALTER TABLE public.tool_versions ENABLE TRIGGER guard_published")
        )

    # Keep active execution snapshots executable with the same pinned media ID.
    for row in connection.execute(
        sa.text(
            "SELECT id, resolved_config FROM runs WHERE status IN ('queued','claimed','running','uncertain')"
        )
    ).mappings():
        snapshot = dict(row["resolved_config"])
        tools = snapshot.get("_resolved", {}).get("tools", {})
        changed = False
        for entry in tools.values() if isinstance(tools, dict) else ():
            definition = entry.get("definition", {}) if isinstance(entry, dict) else {}
            whatsapp = definition.get("whatsapp") if isinstance(definition, dict) else None
            if isinstance(whatsapp, dict) and "header_media_id" in whatsapp:
                _resolve_header(connection, definition)
                changed = True
        if changed:
            connection.execute(
                sa.text(
                    "UPDATE runs SET resolved_config = CAST(:config AS jsonb), config_hash = :hash WHERE id = :id"
                ),
                {"id": row["id"], "config": json.dumps(snapshot), "hash": _fingerprint(snapshot)},
            )

    op.drop_column("integration_media", "source_path")


def downgrade() -> None:
    raise RuntimeError("Meta-hosted media migration is not safely reversible")
