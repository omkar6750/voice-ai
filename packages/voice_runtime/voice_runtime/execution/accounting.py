"""Provider-neutral usage coverage and immutable estimated cost calculations.

Inputs reference existing operation spans; retries are distinct attempts, not
duplicate operations. Adapters supply documented billable quantities. This
module does not infer provider prices, retries, or token usage from transcript.
"""

from __future__ import annotations

from collections import defaultdict
from decimal import Decimal
from typing import Annotated, Literal

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, model_validator

Quantity = Annotated[Decimal, Field(ge=0, allow_inf_nan=False)]


class AccountingValue(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class UsageMeasurement(AccountingValue):
    dimension: str = Field(min_length=1, max_length=80)
    quantity: Quantity | None = None
    source: Literal[
        "provider_reported",
        "framework_reported",
        "framework_estimated",
        "local_estimate",
        "derived",
        "unknown",
    ] = "unknown"
    completeness: Literal["final", "partial", "estimated", "missing", "unknown"] = "unknown"
    # Gross prompt, total and reasoning telemetry may overlap billable units.
    # A provider adapter explicitly marks the disjoint quantities to price.
    billable: bool = True

    @model_validator(mode="after")
    def truthful_measurement(self):
        if self.quantity is None and self.completeness in {"final", "partial", "estimated"}:
            raise ValueError("Measured completeness requires a quantity")
        if self.quantity is not None and self.completeness == "missing":
            raise ValueError("Missing measurements cannot contain a quantity")
        if (
            self.source in {"framework_estimated", "local_estimate"}
            and self.completeness != "estimated"
        ):
            raise ValueError("Estimated sources must be labeled estimated")
        return self


class AttemptUsage(AccountingValue):
    attempt_id: str = Field(min_length=1)
    operation_id: str = Field(min_length=1)
    attempt_index: int = Field(default=1, ge=1)
    purpose: Literal["foreground", "classifier", "summarizer", "background", "other"]
    family: Literal["llm", "stt", "tts", "embedding", "realtime", "other"] = "llm"
    provider: str = Field(min_length=1)
    model: str = Field(min_length=1)
    service_tier: str | None = None
    started_at: AwareDatetime
    status: Literal["completed", "interrupted", "failed", "cancelled", "unknown"]
    measurements: tuple[UsageMeasurement, ...] = ()

    @model_validator(mode="after")
    def unique_dimensions(self):
        dimensions = [measurement.dimension for measurement in self.measurements]
        if len(dimensions) != len(set(dimensions)):
            raise ValueError("An attempt must contain one measurement per dimension")
        return self


class PricingRule(AccountingValue):
    rule_id: str = Field(min_length=1)
    catalog_version: str = Field(min_length=1)
    provider: str = Field(min_length=1)
    model: str = Field(min_length=1)
    family: Literal["llm", "stt", "tts", "embedding", "realtime", "other"] = "llm"
    service_tier: str | None = None
    dimension: str = Field(min_length=1)
    effective_from: AwareDatetime
    effective_to: AwareDatetime | None = None
    accessed_at: AwareDatetime
    source_url: str = Field(pattern=r"^https://", min_length=9)
    currency: str = Field(pattern=r"^[A-Z]{3}$")
    unit_quantity: Decimal = Field(gt=0, allow_inf_nan=False)
    rate: Quantity

    @model_validator(mode="after")
    def valid_interval(self):
        if self.effective_to is not None and self.effective_to <= self.effective_from:
            raise ValueError("Pricing end must follow start")
        return self

    def matches(self, attempt: AttemptUsage, dimension: str) -> bool:
        return (
            self.provider == attempt.provider
            and self.model == attempt.model
            and self.family == attempt.family
            and self.service_tier == attempt.service_tier
            and self.dimension == dimension
            and self.effective_from <= attempt.started_at
            and (self.effective_to is None or attempt.started_at < self.effective_to)
        )


class CostLine(AccountingValue):
    attempt_id: str
    operation_id: str
    dimension: str
    quantity: Quantity | None
    status: Literal["priced", "partial", "usage_missing", "price_missing", "ambiguous_price"]
    currency: str | None = None
    amount: Quantity | None = None
    rate: Quantity | None = None
    unit_quantity: Decimal | None = None
    pricing_rule_id: str | None = None
    catalog_version: str | None = None
    source_url: str | None = None


def price_attempt(attempt: AttemptUsage, rules: tuple[PricingRule, ...]) -> tuple[CostLine, ...]:
    """Pin source, rate, version and currency at calculation time; never reprice implicitly."""
    lines = []
    for measurement in attempt.measurements:
        if not measurement.billable:
            continue
        fields = {
            "attempt_id": attempt.attempt_id,
            "operation_id": attempt.operation_id,
            "dimension": measurement.dimension,
            "quantity": measurement.quantity,
        }
        if measurement.quantity is None:
            lines.append(CostLine(**fields, status="usage_missing"))
            continue
        matches = [rule for rule in rules if rule.matches(attempt, measurement.dimension)]
        if len(matches) != 1:
            lines.append(
                CostLine(**fields, status="price_missing" if not matches else "ambiguous_price")
            )
            continue
        rule = matches[0]
        lines.append(
            CostLine(
                **fields,
                status="priced" if measurement.completeness == "final" else "partial",
                currency=rule.currency,
                amount=measurement.quantity * rule.rate / rule.unit_quantity,
                rate=rule.rate,
                unit_quantity=rule.unit_quantity,
                pricing_rule_id=rule.rule_id,
                catalog_version=rule.catalog_version,
                source_url=rule.source_url,
            )
        )
    # A request with no usage remains visible as missing accounting, not free.
    if not lines:
        lines.append(
            CostLine(
                attempt_id=attempt.attempt_id,
                operation_id=attempt.operation_id,
                dimension="unknown",
                quantity=None,
                status="usage_missing",
            )
        )
    return tuple(lines)


class DimensionTotal(AccountingValue):
    dimension: str
    recorded: Quantity | None
    attempts_recorded: int
    attempts_missing: int
    coverage: Literal["complete", "partial", "missing"]
    estimated_attempts: int


class CurrencyTotal(AccountingValue):
    currency: str
    estimated_recorded: Quantity


class AccountingSummary(AccountingValue):
    operation_count: int
    attempt_count: int
    retry_count: int
    usage: tuple[DimensionTotal, ...]
    cost: tuple[CurrencyTotal, ...]
    unpriced_line_count: int
    cost_coverage: Literal["complete", "partial", "missing"]


def summarize_attempts(
    attempts: tuple[AttemptUsage, ...],
    rules: tuple[PricingRule, ...],
    *,
    dimensions: tuple[str, ...] = ("prompt_tokens", "completion_tokens", "total_tokens"),
) -> AccountingSummary:
    """Count every distinct attempt, including failures and interrupted work.

    Duplicate attempt identity is rejected: callers must resolve replay before
    aggregation rather than silently summing repeated evidence.
    """
    identities = [attempt.attempt_id for attempt in attempts]
    if len(identities) != len(set(identities)):
        raise ValueError("Duplicate provider attempt identity")
    operation_attempts = [(attempt.operation_id, attempt.attempt_index) for attempt in attempts]
    if len(operation_attempts) != len(set(operation_attempts)):
        raise ValueError("Duplicate attempt index within an operation")
    totals = []
    for dimension in dimensions:
        measurements = [
            next((m for m in attempt.measurements if m.dimension == dimension), None)
            for attempt in attempts
        ]
        known = [m for m in measurements if m is not None and m.quantity is not None]
        complete = (
            bool(attempts)
            and len(known) == len(attempts)
            and all(m.completeness == "final" for m in known)
        )
        totals.append(
            DimensionTotal(
                dimension=dimension,
                recorded=sum((m.quantity for m in known), Decimal(0)) if known else None,
                attempts_recorded=len(known),
                attempts_missing=len(attempts) - len(known),
                coverage="complete" if complete else "partial" if known else "missing",
                estimated_attempts=sum(m.completeness == "estimated" for m in known),
            )
        )
    lines = [line for attempt in attempts for line in price_attempt(attempt, rules)]
    currencies: dict[str, Decimal] = defaultdict(Decimal)
    for line in lines:
        if line.amount is not None and line.currency is not None:
            currencies[line.currency] += line.amount
    unpriced = sum(line.amount is None for line in lines)
    return AccountingSummary(
        operation_count=len({attempt.operation_id for attempt in attempts}),
        attempt_count=len(attempts),
        retry_count=sum(attempt.attempt_index > 1 for attempt in attempts),
        usage=tuple(totals),
        cost=tuple(
            CurrencyTotal(currency=key, estimated_recorded=value)
            for key, value in sorted(currencies.items())
        ),
        unpriced_line_count=unpriced,
        cost_coverage=(
            "complete"
            if lines and all(line.status == "priced" for line in lines)
            else "partial"
            if currencies
            else "missing"
        ),
    )
