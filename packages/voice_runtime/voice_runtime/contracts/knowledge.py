"""Mutable corpus ingestion and agent-owned retrieval contracts."""

from typing import Literal

from pydantic import Field, model_validator

from .base import ConfigModel
from .tools import WaitConfig


class KnowledgeConfig(ConfigModel):
    chunk_size: int = Field(default=800, gt=0)
    chunk_overlap: int = Field(default=100, ge=0)
    markdown_aware: bool = True
    embedding_provider: Literal["gemini"] = "gemini"
    embedding_model: Literal["gemini-embedding-001"] = "gemini-embedding-001"
    embedding_dimensions: Literal[768] = 768
    normalize_embeddings: Literal[True] = True
    supported_sources: list[Literal["text", "pdf", "txt", "markdown"]] = Field(
        default_factory=lambda: ["text", "pdf", "txt", "markdown"]
    )
    extraction_max_chars: int = Field(default=2_000_000, gt=0)

    @model_validator(mode="after")
    def overlap_smaller_than_chunk(self):
        if self.chunk_overlap >= self.chunk_size:
            raise ValueError("chunk_overlap must be smaller than chunk_size")
        return self


class RetrievalConfig(ConfigModel):
    top_k: int = Field(default=5, ge=1, le=100)
    keyword_weight: float = Field(default=0.5, ge=0, le=1)
    vector_weight: float = Field(default=0.5, ge=0, le=1)
    rrf_k: int = Field(default=60, gt=0)
    min_vector_similarity: float | None = Field(default=None, ge=-1, le=1)
    min_keyword_score: float | None = Field(default=None, ge=0)
    result_budget_tokens: int = Field(default=1200, gt=0)
    timeout_secs: float = Field(default=10, gt=0)
    reranking_enabled: Literal[False] = False
    wait: WaitConfig = Field(default_factory=lambda: WaitConfig(mode="silent_wait"))

    @model_validator(mode="after")
    def nonzero_weights(self):
        if self.keyword_weight + self.vector_weight <= 0:
            raise ValueError("at least one retrieval weight must be positive")
        return self
