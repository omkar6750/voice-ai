"""Add the database tenant invariant for runtime assignments."""

from alembic import op

revision = "0045_runtime_tenant_guard"
down_revision = "0044_separate_runtime"
branch_labels = None
depends_on = None


def upgrade():
    op.execute(
        "CREATE TRIGGER runtime_assignment_same_org BEFORE INSERT OR UPDATE ON runtime_assignments FOR EACH ROW EXECUTE FUNCTION enforce_same_org_reference('runs','id','run_id','runtime_assignments_run_id_fkey')"
    )


def downgrade():
    op.execute("DROP TRIGGER runtime_assignment_same_org ON runtime_assignments")
