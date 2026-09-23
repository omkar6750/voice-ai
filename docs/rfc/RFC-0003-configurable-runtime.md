---
id: RFC-0003
title: Configurable voice runtime and evidence
status: Accepted
version: 1
date: 2026-09-22
related: [RFC-0001, RFC-0002]
---

# Scope

Implement the approved single-workspace configurable runtime around the tested
demo. Preserve scripts/demo_call.py. Use PostgreSQL/SQLAlchemy, native Pipecat,
and a thin React control plane. No tenancy or message inbox.

# Ownership

Published agent/tool configurations are immutable; drafts use revisions. Agent
versions own flows, model settings, context/cadence and exact tool bindings.
Nodes reference binding keys. Knowledge bases are mutable, with atomic chunk
replacement and retrieval evidence captured per invocation. Contact timezone
controls greetings and callback interpretation; workspace has no timezone.

Model-provider credentials remain deployment environment values. Action-provider
secrets are authenticated ciphertext in PostgreSQL, decrypted only in backend
adapters. Media IDs need a local catalog because no general provider listing
endpoint was found. No inbound message body archive.

# Evidence

Call -> exchanges -> finalized messages and linked operation spans. Exchanges
can contain multiple LLM/tool requests. Opening is explicit. Speech, synthesis,
and serial playback are different facts. Background work may outlive its source
exchange. Native provider spans are reused rather than duplicated.

Structured evidence persists until deletion; recording/debug artifacts default
to seven days. Logging is configurable independently of environment. Durable
bounded local spool must never block realtime audio.

# Execution

Persist before dialing; claim one call per endpoint. No blind restart redial.
Callbacks support manual launch and optional automatic dispatch (disabled).
No speculative success from missing credentials, provider failure or unknown
delivery. External write timeouts remain uncertain unless retry is idempotent.
