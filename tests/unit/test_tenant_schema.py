"""Keep staged tenant backfill aligned with the customer-owned ORM models."""

import ast
from pathlib import Path

from voice_api.db.base_class import Base
from voice_api.models import Organization  # noqa: F401 - registers model package


def test_staged_org_backfill_covers_every_customer_model() -> None:
    migration_path = (
        Path(__file__).resolve().parents[2]
        / "migrations/versions/0029_stage_org_columns.py"
    )
    module = ast.parse(migration_path.read_text(encoding="utf-8"))
    tables_assignment = next(
        node
        for node in module.body
        if isinstance(node, ast.Assign)
        and any(isinstance(target, ast.Name) and target.id == "CUSTOMER_TABLES" for target in node.targets)
    )
    customer_tables = set(ast.literal_eval(tables_assignment.value))
    modeled = {table.name for table in Base.metadata.tables.values() if "org_id" in table.c}
    # The later provider credential and runtime context event migrations add these tables.
    assert modeled == customer_tables | {
        "provider_credentials", "run_context_events", "credential_leases",
        "recording_deletions", "recording_deletion_items",
    }
    assert len(modeled) == 42
    assert "runtime_endpoints" not in modeled
    assert "organizations" not in modeled
