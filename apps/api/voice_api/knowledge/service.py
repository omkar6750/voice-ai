"""Compatibility exports for the canonical, tenant-scoped knowledge service."""

from voice_api.services.knowledge_service import (
    SEARCH_SQL,
    activate_build,
    apply_budget,
    build_is_current,
    build_source,
    locked_source,
    search,
    weighted_rrf,
)

__all__ = [
    "SEARCH_SQL",
    "activate_build",
    "apply_budget",
    "build_is_current",
    "build_source",
    "locked_source",
    "search",
    "weighted_rrf",
]
