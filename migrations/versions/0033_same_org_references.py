"""Reject references from customer rows to another organization's records.

Install a database trigger for each single-column FK whose child and parent
both carry org_id. Existing FKs continue to own reference existence and
delete behavior; these guards add the missing tenant-equality invariant.
"""

import hashlib

import sqlalchemy as sa
from alembic import op

revision = "0033_same_org_refs"
down_revision = "0032_org_scoped_unique"
branch_labels = None
depends_on = None


def _tenant_foreign_keys(connection):
    return connection.execute(
        sa.text(
            """
            SELECT child.relname AS child_table,
                   parent.relname AS parent_table,
                   constraint_row.conname AS constraint_name,
                   child_column.attname AS child_column,
                   parent_column.attname AS parent_column
            FROM pg_constraint AS constraint_row
            JOIN pg_class AS child ON child.oid = constraint_row.conrelid
            JOIN pg_namespace AS child_schema ON child_schema.oid = child.relnamespace
            JOIN pg_class AS parent ON parent.oid = constraint_row.confrelid
            JOIN pg_namespace AS parent_schema ON parent_schema.oid = parent.relnamespace
            JOIN LATERAL unnest(constraint_row.conkey) WITH ORDINALITY
                 AS child_key(attnum, ordinal) ON true
            JOIN LATERAL unnest(constraint_row.confkey) WITH ORDINALITY
                 AS parent_key(attnum, ordinal) ON parent_key.ordinal = child_key.ordinal
            JOIN pg_attribute AS child_column
                 ON child_column.attrelid = child.oid AND child_column.attnum = child_key.attnum
            JOIN pg_attribute AS parent_column
                 ON parent_column.attrelid = parent.oid AND parent_column.attnum = parent_key.attnum
            WHERE constraint_row.contype = 'f'
              AND cardinality(constraint_row.conkey) = 1
              AND child_schema.nspname = current_schema()
              AND parent_schema.nspname = current_schema()
              AND EXISTS (
                  SELECT 1 FROM pg_attribute
                  WHERE attrelid = child.oid AND attname = 'org_id' AND NOT attisdropped
              )
              AND EXISTS (
                  SELECT 1 FROM pg_attribute
                  WHERE attrelid = parent.oid AND attname = 'org_id' AND NOT attisdropped
              )
            ORDER BY child.relname, constraint_row.conname
            """
        )
    ).mappings().all()


def upgrade() -> None:
    connection = op.get_bind()
    foreign_keys = _tenant_foreign_keys(connection)
    for fk in foreign_keys:
        child, parent = fk["child_table"], fk["parent_table"]
        local, remote = fk["child_column"], fk["parent_column"]
        mismatch = connection.execute(
            sa.text(
                f'SELECT 1 FROM "{child}" AS child '
                f'JOIN "{parent}" AS parent ON parent."{remote}" = child."{local}" '
                "WHERE child.org_id IS DISTINCT FROM parent.org_id LIMIT 1"
            )
        ).first()
        if mismatch:
            raise RuntimeError(
                f"Cross-organization reference exists: {child}.{local} -> {parent}.{remote}"
            )

    op.execute(
        """
        CREATE FUNCTION enforce_same_org_reference() RETURNS trigger
        LANGUAGE plpgsql AS $$
        DECLARE
            referenced_org text;
            referenced_id text;
        BEGIN
            referenced_id := to_jsonb(NEW)->>TG_ARGV[2];
            IF referenced_id IS NULL THEN
                RETURN NEW;
            END IF;
            EXECUTE format(
                'SELECT org_id::text FROM %I WHERE %I::text = $1',
                TG_ARGV[0], TG_ARGV[1]
            ) INTO referenced_org USING referenced_id;
            IF referenced_org IS NOT NULL AND referenced_org IS DISTINCT FROM NEW.org_id::text THEN
                RAISE EXCEPTION 'cross-organization reference violates tenant boundary'
                    USING ERRCODE = '23514', CONSTRAINT = TG_ARGV[3];
            END IF;
            RETURN NEW;
        END;
        $$
        """
    )
    for index, fk in enumerate(foreign_keys):
        child = fk["child_table"]
        constraint_name = fk["constraint_name"]
        local, remote = fk["child_column"], fk["parent_column"]
        parent = fk["parent_table"]
        suffix = hashlib.sha1(constraint_name.encode()).hexdigest()[:10]
        trigger_name = f"trg_org_fk_{index}_{suffix}"
        quote = connection.dialect.identifier_preparer.quote
        arguments = ", ".join(
            "'" + value.replace("'", "''") + "'"
            for value in (parent, remote, local, constraint_name)
        )
        op.execute(
            f"CREATE TRIGGER {quote(trigger_name)} BEFORE INSERT OR UPDATE ON {quote(child)} "
            f"FOR EACH ROW EXECUTE FUNCTION enforce_same_org_reference({arguments})"
        )


def downgrade() -> None:
    connection = op.get_bind()
    foreign_keys = _tenant_foreign_keys(connection)
    for index, fk in enumerate(foreign_keys):
        suffix = hashlib.sha1(fk["constraint_name"].encode()).hexdigest()[:10]
        trigger_name = f"trg_org_fk_{index}_{suffix}"
        op.execute(
            sa.text(f'DROP TRIGGER IF EXISTS "{trigger_name}" ON "{fk["child_table"]}"')
        )
    op.execute("DROP FUNCTION IF EXISTS enforce_same_org_reference()")
