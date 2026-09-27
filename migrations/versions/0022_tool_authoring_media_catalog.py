"""Add explicit reusable-media metadata and WhatsApp tool configuration."""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision = "0022_tool_media_catalog"
down_revision = "0021_diagnostic_metadata_jsonb"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.alter_column("integration_media", "availability", new_column_name="status")
    op.alter_column("integration_media", "checked_at", new_column_name="last_verified_at")
    op.add_column(
        "integration_media",
        sa.Column("display_name", sa.String(255), nullable=True),
    )
    op.add_column(
        "integration_media",
        sa.Column("media_type", sa.String(30), nullable=True),
    )
    op.add_column(
        "integration_media",
        sa.Column("source", sa.String(30), nullable=True),
    )
    op.add_column(
        "integration_media",
        sa.Column(
            "provider_metadata",
            JSONB,
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
    )
    op.alter_column("integration_media", "sha256", existing_type=sa.String(64), nullable=True)
    op.execute(
        sa.text(
            """
            UPDATE integration_media
            SET display_name = filename,
                media_type = CASE
                    WHEN mime_type LIKE 'image/%' THEN 'image'
                    WHEN mime_type LIKE 'video/%' THEN 'video'
                    WHEN mime_type LIKE 'audio/%' THEN 'audio'
                    ELSE 'document'
                END,
                source = CASE WHEN source_path IS NULL THEN 'imported' ELSE 'uploaded' END
            WHERE display_name IS NULL
            """
        )
    )
    op.alter_column("integration_media", "display_name", nullable=False)
    op.alter_column("integration_media", "media_type", nullable=False)
    op.alter_column("integration_media", "source", nullable=False)
    op.create_check_constraint(
        "ck_integration_media_type",
        "integration_media",
        "media_type IN ('image','video','document','audio')",
    )
    op.create_check_constraint(
        "ck_integration_media_source",
        "integration_media",
        "source IN ('uploaded','imported')",
    )
    op.create_check_constraint(
        "ck_integration_media_status",
        "integration_media",
        "status IN ('available','unverified','unavailable','deleted')",
    )

    # The current development data has one active WhatsApp connection. Give
    # existing generated template tools the explicit account/template identity
    # required by the new typed contract; media remains optional until selected.
    op.execute(sa.text("ALTER TABLE public.tool_versions DISABLE TRIGGER guard_published"))
    op.execute(
        sa.text(
            """
            UPDATE tool_versions AS tv
            SET config = tv.config || jsonb_build_object(
                'whatsapp', jsonb_build_object(
                    'connection_id', connection.id,
                    'template_name', regexp_replace(t.name, '^whatsapp_template_', ''),
                    'language', 'en',
                    'parameter_mappings', '{}'::jsonb
                )
            )
            FROM tools AS t
            CROSS JOIN LATERAL (
                SELECT id
                FROM integration_connections
                WHERE provider = 'whatsapp' AND deleted_at IS NULL
                ORDER BY created_at
                LIMIT 1
            ) AS connection
            WHERE tv.tool_id = t.id
              AND tv.config->>'handler' = 'send_whatsapp_template'
              AND tv.config->'whatsapp' IS NULL
            """
        )
    )
    op.execute(sa.text("ALTER TABLE public.tool_versions ENABLE TRIGGER guard_published"))


def downgrade() -> None:
    raise RuntimeError("Tool authoring and media catalog must not be downgraded without a reviewed migration")
