# PLAN-0034 — Callback role routing and backend assignment

Status: Completed (2026-09-29)

## Existing facts

- `check_callback_availability` currently exposes `role` as an unrestricted string in the registered-handler catalog.
- Agent versions contain enabled callback roles and bookable people. The availability API loads that version and resolves people whose configured roles include the requested role.
- The model does not select an employee or calendar. The API embeds the chosen person/calendar in each signed slot; `book_callback` receives that opaque slot ID.
- Availability currently resolves the requested phrase using each bookable person's timezone and fails the entire request when any matching person's calendar is disconnected or its Freebusy query fails.
- RFC-0007 states that the contact timezone owns callback-time interpretation; an unknown timezone requires clarification.

## Scope and runtime behavior

- Build the availability tool's `role` schema from enabled roles in the pinned agent version. Use role keys as a JSON Schema enum and expose configured labels/descriptions as model-readable guidance. Do not expose person names, calendar IDs, or person-selection parameters.
- Omit callback availability from the current node when scheduling is disabled or no enabled role/person pairing is usable. Keep API-side validation authoritative for stale/malicious model arguments.
- Resolve the caller's phrase once in the contact's IANA timezone. Do not substitute an employee/calendar timezone when the contact timezone is missing; return a structured clarification-required error.
- For the selected role, probe eligible enabled people with connected calendars independently. Ignore an unavailable candidate when another calendar can be checked; distinguish partial results, all-calendar failure, and genuine no availability.
- Assign each slot to a person deterministically: earliest absolute start time first, then configured person order for ties. Deduplicate equivalent time intervals and retain the selected person/calendar only inside the signed slot.
- Booking remains synchronous: validate the signed slot and conversation ownership, re-check availability, create the calendar event, persist the callback, and compensate if persistence fails. The model may confirm only a confirmed booking response.

## Contracts, files, and data

- Runtime: `packages/voice_runtime/voice_runtime/contracts/registry.py` and `execution/native.py` construct the per-agent schema without mutating shared handler specs.
- API: `apps/api/voice_api/api/v1/endpoints/calendar.py`, `services/calendar_service.py`, and strict schemas in `apps/api/voice_api/schemas/calendar.py` define errors and partial availability.
- Public response types change for explicit partial-calendar and unavailable-calendar outcomes. Export OpenAPI and regenerate dashboard types; keep frontend calls on generated contracts.
- No database schema change is required. Agent callback config and existing signed slot payload remain the source of role/person/calendar ownership.

## Tests and acceptance

- Serialized schema contains exactly enabled role keys and their labels/descriptions, excludes disabled roles and all person/calendar identifiers, and does not mutate the shared registry schema.
- Cover unknown/disabled role, disabled scheduling, no usable people, unknown contact timezone, connected/disconnected mixtures, per-calendar Freebusy failures, all failures versus no free slots, deterministic assignment/tie/dedup behavior, and timezone conversion.
- Cover stale/tampered/expired slots, cross-contact/version slot use, slot conflict, successful booking, calendar event failure, and persistence compensation.
- Run focused Python tests and Ruff, export OpenAPI, regenerate dashboard types, and run dashboard typecheck/build.
- Manual test with multiple people for one role: the agent chooses a configured role, never chooses a person, offers backend-assigned slots, and confirms only after a successful booking result.

## Non-goals

- No asynchronous tool-result lifecycle, fixed acknowledgement phrase, new wait mode, or unsolicited agent speech.
- No person preference input from the model, calendar UI redesign, or changes to automatic callback dispatch.
- No changes to demo/seed scripts or legacy compatibility modes.

## Completion record

- Runtime function schemas now expose only enabled roles that have at least one enabled bookable person; role descriptions are visible to the model and person/calendar identifiers are not.
- Availability is interpreted once in the contact timezone. Disconnected and failing calendars are isolated; partial, unavailable, invalid-timeframe, and no-availability outcomes are distinct. Slot assignment is earliest-time-first with configured-order tie breaking and interval deduplication.
- Booking rejects a signed slot if the contact timezone changed after availability was checked.
- Verification: focused callback/runtime tests — 31 passed; Ruff passed; OpenAPI export and dashboard type generation succeeded; dashboard production build succeeded. The build reports the existing >500 kB chunk advisory.
- Live Google OAuth/Freebusy/calendar event behavior was not exercised; it still requires connected test credentials.
- Follow-on async tool outcomes and wait-setting removal remain planned separately in PLAN-0035 and PLAN-0036.
