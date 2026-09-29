"""Accounting invariants: missing differs from zero and money never loses provenance."""

from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
from pydantic import ValidationError
from voice_runtime.execution.accounting import (
    AttemptUsage,
    PricingRule,
    UsageMeasurement,
    price_attempt,
    summarize_attempts,
)

NOW = datetime(2026, 9, 28, tzinfo=UTC)


def measurement(dimension="input_token", quantity="100", **kwargs):
    return UsageMeasurement(
        dimension=dimension,
        quantity=quantity,
        source="provider_reported",
        completeness="final",
        **kwargs,
    )


def attempt(measurements=(), **kwargs):
    return AttemptUsage(
        attempt_id="request-1",
        operation_id="span-1",
        provider="example",
        model="model-a",
        purpose="foreground",
        started_at=NOW,
        status="completed",
        measurements=measurements,
        **kwargs,
    )


def rule(**kwargs):
    values = {
        "rule_id": "price-a",
        "catalog_version": "catalog-a",
        "provider": "example",
        "model": "model-a",
        "dimension": "input_token",
        "effective_from": NOW,
        "accessed_at": NOW,
        "source_url": "https://example.com/pricing",
        "currency": "USD",
        "unit_quantity": "1000000",
        "rate": "0.15",
    }
    return PricingRule(**{**values, **kwargs})


def test_pricing_uses_decimal_and_pins_source_version_and_rate():
    line = price_attempt(attempt((measurement(),)), (rule(),))[0]
    assert line.amount == Decimal("0.000015")
    assert line.currency == "USD"
    assert line.catalog_version == "catalog-a"
    assert line.pricing_rule_id == "price-a"
    assert line.source_url == "https://example.com/pricing"
    assert line.status == "priced"
    assert line.operation_id == "span-1"


def test_unmeasured_attempt_is_missing_not_free():
    line = price_attempt(attempt(), (rule(),))[0]
    assert line.amount is None
    assert line.status == "usage_missing"
    summary = summarize_attempts((attempt(),), (rule(),))
    assert summary.cost == ()
    assert summary.usage[0].recorded is None
    assert summary.cost_coverage == "missing"


def test_measured_zero_is_preserved():
    data = attempt((measurement(quantity="0"),))
    assert price_attempt(data, (rule(),))[0].amount == Decimal(0)
    summary = summarize_attempts((data,), (rule(),), dimensions=("input_token",))
    assert summary.usage[0].recorded == 0
    assert summary.usage[0].coverage == "complete"
    assert summary.cost[0].estimated_recorded == 0
    assert summary.cost_coverage == "complete"


def test_missing_rule_does_not_hide_measured_usage():
    data = attempt((measurement(),))
    assert price_attempt(data, ())[0].status == "price_missing"
    summary = summarize_attempts((data,), (), dimensions=("input_token",))
    assert summary.usage[0].recorded == 100
    assert summary.unpriced_line_count == 1


def test_overlapping_rules_fail_as_ambiguous_instead_of_picking_first():
    line = price_attempt(attempt((measurement(),)), (rule(), rule(rule_id="price-b")))[0]
    assert line.status == "ambiguous_price"
    assert line.amount is None


def test_pricing_effective_dates_are_half_open_and_historical_lines_are_immutable():
    boundary = NOW + timedelta(days=1)
    old = rule(effective_to=boundary)
    new = rule(rule_id="price-b", catalog_version="catalog-b", rate="0.30", effective_from=boundary)
    data = attempt((measurement(),))
    original = price_attempt(data, (old, new))[0]
    later = data.model_copy(update={"started_at": boundary})
    assert price_attempt(later, (old, new))[0].catalog_version == "catalog-b"
    assert price_attempt(later, (old, new))[0].amount == original.amount * 2
    assert original.catalog_version == "catalog-a"
    with pytest.raises(ValidationError):
        original.rate = Decimal("9")


def test_service_tier_model_and_family_must_match_explicitly():
    data = attempt((measurement(),))
    for incompatible in (
        rule(service_tier="batch"),
        rule(model="another"),
        rule(family="tts"),
        rule(provider="another"),
        rule(effective_from=NOW + timedelta(days=1)),
    ):
        assert price_attempt(data, (incompatible,))[0].status == "price_missing"


def test_currencies_are_aggregated_separately():
    first = attempt((measurement(),))
    second = first.model_copy(
        update={"attempt_id": "request-2", "operation_id": "span-2", "model": "model-b"}
    )
    summary = summarize_attempts(
        (first, second), (rule(), rule(model="model-b", currency="INR", rate="10"))
    )
    assert [(entry.currency, entry.estimated_recorded) for entry in summary.cost] == [
        ("INR", Decimal("0.001")),
        ("USD", Decimal("0.000015")),
    ]


