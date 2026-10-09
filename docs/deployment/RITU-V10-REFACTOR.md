# Ritu v10 refactor · 2026-10-06

Saved directly to **localhost:55432/voice**, Ritu v10 draft revision **4 → 5**.
Version ID: `edb25989-7d67-4156-b55f-842c2a60cb0c`.
The saved configuration equals the validated proposal. Active v8 revision 9 and v7/v9 remain unchanged. No hosted database writes, publication, activation, provider actions, calls or messages.

## Nodes and prompts

Seven existing node IDs retained; `fit_clarification` removed with all references. No new flow nodes.

| Node | Result |
| --- | --- |
| Greeting | Establish contact/time only; availability to Discovery, busy to Sales Callback, refusal to Closing. |
| Discovery | Requirement, underlying problem and intent in usually 2-4 responses; no pitch; busy bypasses classification. Later genuine projects generally warm. |
| Hot | Targeted pitch, optional existing human-confirmed 15% campaign; book Technical Solutions directly; consented WhatsApp after successful booking. |
| Warm | Answer actual concerns without restarting discovery; direct Technical Solutions booking or requested generic WhatsApp after permission. |
| Cold | One low-pressure future-relevance check; no aggressive pitch. |
| Callback Scheduling | Sales-conversation continuation only; factual booking reason; no automatic WhatsApp. |
| Closing | Brief truthful farewell; no new CTA, pitch, booking or send. |

Global-plus-node composition now actually supplies the shared prompt. Existing Telugu/Hindi/Marathi/English speaking style retained: native script, natural code-mixing, respectful forms, feminine self-reference, no grammar correction, no repeated stock acknowledgements, concise complete speech and honest AI disclosure. Shared identity/name/language/safety clauses moved out of duplicated node prompts. Names and languages are recorded only when changed. Global prompt contains no sales-stage or booking sequence.

First/last-name contact variables retained and used; compatibility name and existing `recepient_name`, `preferred_language`, `whatsapp_message_sent` facts preserved exactly. Added caller first/last-name facts and separate referral full/first/last name, phone, email and context facts through existing generated `record_*` tools. Referral capture can happen mid-conversation; collect one missing detail at a time and preserve role, reason, timing/timezone, permission and restrictions. Recording these facts does not create another contact row or authorize calls/messages to the referred person. Caller identity/destination stays separate.

All six tool IDs, versions, schemas and relational bindings unchanged. Availability/booking/request tools exposed inside Hot/Warm. Existing callback calendar role is reused because it is the only configured calendar pool; reasons distinguish sales continuation from Technical Solutions scoping. Invalid classifier output has no valid-classification fallback; stay in Discovery, clarify or close rather than silently route Hot. Fixed classifier schema/questions preserved.

## All 27 routing combinations

Each column represents one exact tone suffix of `temperature|fit|tone`.

| Temperature | Fit | receptive | hesitant | resistant |
| --- | --- | --- | --- | --- |
| hot | strong_fit | hot_followup | hot_followup | warm_nurture |
| hot | possible_fit | hot_followup | warm_nurture | warm_nurture |
| hot | poor_fit | cold_check | cold_check | cold_check |
| warm | strong_fit | warm_nurture | warm_nurture | cold_check |
| warm | possible_fit | warm_nurture | warm_nurture | cold_check |
| warm | poor_fit | cold_check | cold_check | cold_check |
| cold | strong_fit | cold_check | cold_check | cold_check |
| cold | possible_fit | cold_check | cold_check | cold_check |
| cold | poor_fit | cold_check | cold_check | cold_check |

## WhatsApp and runtime

Enabled the existing composer using its configured Groq model and existing compatible LLM credential reference. Prompt now summarizes confirmed requirement/next step, preserves native language/code-mixing, requires the voice AI demo URL, prohibits invented product demos/proposals/discount eligibility, and includes exact confirmed booking day/local time. Earlier generic sends do not prevent a distinct appointment confirmation; duplicate confirmations still prohibited by tool history.

Small local runtime change supplies sanitized final `book_callback` result payloads and original booking reasons from existing evidence to the composer. Failed and uncertain results are retained as evidence, not successes; availability results are excluded. No schema migration or new external tool contract. Existing template/media/provider configuration preserved.

Runtime source changes are local. A runtime process already running old code needs reload/restart before testing the new composer evidence path. Existing conversations retain frozen snapshots; start a fresh v10 draft test.

## Validation and limits

35 scoped composer/native-node tests pass, including exact structured appointment evidence, confirmed/uncertain result handling, invalid composer output and provider-failure no-send behavior. Scoped Ruff check/format passes. DB contract/calendar/binding/resolution validations pass; saved revision and active-version pointer re-read successfully. Preservation checks cover tool bindings, classifier, callback calendars, speech/LLM/VAD settings and old fact slots.

