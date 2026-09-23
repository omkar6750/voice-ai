"""API DTOs reuse runtime-owned ingestion/retrieval contracts."""

from typing import Literal

from pydantic import Field
from voice_runtime.contracts.base import ConfigModel
from voice_runtime.contracts.knowledge import KnowledgeConfig, RetrievalConfig


def ingestion_config(value: dict) -> KnowledgeConfig:
    # Preserve legacy stored JSON; old KB-owned retrieval fields no longer control search.
    legacy = {
        "top_k",
        "context_budget",
        "timeout_seconds",
        "vector_weight",
        "keyword_weight",
        "rerank_enabled",
    }
    return KnowledgeConfig.model_validate(
        {key: item for key, item in value.items() if key not in legacy}
    )


class BaseCreate(ConfigModel):
    name: str = Field(min_length=1, max_length=120)
    config: KnowledgeConfig = Field(default_factory=KnowledgeConfig)


class SourceCreate(ConfigModel):
    title: str = Field(min_length=1, max_length=240)
    content: str = Field(min_length=1, max_length=2_000_000)
    kind: Literal["paste", "txt", "md", "pdf"] = "paste"


class SearchRequest(ConfigModel):
    query: str = Field(min_length=1, max_length=8000)
    retrieval: RetrievalConfig = Field(default_factory=RetrievalConfig)


class SearchHit(ConfigModel):
    chunk_id: str
    source_id: str
    title: str
    source_path: str | None
    ordinal: int
    content: str
    score: float
    score_type: Literal["weighted_rrf"] = "weighted_rrf"
    metadata: dict = Field(default_factory=dict)
