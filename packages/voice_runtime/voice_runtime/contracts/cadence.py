"""Independent classifier and summary scheduling controls."""

from typing import Literal

from pydantic import Field, model_validator

from .base import ConfigModel, Identifier
from .providers import LLMConfig


class CadenceConfig(ConfigModel):
    enabled: bool = True
    node_entries: list[Identifier] = Field(default_factory=list)
    node_exits: list[Identifier] = Field(default_factory=list)
    every_n_exchanges: int | None = Field(default=None, gt=0)
    interval_secs: float | None = Field(default=None, gt=0)
    explicit_requests: bool = True
    on_finalization: bool = False
    cooldown_secs: float = Field(default=0, ge=0)
    max_attempts: int = Field(default=100, gt=0)


class JevQuestion(ConfigModel):
    type: str = "choice"
    instructions: str = ""
    criteria: dict[str, str] = Field(default_factory=dict)


def default_jev_questions() -> dict[str, JevQuestion]:
    return {
        "lead_temperature": JevQuestion(
            type="choice",
            instructions=(
                "Classify the contact's current sales intent based primarily on their behavior and meaning in the conversation. "
                "Voice-call responses are often very short, so do not treat short answers such as 'yeah', 'okay', 'hmm', or 'sure' as negative by themselves. "
                "Consider whether the contact has a real need, demonstrates interest in the offering, asks buying-related questions, indicates timing or urgency, or shows resistance. "
                "When evidence supports multiple classifications or contains conflicting signals, preserve that uncertainty."
            ),
            criteria={
                "hot": "The contact shows clear current buying intent or meaningful progression toward a purchase. Signals may include confirming a real need, wanting the service soon, asking about price, timeline, implementation, next steps, availability, payment, or requesting a meeting or proposal.",
                "warm": "The contact shows genuine interest or relevance but has not demonstrated strong immediate purchase intent. They may listen, answer discovery questions positively, acknowledge a need, or ask general questions, but timing, commitment, urgency, or next-step intent remains uncertain.",
                "cold": "The contact demonstrates little current interest or weak relevance. Signals include saying they are only browsing, having no current need, rejecting the offering, repeatedly avoiding engagement, stating bad timing without future intent, or otherwise showing no meaningful movement toward a purchase.",
            },
        ),
        "service_fit": JevQuestion(
            type="choice",
            instructions="Determine how closely the contact's actual need matches the service currently being offered (custom modern web & mobile app development).",
            criteria={
                "strong_fit": "The contact clearly needs custom web or mobile application development, UI/UX redesign, or secure cloud backends.",
                "possible_fit": "The need may overlap with the offered service (e.g. existing tech team needing support, adjacent integrations) but requires clarification.",
                "poor_fit": "The contact needs something materially different (e.g. non-software hardware, marketing-only, or no development needed).",
            },
        ),
        "tone": JevQuestion(
            type="choice",
            instructions="What is the contact's conversational tone and attitude?",
            criteria={
                "receptive": "Friendly, engaged, curious, or actively answering questions.",
                "hesitant": "Reserved, busy, distracted, but not hostile.",
                "resistant": "Disinterested, irritated, abusive, or explicitly asking to stop.",
            },
        ),
    }


class JevClassifierConfig(ConfigModel):
    model: str = "jev-latest"
    api_url: str = "https://api.typesafe.ai/v1/systemone"
    questions: dict[str, JevQuestion] = Field(default_factory=default_jev_questions)

    output_fields: list[str] = Field(
        default_factory=lambda: ["lead_temperature", "service_fit", "tone"]
    )


class ClassifierLLMConfig(LLMConfig):
    prompt: str = "Classify the supplied conversation using only observed evidence."
    output_fields: dict[str, list[str]] = Field(
        default_factory=lambda: {
            "lead_temperature": ["hot", "warm", "cold"],
            "service_fit": ["strong_fit", "possible_fit", "poor_fit"],
            "tone": ["receptive", "hesitant", "resistant"],
        }
    )
    max_output_tokens: int = Field(default=96, gt=0, le=512)


class ClassifierConfig(CadenceConfig):
    classifier_type: Literal["llm", "jev"] = "llm"
    node_exits: list[Identifier] = Field(default_factory=lambda: ["discovery", "qualification"])
    llm: ClassifierLLMConfig | None = Field(default_factory=ClassifierLLMConfig)
    jev: JevClassifierConfig | None = None
    max_result_chars: int = Field(default=512, gt=0, le=4096)
    include_confidence: bool = False
    include_probabilities: bool = False
    answer_signals: list[str] = Field(default_factory=list)
    topic_signals: list[str] = Field(default_factory=list)
    keywords: list[str] = Field(default_factory=list)
    confidence_threshold: float = Field(default=0.8, ge=0, le=1)
    consecutive_verdicts: int = Field(default=1, gt=0)

    @model_validator(mode="before")
    @classmethod
    def migrate_legacy_classifier_shape(cls, value):
        if not isinstance(value, dict):
            return value
        value = dict(value)
        classifier_type = value.get("classifier_type", "llm")
        if "llm" not in value and ("model" in value or "prompt" in value):
            legacy_model = dict(value.pop("model", {}) or {})
            if "prompt" in value:
                legacy_model["prompt"] = value.pop("prompt")
            value["llm"] = legacy_model
        if classifier_type == "jev":
            value["llm"] = None
            value.setdefault("jev", {"questions": default_jev_questions()})
        else:
            value["jev"] = None
        return value

    @model_validator(mode="after")
    def selected_branch_only(self):
        if self.classifier_type == "llm":
            if self.llm is None:
                object.__setattr__(self, "llm", ClassifierLLMConfig())
            object.__setattr__(self, "jev", None)
        else:
            if self.jev is None:
                object.__setattr__(self, "jev", JevClassifierConfig())
            object.__setattr__(self, "llm", None)
        return self


class SummarizerConfig(CadenceConfig):
    enabled: bool = False
    model: LLMConfig = Field(default_factory=lambda: LLMConfig(max_tokens=512))
    prompt: str = "Summarize the supplied history faithfully; preserve decisions and facts."
    answer_signals: list[str] = Field(default_factory=list)
    topic_signals: list[str] = Field(default_factory=list)
    keywords: list[str] = Field(default_factory=list)
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