All requested path wiring is present: hot/warm conversion, cold close, greeting/discovery busy bypass, declined booking close, permission-only warm information, returned-slot acceptance, booking failure/uncertainty, stop handling, shared-language retention, later-timing guidance and all 27 destinations. These are graph/prompt and unit validations, not a claim of 15 live conversational acceptance tests. No real calendar/WhatsApp/provider/modem actions were run. Model compliance with timing classification, consent, refusal, multilingual transitions and slot-selection rules needs a fresh end-to-end test call/chat.

Assumptions: v10 is the requested local draft; current campaign wording is retained conditionally without verifying commercial eligibility; existing single calendar role serves both factual booking purposes. Referred people are recorded as conversation facts as requested, not automatically added to the contact directory.

## 2026-10-07 follow-up: compact contact capture (revision 6)

Saved local Ritu v10 draft revision 5 -> 6 at localhost:55432/voice. Removed `recepient_name` and all six `referred_contact_*` fact slots and prompt references. Remaining facts: caller_first_name, caller_last_name, preferred_language, whatsapp_message_sent. Caller name corrections write only changed supplied parts; no full-name write or name writes merely for greeting.

Bound the existing published `save_referral` tool `aca15a9f-31d1-4102-a00d-1486c3cb3636` to all six non-closing nodes using existing binding synchronization. One combined collection question asks for the referred person's name, best phone/email and any useful context. One save_referral invocation saves supplied first/last name, phone, email, organization, role and context; no separate referral fact writes. Existing typed phone/email parameters remain separate within that one call, avoiding unnecessary comma parsing without additional tool calls. Unknown details remain absent; incomplete name-only referrals are valid.

Read supplied phone/email back once and await explicit confirmation before saving. Corrected details require a corrected readback. Use contact_details_confirmed=true only after confirmation; the existing backend rejects unconfirmed phone/email saves. Different WhatsApp destination numbers must also be read back and explicitly confirmed for the requested message before passing `to`. Referral numbers are not automatic WhatsApp destinations. A confirmed readback proves transcription accuracy, not third-party outreach consent.

Current draft re-read after commit equals the validated configuration. Contract, calendar, binding and resolved snapshot checks pass; two existing referral contract tests and scoped Ruff pass. Existing composer, all classifier routes, booking configuration, multilingual/code-mixing clauses and speech/LLM settings preserved. Published/active versions unchanged. No schema/runtime changes, hosted writes, referral records, calls or messages performed. Live conversational adherence remains unverified.

## 2026-10-07 prompt compaction (revision 7)

Local Ritu v10 draft revision 6 -> 7: compacted shared global behavior, all seven node role/task prompts, composer and summarizer. Total authored text reduced from 4,464 to 1,460 tokens using cl100k_base as a counting proxy (the configured Qwen tokenizer may differ). Global 339; Greeting 73; Discovery 106; Hot 270; Warm 276; Cold 57; Callback 138; Closing 27; composer/summary account for the rest. A single active-node combination is at most 615 authored tokens before tool schemas, transcript, rendered variable values and runtime additions. Classifier's fixed contract/questions remain unchanged and are not included in this authored prompt count.

Removed repeated referral instructions from each node; global shared capture rules retain the single collection question, confirmed readback and one save_referral invocation. Kept native-script/code-mixing, respectful forms/feminine self-reference, identity changes only, brief speech, confirmation of different WhatsApp numbers, immutable classification routing, busy bypass, direct Hot/Warm booking, returned-slot acceptance, uncertainty/no-retry rules, generic-send deduplication versus new booking confirmations, voice AI demo identity, opt-out/closing restrictions and verified-action-only claims.

No tool definitions, bindings, facts, routes, speech/model settings or published/active versions changed. Agent contract/binding/resolution validations and scoped updater Ruff passed; saved row re-read equals validated proposal. Tokenizer used through temporary uv --with dependency; project dependencies/lockfile unchanged. Live model behavior remains unverified.

## 2026-10-07 compaction reverted (revision 8)

User clarified the budget is 1,500 tokens per node, not across all prompts. Restored the exact pre-compaction revision 6 configuration as local draft revision 8, verified by database re-read and full configuration equality. The larger global/node/composer/summary prompts are restored. Single save_referral binding, removal of redundant recipient/referral name facts, caller first/last-name facts and phone/email/alternate WhatsApp confirmation rules remain. Agent contract, binding and resolution validation passed; active published version unchanged. Revision 7 compaction is superseded. No live calls/messages or hosted writes.
