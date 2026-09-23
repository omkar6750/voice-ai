"""Independent classifier and summary scheduling controls."""

from pydantic import Field, model_validator

from .base import ConfigModel, Identifier
from .providers import LLMConfig


class CadenceConfig(ConfigModel):
    enabled: bool = True
    node_exits: list[Identifier] = Field(default_factory=list)
    every_n_exchanges: int | None = Field(default=None, gt=0)
    interval_secs: float | None = Field(default=None, gt=0)
    explicit_requests: bool = True
    on_finalization: bool = False
    cooldown_secs: float = Field(default=0, ge=0)
    max_attempts: int = Field(default=100, gt=0)


class ClassifierConfig(CadenceConfig):
    node_exits: list[Identifier] = Field(default_factory=lambda: ["discovery", "qualification"])
    model: LLMConfig = Field(default_factory=LLMConfig)
    prompt: str = "Classify the supplied conversation using only observed evidence."
    answer_signals: list[str] = Field(default_factory=list)
    topic_signals: list[str] = Field(default_factory=list)
    keywords: list[str] = Field(default_factory=list)
    confidence_threshold: float = Field(default=0.8, ge=0, le=1)
    consecutive_verdicts: int = Field(default=1, gt=0)


class SummarizerConfig(CadenceConfig):
    enabled: bool = False
    model: LLMConfig = Field(default_factory=lambda: LLMConfig(max_tokens=512))
    prompt: str = "Summarize the supplied history faithfully; preserve decisions and facts."
    unsummarized_messages: int = Field(default=20, gt=0)
    unsummarized_exchanges: int | None = Field(default=None, gt=0)
    token_threshold: int | None = Field(default=None, gt=0)
    context_window_tokens: int = Field(default=8192, gt=0)
    compaction_threshold: float = Field(default=0.7, gt=0, lt=1)
    hard_ceiling: float = Field(default=0.9, gt=0, le=1)
    target_ratio: float = Field(default=0.4, gt=0, lt=1)
    output_budget_tokens: int = Field(default=512, gt=0)
    preserve_opening_messages: int = Field(default=2, ge=0)
    preserve_recent_messages: int = Field(default=6, ge=0)

    @model_validator(mode="after")
    def ordered_budgets(self):
        if not self.target_ratio < self.compaction_threshold < self.hard_ceiling:
            raise ValueError("require target_ratio < compaction_threshold < hard_ceiling")
        return self