def test_retries_and_interrupted_attempts_are_all_counted():
    first = attempt((measurement(),))
    retry = first.model_copy(
        update={"attempt_id": "request-2", "attempt_index": 2, "status": "interrupted"}
    )
    summary = summarize_attempts((first, retry), (rule(),), dimensions=("input_token",))
    assert summary.operation_count == 1
    assert summary.attempt_count == 2
    assert summary.retry_count == 1
    assert summary.usage[0].recorded == 200
    assert summary.cost[0].estimated_recorded == Decimal("0.000030")


def test_partial_usage_totals_show_missing_attempt_count():
    measured = attempt((measurement(),))
    missing = measured.model_copy(
        update={"attempt_id": "request-2", "operation_id": "span-2", "measurements": ()}
    )
    summary = summarize_attempts((measured, missing), (rule(),), dimensions=("input_token",))
    assert summary.usage[0].recorded == 100
    assert summary.usage[0].attempts_recorded == 1
    assert summary.usage[0].attempts_missing == 1
    assert summary.usage[0].coverage == "partial"
    assert summary.cost_coverage == "partial"


def test_framework_estimates_do_not_claim_complete_coverage():
    estimate = UsageMeasurement(
        dimension="input_token",
        quantity="100",
        source="framework_estimated",
        completeness="estimated",
    )
    data = attempt((estimate,))
    summary = summarize_attempts((data,), (rule(),), dimensions=("input_token",))
    assert summary.usage[0].estimated_attempts == 1
    assert summary.usage[0].coverage == "partial"
    assert summary.cost_coverage == "partial"
    assert price_attempt(data, (rule(),))[0].status == "partial"


def test_cached_tokens_are_priced_as_disjoint_quantities_not_gross_plus_cache():
    data = attempt(
        (
            measurement("prompt_tokens", "1000", billable=False),
            measurement("input_token", "600"),
            measurement("cached_input_token", "400"),
        )
    )
    lines = price_attempt(data, (rule(rate="1"), rule(dimension="cached_input_token", rate="0.5")))
    assert len(lines) == 2
    assert sum(line.amount for line in lines) == Decimal("0.0008")


def test_reasoning_telemetry_is_not_charged_twice_when_output_already_includes_it():
    data = attempt(
        (measurement("output_token", "100"), measurement("reasoning_tokens", "40", billable=False))
    )
    lines = price_attempt(data, (rule(dimension="output_token", rate="2"),))
    assert len(lines) == 1
    assert lines[0].amount == Decimal("0.0002")


def test_non_token_units_follow_the_same_cost_calculation():
    data = attempt((measurement("audio_second", "90"),), family="tts")
    line = price_attempt(
        data, (rule(family="tts", dimension="audio_second", unit_quantity="60", rate="0.1"),)
    )[0]
    assert line.amount == Decimal("0.15")


def test_telemetry_only_attempt_has_unknown_cost_not_zero():
    data = attempt((measurement("prompt_tokens", "100", billable=False),))
    assert price_attempt(data, (rule(),))[0].status == "usage_missing"


@pytest.mark.parametrize("quantity", ["-1", "NaN", "Infinity"])
def test_invalid_quantities_are_rejected(quantity):
    with pytest.raises(ValidationError):
        measurement(quantity=quantity)


def test_naive_pricing_timestamps_and_empty_effective_intervals_are_rejected():
    with pytest.raises(ValidationError):
        rule(effective_from=datetime(2026, 9, 28))
    with pytest.raises(ValidationError):
        rule(effective_to=NOW)


def test_duplicate_attempt_identity_or_index_is_rejected():
    data = attempt((measurement(),))
    with pytest.raises(ValueError, match="Duplicate provider attempt"):
        summarize_attempts((data, data), (rule(),))
    second = data.model_copy(update={"attempt_id": "request-2"})
    with pytest.raises(ValueError, match="Duplicate attempt index"):
        summarize_attempts((data, second), (rule(),))


def test_duplicate_measurement_dimension_is_rejected():
    with pytest.raises(ValidationError):
        attempt((measurement(), measurement()))


def test_missing_or_estimated_measurements_cannot_be_labeled_final():
    with pytest.raises(ValidationError):
        UsageMeasurement(dimension="input_token", completeness="final")
    with pytest.raises(ValidationError):
        UsageMeasurement(
            dimension="input_token", quantity=1, source="local_estimate", completeness="final"
        )


def test_empty_run_has_unknown_coverage():
    summary = summarize_attempts((), ())
    assert summary.operation_count == 0
    assert summary.cost_coverage == "missing"
    assert summary.usage[0].recorded is None


@pytest.mark.parametrize("purpose", ["foreground", "classifier", "summarizer", "background"])
def test_all_operation_purposes_participate_in_accounting(purpose):
    data = attempt((measurement(),)).model_copy(update={"purpose": purpose})
    summary = summarize_attempts((data,), (rule(),), dimensions=("input_token",))
    assert summary.usage[0].recorded == 100
    assert summary.cost[0].estimated_recorded == Decimal("0.000015")
