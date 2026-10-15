# Issues and regression coverage

Reviewed October 15, 2026 against `42f7b10`. These records summarize incidents from development and the code/tests now present. Implemented does not mean newly verified on production or hardware. Private evidence stays outside Git.

## Implemented fixes

| Issue | Status |
|---|---|
| [ISSUE-001: Dashboard stop became a pipeline failure](ISSUE-001-operator-stop.md) | Implemented; hardware acceptance remains separate |
| [ISSUE-002: Repeated tool notifications caused conflicting evidence](ISSUE-002-duplicate-tool-context.md) | Implemented |
| [ISSUE-003: Interrupted held speech could resume after voicemail detection](ISSUE-003-stale-greeting.md) | Implemented for the gate race |
| [ISSUE-004: Evidence failure hid release and left a modem occupied](ISSUE-004-cleanup-and-leases.md) | Implemented; recovery requires hardware proof |
| [ISSUE-005: Dial acceptance and a single idle reading were insufficient](ISSUE-005-modem-setup-release.md) | Implemented |
| [ISSUE-006: Call release reason was unknown or over-attributed](ISSUE-006-call-outcomes.md) | Implemented evidence model; some causes remain unknown |
| [ISSUE-007: Providers rejected missing initial user input and cloning failed](ISSUE-007-initial-task-and-cloning.md) | Implemented |
| [ISSUE-008: Fallback changed role handling or lost current node instructions](ISSUE-008-llm-fallback.md) | Implemented |
| [ISSUE-009: Follow-up omitted a required link or invented booking confirmation](ISSUE-009-whatsapp-composer.md) | Implemented validation and booking provenance |
| [ISSUE-010: Terminal actions and context changes caused extra speech or failures](ISSUE-010-closing-and-context.md) | Implemented mechanics; prompt quality remains separate |
| [ISSUE-011: Contact variables were inconsistent and referral facts had no review lifecycle](ISSUE-011-contacts-and-referrals.md) | Implemented |
| [ISSUE-012: Legacy per-frame speech recognition did not produce final transcripts](ISSUE-012-sarvam-stt.md) | Implemented adapter change; provider acceptance is separate |

## Open investigations

| Issue | Established limit and next evidence needed |
|---|---|
| [OPEN-001: Sarvam playback text](open-investigations.md#open-001-sarvam-playback-text) | No exact spoken-word alignment; do not claim PCM character ratios are exact |
| [OPEN-002: Serial response ownership](open-investigations.md#open-002-serial-response-ownership) | Reproduce NO CARRIER plus trailing OK with the real reader; commit regression before claiming fixed |
| [OPEN-003: Conversation quality](open-investigations.md#open-003-conversation-quality) | Over-discovery, internal narration and routing need candidate-execution evals |
| [OPEN-004: Production transfer](open-investigations.md#open-004-production-transfer) | Prepared import and selected artifacts are not confirmed uploads |

## Change and test navigation

The current focused verification is **170 passed, 2 failed**. See
[OPEN-005](open-investigations.md#open-005-existing-test-expectations-conflict-with-current-policies)
before interpreting the linked tests as passing coverage.

- [Change history](change-history.md) lists every non-merge commit in this checkout and its changed areas.
- [Regression guide](../testing/regression-tests.md) explains test design and layer selection.
- [Verification record](verification.md) records only checks actually rerun for this documentation update.
- [Architecture index](../architecture/decision-index.md) distinguishes current decisions from historical proposals.
