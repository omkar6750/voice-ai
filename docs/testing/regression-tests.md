# Writing regression tests from real failures

Regression tests reproduce a failure's cause and assert the corrected behavior.
They should explain why the fix works and fail if that fix is removed. The
[issue catalog](../issues/README.md) links the problems encountered in this project
to their existing tests. These are engineering regressions, not a completed
conversation benchmark or proof of live provider reliability.

The October 15 focused rerun found two existing expectation mismatches. The linked
fallback context test fails before reaching its context assertions; a terminal
shutdown-failure test expects a different completion status. See
[OPEN-005](../issues/open-investigations.md#open-005-existing-test-expectations-conflict-with-current-policies)
and the [verification record](../issues/verification.md). A test link alone does not
claim that test passed.

## Workflow

1. **Record the observation.** Capture the symptom, expected outcome, affected layer
   and evidence references in `docs/issues/`. Keep private run IDs and raw material
   in ignored local investigation files when not needed for a public explanation.
2. **Establish cause.** Separate the provider error, model behavior, pipeline failure,
   persistence rejection and cleanup outcome. A red badge alone is not a cause.
3. **Minimize the reproduction.** Use the real wrapper/processor where the bug lived.
   Replace only external serial, provider, clock, network and database boundaries.
4. **Assert the broken invariant.** Test call order, frame delivery, identity, state,
   absence of duplicate side effects or preserved ownership. Avoid asserting private
   implementation details that merely restate the code.
5. **Demonstrate the regression.** When practical, run the new test against the old
   implementation or temporarily revert only the fix. Record this evidence; do not
   say a red/green cycle occurred if it was not run.
6. **Fix narrowly and run neighboring cases.** Include the failure path and successful
   path. Async shutdown changes need cancellation/race coverage, not broad sleeps.
7. **Update the issue record.** List exact test selectors, code, commands run, result,
   skipped gates and remaining hardware/provider acceptance. Link an ADR only when
   a settled architectural decision changed.

## Examples already in the repository

| Real problem | Existing test and the invariant it protects |
|---|---|
| Dashboard End call became PCM write failure | `test_sim7600_release_verification.py::test_pipeline_stops_before_hangup_disables_pcm`: pipeline workers stop before modem hangup/audio disable |
| Pipeline shutdown failure skipped physical cleanup | Same file, `test_failed_pipeline_shutdown_still_hangs_up_and_closes_modem`: failure still attempts hangup and closes ports |
| Duplicate tool context delivery produced conflicting evidence | `test_native_evidence.py::test_repeated_context_notifications_keep_one_delivery_and_consumption`: one immutable delivery per result |
| Voicemail branch observed conversation tool callbacks | `test_voicemail_context_isolation.py::test_conversation_tool_result_cannot_update_voicemail_context`: isolated assistant context |
| Interrupted greeting resumed from held speech | `test_voicemail_tts_gate.py::test_interruption_during_release_stops_remaining_old_frames`: interruption invalidates in-progress gate release |
| Old published agent could not be cloned | `test_initial_task_message.py::test_clone_published_version_without_opening_task_preserves_draft`: clone remains editable; new writes stay strict |
| Fallback model lost current instructions | `test_provider_failover.py::test_groq_fallback_preserves_current_node_instruction_and_user_task`: both services see current semantic context |
| WhatsApp composer omitted required URL | `test_whatsapp_composer.py::test_composer_rejects_missing_required_link_and_wrong_fields`: validation fails before send |
| Endpoint looked occupied after execution ended | `test_modem_recovery.py::test_recovery_releases_stopped_owner_only_after_hardware_proof`: recovery requires proof, not a UI reset |

All filenames above are under [`tests/unit`](../../tests/unit). Each issue file
contains clickable source links. Do not interpret a nearby test as coverage for a
different unresolved failure, such as precise TTS playback truncation.

## Choosing the test layer

Organization provisioning is covered by
[`test_organization_seed.py`](../../tests/integration/test_organization_seed.py).
It uses an isolated migrated PostgreSQL database and creates its own organizations,
including when no legacy tenant exists. It checks that seeding works without
production provider keys, survives registration retries without duplicates, preserves
existing v1 catalogs and settings, and creates independently linked run evidence
for each organization. It also checks that the starter remains an inactive draft,
production publication rejects missing credentials, and draft activation is blocked.
The corresponding
[fixture tests](../../tests/unit/test_organization_demo.py) check private-field
exclusion and the starter's terminating graph without executing providers.

| Layer | Use it for | Replace |
|---|---|---|
| Pure contract/function | Prompt parsing, role normalization, schemas, required URLs | Nothing external |
| Pipecat wrapper/processor | Duplicate notifications, tool results, frame gates and end ordering | Provider/network and owning worker boundary |
| Service/API | Revision conflicts, scope, stop requests and cleanup synchronization | Explicit service boundaries or isolated DB |
| Database integration | Constraints, transactions, tenant guards, migrations and replay conflicts | Dedicated migrated PostgreSQL, never production |
| Dashboard | Editor references, displayed status and operator actions | Controlled API/state fixtures |
| Manual hardware/provider acceptance | Real PCM, serial disconnects, carrier timing and provider formats | Actual approved hardware/credentials; keep outside offline suite |

Use `asyncio.Event`, a controlled queue, mocked monotonic clock or recorded fake
responses to drive races. Avoid timing-sensitive sleeps as a substitute for causality.
External tool writes should use fakes that record intended calls. Offline tests must
not send WhatsApp messages, create Calendar bookings, dial contacts or query production.

## Run the narrow test first

From the repository root:

```powershell
uv run pytest tests/unit/test_sim7600_release_verification.py::test_pipeline_stops_before_hangup_disables_pcm
uv run pytest tests/unit/test_voicemail_context_isolation.py tests/unit/test_voicemail_tts_gate.py tests/unit/test_end_call_ordering.py
uv run ruff check packages/voice_runtime/voice_runtime/telephony/driver.py tests/unit/test_sim7600_release_verification.py
```

If a pytest temporary directory is occupied by another process, use a unique
`--basetemp=data/test-temp-<investigation>` directory. Do not delete another test run's
directory or rerun against a production database to bypass an unavailable local one.

Integration tests use `VOICE_TEST_DATABASE_URL` and the guards in their fixtures.
Some tests skip when it is missing. Report those skips rather than treating them as
passing constraint or migration checks. Use frontend commands from `apps/dashboard`:
`npm run test:prompts`, `npm run test:tools` and `npm run build`.

## Coverage that still needs a separate evaluation suite

Saved transcripts expose over-discovery, repeated acknowledgments, internal tool
narration and incorrect routing. Evaluate those against a candidate configuration
using scripted caller turns and controlled tool responses. Scoring an old transcript
does not exercise a new prompt. Exact wording is usually not the right assertion.

A future dataset should version its schema, cases, expected actions and rubric.
Deterministic correctness checks and evidence-backed conversational judging should
remain separate. No such dataset or judge implementation is claimed by this guide.

## Issue record checklist

- Symptom and established cause are separate.
- Source and exact test functions exist.
- Implemented fix and proposed follow-up are labeled separately.
- A fixture contains no real keys, contact details, raw audio or private prompts.
- Recorded verification says when and what ran, with skips and limits.
- Hardware/provider acceptance is not inferred from fakes.
