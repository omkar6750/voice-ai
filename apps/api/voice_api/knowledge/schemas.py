"""Knowledge API DTOs; configuration is local until runtime contracts settle."""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class KnowledgeConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")
    embedding_model: Literal["gemini-embedding-001"] = "gemini-embedding-001"
    chunk_size: int = Field(default=1600, ge=100, le=6000)
    chunk_overlap: int = Field(default=200, ge=0)
    top_k: int = Field(default=5, ge=1, le=50)
    context_budget: int = Field(default=1200, ge=1, le=20000)
    timeout_seconds: float = Field(default=10, gt=0, le=120)
    vector_weight: float = Field(default=0.5, ge=0, le=1)
    keyword_weight: float = Field(default=0.5, ge=0, le=1)
    rerank_enabled: bool = False

    @model_validator(mode="after")
    def validate_options(self):
        if self.chunk_overlap >= self.chunk_size:
            raise ValueError("chunk_overlap must be smaller than chunk_size")
        if self.vector_weight + self.keyword_weight <= 0:
            raise ValueError("At least one retrieval weight must be positive")
        if self.rerank_enabled:
            raise ValueError("Reranking is unavailable: no reranker adapter is configured")
        return self


class BaseCreate(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    config: KnowledgeConfig = Field(default_factory=KnowledgeConfig)


class SourceCreate(BaseModel):
    title: str = Field(min_length=1, max_length=240)
    content: str = Field(min_length=1, max_length=5_000_000)
    kind: Literal["paste", "txt", "md"] = "paste"


class SearchRequest(BaseModel):
    query: str = Field(min_length=1, max_length=8000)


class SearchHit(BaseModel):
    chunk_id: str
    source_id: str
    title: str
    source_path: str | None
    ordinal: int
    content: str
    score: float
    metadata: dict = Field(default_factory=dict)
