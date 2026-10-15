# ISSUE-009 Follow-up omitted a required link or invented booking confirmation

Status: Implemented validation and booking provenance. Reviewed October 15, 2026.

## Observed problem

A fluent message can omit a mandatory demo URL or repeat an unconfirmed appointment from conversation text. Template greetings/sign-offs can also be duplicated by an overly broad composer prompt.

## Implemented behavior

Separate tool selection from composition. Validate exact dynamic fields, nonempty length-bounded strings and configured URLs before send. Supply finalized dialogue and separate structured booking results; only confirmed booking evidence proves an appointment.

## Source

- [packages/voice_runtime/voice_runtime/execution/whatsapp_composer.py](../../packages/voice_runtime/voice_runtime/execution/whatsapp_composer.py)
- [packages/voice_runtime/voice_runtime/execution/exchange.py](../../packages/voice_runtime/voice_runtime/execution/exchange.py)

## Regression coverage

- [test_whatsapp_composer.py](../../tests/unit/test_whatsapp_composer.py) — `test_composer_rejects_missing_required_link_and_wrong_fields`.
- [test_whatsapp_composer.py](../../tests/unit/test_whatsapp_composer.py) — `test_failed_composition_has_diagnostic_and_never_sends`.
- [test_whatsapp_composer.py](../../tests/unit/test_whatsapp_composer.py) — `test_composer_receives_structured_booking_evidence`.
- [test_whatsapp_composer.py](../../tests/unit/test_whatsapp_composer.py) — `test_main_agent_only_sees_optional_recipient`.

## Verification limits

A successful guard test does not prove an old send used the same saved template prompt or required-URL configuration. Inspect the pinned run snapshot.

These links identify existing coverage. See [verification record](verification.md) for commands rerun during this review. Follow the [regression guide](../testing/regression-tests.md) before changing behavior.
