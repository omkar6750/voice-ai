---
id: ADR-0058
title: Conversation fact defaults and node-entry prompt fallbacks
status: Accepted
date: 2026-10-09
---

Conversation facts initialize once per new run from an operator default, with
an empty string as the unset marker for every declared type. Nonempty defaults
must match the type, enum and numeric bounds. Null and nonfinite defaults are
invalid. Record tools retain typed validation; facts survive node changes and
context resets but are not persisted into later calls.

Plain-text expressions `[ {{fallback}} | {{preferred}} ]` choose the rightmost
nonempty candidate. Strings containing only whitespace and numeric zero are
empty; string "0" is not. Chains are supported, booleans are excluded, and an
all-empty expression renders an empty string. No evaluation, literals, nesting
or recursive substitution is supported. Escaped expressions remain literal.

The pure voice_shared parser/resolver serves validation, read-only previews and
the local FlowManager rendering hook. Instructions, task messages and tts_say
action text resolve at node entry, including re-entry. Recording a fact within
a node does not refresh existing instructions until the next entry. Historical
messages and tool results are never processed as templates.

Defaults live in configuration JSONB. Missing defaults in historical versions
remain empty, and published rows are not rewritten. New saves reject collisions
between fact keys and exposed contact or temporal variables. Runtime preflight
rejects malformed expressions before pipeline preparation proceeds.

Typed resolution records travel with flow-visit evidence into the existing
node span's input JSONB. Candidate values, source offsets, provenance, chosen
values and entry time are retained once per visit and redacted through existing
evidence controls. LLM operations retain their existing node_visit_id link and
exact provider-input evidence. Historical resolution is never inferred from
the current configuration.

Dashboard prompts remain literal Tiptap text. A fallback picker and typed default
controls assist authoring; the preview API renders unsaved samples without writes,
provider requests or tool execution. This feature does not change provider language
settings, WhatsApp status handling or any saved Ritu versions.
