# Ritu: focused local agent

Active local version: **5** (`6c937262-e460-49a4-811c-0f766edc0e7e`).
Agent name: **Ritu**. Company: **Neotribe Software Studio**.

Based on main database Elevated Box v15. Main was read only; old local drafts and published versions remain available. This configuration has not been deployed.

## Stage responsibilities

| Node | Responsibility |
| --- | --- |
| greeting | Introduce Ritu, establish who answered, explain enquiry/source and ask permission. No pricing or offer. |
| discovery_and_qualify | Follow the requirement naturally; explain relevant pricing, milestones, demos and value. Once need and intent are sufficiently clear, call `classify_lead` once. |
| hot_followup | Ask permission for WhatsApp, send only with consent, explain the qualified-lead 15% offer, then offer a 15-minute technical callback. |
| warm_nurture | Address one real concern; agree a low-pressure, consented next step. |
| cold_check | Check whether follow-up is wanted. Inferred cold is not an opt-out. |
| fit_clarification | Clarify one potential service mismatch without inventing capabilities. |
| callback_scheduling | Preserve stated time, retrieve actual availability, obtain acceptance and book a returned slot. |
| closing | Brief truthful farewell; no new message or booking writes. End after output. |

Every node uses the shared identity, language and action-safety rules plus its own stage instructions. Append retains answers; the current stage replaces previous objectives. Task messages are short system instructions, not fabricated caller messages.

## Fixed classification

No entry/exit/exchange-based classification. Only discovery exposes the classification tool. Its result controls the transition; no generic `change_node` tool is used.

The three questions have three answers each: **27 combinations**. All combinations are explicitly configured using `classification_key`:

- Poor fit: fit clarification.
- Hot + strong fit + receptive: hot follow-up.
- Other cold results: cold check.
- Remaining valid combinations: warm nurture.
- Invalid/failed result: stay; clarify or offer human help without inventing a label.

Explicit refusal or a callback request bypasses classification immediately.

## Knowledge and tools

Six main Northstar reference chunks were imported into a separate local KB, with caller-facing branding changed to Neotribe. They are retrieved on demand with a short English keyword query, up to two chunks and a bounded result budget. They are not pasted into every prompt. Keyword retrieval avoids per-query embedding costs.

Published tool versions and provider credential references are pinned. Existing local Sarvam speech, Groq LLM, JEV classifier, OpenRouter summary, WhatsApp template connection and technical-solutions calendar are configured. Credential decryption was checked without printing secrets. Speech language is auto-detected.

WhatsApp is available only in hot/warm follow-up; calendar writes only in scheduling. A scheduled callback request is distinct from a confirmed human calendar appointment. Uncertain external writes must not be automatically retried or replaced with fallback writes.

## Verification and operator acceptance

27 focused checks pass, including scoped prompts, classifier contracts/routing and real flow compilation. Both saved voice and text snapshots resolve; local calendar validation, credential decryption and three KB searches pass.

No live provider generation, WhatsApp send, booking or modem call was performed. Use Chat test first to check greetings, qualification, each route, consent refusal, callback bypass, provider/tool failures and interruption; live WhatsApp/calendar actions remain enabled. Then verify one browser call and SIM7600 call locally. Prompt rules and tool scoping reduce risk but cannot guarantee an LLM's every response. Main LLM output is capped at 180 tokens; provider TPM limits still require measured testing.

Review configuration: `docs/plan/elevated-box-focused-local.json`.
Local-only builder: `scripts/build_elevated_box_focused_local.py` (guards development and DB port 55433).
