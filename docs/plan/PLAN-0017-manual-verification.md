# PLAN-0017 · Final manual verification

Status: ready

This checklist verifies the completed Plans 0008–0016 through the API,
dashboard, database, and one real browser or SIM7600 call. Use a development
database and development provider keys only.

## Environment setup

1. Start PostgreSQL with Docker Compose. The default database port is `55432`.
2. Apply migrations with `uv run alembic upgrade head`.
3. Start the API with:
   `uv run uvicorn voice_api.main:app --reload --port 8000`.
4. Start the dashboard with `cd apps/dashboard; npm run dev`.
5. Enter the operator token in the dashboard connection screen.
6. Confirm provider credentials are present only in the API/runtime environment.
7. Register or verify the SIM7600 endpoint if testing a phone call.
8. On the Endpoints page, click **Test connection**. Confirm Online, SIM readiness,
   voice/data registration, operator/radio, and RSSI appear. Confirm it checks
   every five seconds while connected and stops after disconnect; click again
   to begin another check cycle.
8. Confirm the API, runtime worker, and database use the same database URL and
   provider environment.

## Database and tool checks

1. Run the tool validation/cleanup report.
2. Verify one current agent and its active version; current development agent
   versions should begin at version 1 after the authorized cleanup.
3. Confirm every active binding resolves to a published tool version and every
   registered handler exists in the runtime registry.
4. Open a registered tool and confirm the card shows handler/provider and does
   not show HTTP endpoint/method fields.
5. Open an HTTP tool and confirm endpoint and method are shown.
6. Clone a published tool, edit the draft, validate it, publish it, and bind it
   to an agent draft.

## WhatsApp checks

1. Open the WhatsApp integration and upload media.
2. Import an existing Meta media ID and verify it.
3. Edit local media metadata and confirm the provider ID remains unchanged.
4. Configure a WhatsApp template tool and select media from the media catalog.
5. Confirm the saved tool stores the local media record ID, not only the Meta
   provider ID.
6. Execute a test call with valid credentials and confirm the provider message
   ID and media evidence are visible.

## Classifier and context checks

1. Configure entry and exit classifier nodes on an agent draft.
2. Save, publish, activate, and run a call through both nodes.
3. Confirm classifier spans appear for entry and exit phases.
4. Confirm each classifier result appears in the next LLM input/context.
5. In the waterfall, verify `Result recorded`, `Added to context`, and
   `Consumed by LLM` are distinct visible states.
6. Trigger a classifier provider failure and confirm the call continues with a
   diagnostic instead of silently dropping the result.

## Barge-in and interruption checks

1. Let the agent speak and interrupt it mid-sentence.
2. Confirm caller speech, STT, `InterruptionFrame`, TTS interruption, and
   playback interruption appear in the waterfall.
3. Confirm canceled LLM/tool work is recorded when cancellation occurs.
4. Confirm generated assistant text and spoken TTS text are distinguishable.
5. Confirm caller speech and its STT span are grouped under one turn while
   remaining separate measurements.

## Failure-state checks

Exercise each condition and inspect the run diagnostic:

- user hangup
- remote hangup
- browser disconnect
- missing COM port
- modem startup timeout
- low RSSI
- network unregistration
- invalid provider key
- provider throttling
- provider quota exhaustion
- TTS failure
- evidence delivery failure

Each must show a specific category/source/message rather than only
`pipeline error`. Verify that low RSSI is reported as an observation unless
the modem provides a causal disconnect reason.

## Model/provider checks

1. In an editable agent draft, open Models.
2. Change STT provider/model where the catalog allows it.
3. Change TTS provider/model/voice/language.
4. Save, publish, activate, and start a call.
5. Verify the resolved run snapshot contains the selected values.
6. Verify provider evidence contains the selected providers/models.
7. Confirm unsupported or unavailable providers and fields are visibly marked.
8. Confirm no credential value appears in API responses, OpenAPI, logs,
   evidence, or browser state.

## Final call and dashboard acceptance

For a browser final call:

1. Open the dashboard Test Agent modal and select the intended agent/version.
2. Start the browser call and confirm the run resolves that exact version.
3. Exercise one normal response, one tool call, one classifier boundary, and
   one caller barge-in.
4. End the call from the browser and inspect the run detail, transcript,
   waterfall, diagnostics, and tool result context states.

For a SIM7600 final call, use the same sequence after verifying the modem
endpoint and call state. Compare modem termination state, signal metadata, and
provider diagnostics in the run evidence.

The final acceptance result is complete only when the selected version, runtime
provider values, tool result context delivery, classifier execution,
   interruptions, termination cause, and provider errors are all visible and
   internally consistent. Provider account usage/credit reporting is not part
   of the dashboard because the configured providers do not expose it through
   supported APIs.
