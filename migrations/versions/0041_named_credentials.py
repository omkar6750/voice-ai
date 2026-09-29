"""Named org credentials, scoped secret versions and server-only run leases."""

import sqlalchemy as sa
from alembic import op

revision = "0041_named_credentials"
down_revision = "0040_merge_clerk_and_runtime"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_constraint("uq_provider_credentials_org", "provider_credentials", type_="unique")
    op.add_column("provider_credentials", sa.Column("name", sa.String(120), nullable=True))
    op.execute("UPDATE provider_credentials SET name = provider || ' default'")
    op.alter_column("provider_credentials", "name", nullable=False)
    op.add_column("provider_credentials", sa.Column("legacy_default", sa.Boolean(), nullable=False, server_default=sa.false()))
    op.execute("UPDATE provider_credentials SET legacy_default = true")
    for column in (
        sa.Column("purpose", sa.String(40), nullable=False, server_default="api_key"),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("status", sa.String(20), nullable=False, server_default="stored"),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
    ):
        op.add_column("provider_credentials", column)
    op.create_index("uq_provider_credentials_org_name", "provider_credentials", ["org_id", "name"],
                    unique=True, postgresql_where=sa.text("deleted_at IS NULL"))
    op.create_check_constraint("ck_provider_credentials_version", "provider_credentials", "version > 0")
    op.create_check_constraint("ck_provider_credentials_status", "provider_credentials", "status IN ('stored', 'deleted')")
    for table in ("integration_secrets", "calendar_integration_secrets"):
        op.add_column(table, sa.Column("version", sa.Integer(), nullable=False, server_default="1"))
    op.add_column("integration_connections", sa.Column("credential_id", sa.String(36), nullable=True))
    op.create_foreign_key("fk_integration_connections_credential", "integration_connections", "provider_credentials", ["credential_id"], ["id"])
    op.create_index("ix_integration_connections_credential_id", "integration_connections", ["credential_id"])
    op.create_table("credential_leases",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("org_id", sa.String(36), sa.ForeignKey("organizations.id"), nullable=False),
        sa.Column("run_id", sa.String(36), sa.ForeignKey("runs.id"), nullable=False),
        sa.Column("credential_id", sa.String(36), sa.ForeignKey("provider_credentials.id"), nullable=False),
        sa.Column("credential_version", sa.Integer(), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.CheckConstraint("credential_version > 0", name="ck_credential_leases_version"),
        sa.UniqueConstraint("run_id", "credential_id", "credential_version", name="uq_credential_leases_run_version"),
    )
    for column in ("org_id", "run_id", "credential_id"):
        op.create_index(f"ix_credential_leases_{column}", "credential_leases", [column])
    op.create_table("call_admission",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("run_id", sa.String(36), sa.ForeignKey("runs.id", ondelete="SET NULL")),
        sa.Column("expires_at", sa.DateTime(timezone=True)),
        sa.CheckConstraint("id = 1", name="ck_call_admission_singleton"))
    op.execute("INSERT INTO call_admission (id) VALUES (1)")
    for table, parent, column in (
        ("integration_connections", "provider_credentials", "credential_id"),
        ("credential_leases", "provider_credentials", "credential_id"),
        ("credential_leases", "runs", "run_id"),
    ):
        op.execute(f"""CREATE TRIGGER trg_named_{table}_{column} BEFORE INSERT OR UPDATE ON {table}
            FOR EACH ROW EXECUTE FUNCTION enforce_same_org_reference('{parent}', 'id', '{column}', 'same_org_named_credential')""")
    op.execute("""
        CREATE FUNCTION guard_named_credential() RETURNS trigger LANGUAGE plpgsql AS $$
        BEGIN
            IF NEW.id IS DISTINCT FROM OLD.id OR NEW.org_id IS DISTINCT FROM OLD.org_id
               OR NEW.provider IS DISTINCT FROM OLD.provider OR NEW.purpose IS DISTINCT FROM OLD.purpose
               OR NEW.legacy_default IS DISTINCT FROM OLD.legacy_default
               OR OLD.deleted_at IS NOT NULL THEN
                RAISE EXCEPTION 'credential identity is immutable' USING ERRCODE = '23514';
            END IF;
            IF NEW.ciphertext IS DISTINCT FROM OLD.ciphertext AND NEW.deleted_at IS NULL
               AND NEW.version <> OLD.version + 1 THEN
                RAISE EXCEPTION 'credential replacement requires next version' USING ERRCODE = '23514';
            END IF;
            IF NEW.version < OLD.version OR NEW.version > OLD.version + 1 THEN
                RAISE EXCEPTION 'invalid credential version' USING ERRCODE = '23514';
            END IF;
            IF NEW.deleted_at IS NOT NULL THEN
                UPDATE credential_leases SET revoked_at = now()
                WHERE credential_id = OLD.id AND revoked_at IS NULL;
            END IF;
            RETURN NEW;
        END $$;
    """)
    op.execute(
        "CREATE TRIGGER trg_named_credential_identity BEFORE UPDATE ON provider_credentials "
        "FOR EACH ROW EXECUTE FUNCTION guard_named_credential()"
    )


def downgrade() -> None:
    raise RuntimeError("Named credential identities and revocations cannot be discarded")
