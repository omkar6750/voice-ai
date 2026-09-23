---
id: RFC-0003
title: Configurable voice runtime and evidence
status: Accepted
version: 2
date: 2026-09-23
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

Run -> exchanges and finalized messages with explicitly linked operation spans.
An optional Call holds telephone lifecycle; browser runs need no Call. Exchanges
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

# Schema review amendment

This revision records all 29 sections of the supplied external schema review.
It is a documentation-only amendment. The statements above describe intended
guarantees, not proof of completed implementation. The reviewed baseline is
`69523d2`; existing tests and migration success do not establish the guarantees below.

Preserve single-workspace scope, mutable knowledge, agent-owned prompts and flows,
explicit exchanges, configured retention, and backend-only action credentials.
The original Call-owned exchange hierarchy is superseded here by Run ownership.
Browser/cloud-provider adapters are not implemented by this documentation change.

## Decision history

ADR-0006 and ADR-0007 were updated in place to version 2 at the user's explicit
request on 2026-09-23, including flow visits and ordered tool results. This is a
specific exception to the usual immutable ADR rule, not a general policy change.

## Numbered review dispositions

### 1. Session as root

- **Recommendation:** Replace Run/Call with AgentSession/TelephonyCall.
- **Decision and reason: adapt.** Accept conversation execution as root; retain Run
  and Call names. Run owns agent execution and evidence; optional Call owns telephone
  lifecycle. Final analysis can continue after hangup.
- **Gap:** Move exchanges/messages to Run and remove duplicate agent ownership from
  Call after preserving migration. One Run has zero or one Call initially.
- **Check:** Browser transcript persists without Call; telephone Run links one Call;
  configuration identity cannot disagree between the two records.

### 2. Remove Exchange

- **Recommendation:** Replace exchanges/messages with speaker turns.
- **Decision and reason: reject removal.** Speaker messages and response groups serve
  different purposes. An exchange can group greeting or caller input with multiple
  LLM/tool requests and assistant responses; flow nodes are not exchange boundaries.
- **Gap:** Add direct Run ownership, stable ordering and explicit exchange membership.
  Preserve generated text, synthesis and actual playback as distinct evidence.
- **Check:** Greeting, barge-in, multiple responses and background work retain correct
  links without reconstructing causality from timestamps.

### 3. Transcript versus exact LLM context

- **Recommendation:** Separate conversational transcript from provider context.
- **Decision and reason: accept separation.** Prompts, tool pairs and summaries differ
  from dialogue. Store sanitized actual input/output on each LLM operation; another
  context-message table is unnecessary initially.
- **Gap:** Wire request/response capture and source-message boundaries.
- **Check:** Readable transcript and exact sanitized inference evidence coexist,
  including the tool results and summaries actually supplied to that inference.

### 4. FlowNodeVisit

- **Recommendation:** Persist visits, timing and transition provenance.
- **Decision and reason: accept.** Stable visit IDs distinguish revisiting one node.
  Record entry/exit and triggering tool or runtime action. A separate node-change
  reason is unnecessary; never ask an LLM to generate a reason at runtime.
- **Gap:** Add visit persistence linked to a timing span. Span owns timing; visit
  entry/exit are exposed through that link rather than independently updated copies.
- **Check:** Re-entry creates another visit; transitions reference actual triggers,
  with no extra inference to explain them.

### 5. ServiceOperation

- **Recommendation:** Separate first-class service analytics from TraceSpan.
- **Decision and reason: adapt existing spans.** Add typed provider/model, operation
  links and queryable metrics without two rows representing each provider operation.
- **Gap:** Add OTel identifiers, final inputs/outputs, message/visit links and supported
  latency/usage columns. Normalize units; unknown metrics stay null. Distinguish event
  timestamps from monotonic durations and streaming STT from discrete requests.
- **Check:** LLM -> tool -> LLM produces two operations. Duplicate metrics do not double
  count; waterfall shows overlap, cancellation and playback separately from synthesis.

### 6. Raw RuntimeEvent table

- **Recommendation:** Store short-retained raw pipeline events in PostgreSQL.
- **Decision and reason: reject for now.** Significant lifecycle markers belong in
  structured evidence; optional expiring files hold pipeline/token/STT-revision detail.
- **Gap:** Enforce logging overrides and artifact expiration in runtime.
- **Check:** Logging disabled preserves final evidence; enabled detail expires by
  policy. No database row per token or PCM chunk.

### 7. Ordered tool results

- **Recommendation:** Add ToolInvocationResult and inference/function-call links.
- **Decision and reason: accept.** Intermediate results supplied to context must not
  overwrite each other, and parallel calls need explicit provenance.
- **Gap:** Add sequence, finality, originating operation, errors and consumption
  boundary. Absence differs from empty JSON; a completed result may itself be null.
  Internal progress that never enters context need not become durable result evidence.
- **Check:** Parallel tools and delayed consumption preserve originating exchange;
  duplicate ingestion cannot create duplicate final results.

### 8. OutboundMessage and receipts subsystem

- **Recommendation:** Move send/delivery evidence out of generic tools.
- **Decision and reason: reject expansion.** Conversation-history APIs may not reliably
  supply sent-message records, but exact local tool evidence already satisfies that
  need. No separate outbound message table, inbox or inbound body archive.
- **Gap:** Make receipt matching account/connection-scoped, deduplicated and safe under
  concurrent updates. Preserve exact send/template/media payload and external message ID.
- **Check:** Duplicate/reordered receipts neither lose evidence nor cross accounts;
  acceptance stays distinct from delivery/read; uncertain sends are not retried blindly.

### 9. Version/revision semantics

- **Recommendation:** Replace version/revision with releases and deployments.
- **Decision and reason: reject alleged flaw; defer deployments.** Version identifies
  configuration; revision deliberately detects conflicting draft edits. Immutable
  draft-edit history was never promised. Active-version FK cycles are manageable.
- **Gap:** Add clone-draft, expected revisions for all draft/binding writes, database
  immutability guards and published same-agent activation checks.
- **Check:** Conflicting edits fail; direct SQL cannot mutate published config/bindings;
  clone preserves lineage; publishing never implicitly activates a version.

### 10. Resolved configuration hash

- **Recommendation:** Expand snapshots and record a SHA-256 hash.
- **Decision and reason: accept.** Include schema version, resolved prompts/flow/tools,
  settings, overrides, non-secret bindings and application/dependency identifiers.
  Hash identifies configuration, not deterministic replay of mutable KBs/providers.
- **Gap:** Replace simple agent-config copying with complete sanitized resolution.
- **Check:** Canonical equivalent configs hash equally; effective changes differ;
  secrets never enter snapshots. KB identity/name replaces historical corpus copies.

### 11. Prompt library

- **Recommendation:** Add independently versioned prompt objects.
- **Decision and reason: defer.** Agent-owned prompts publish together; separate prompt
  releases add dependencies without a current workflow requiring them.
- **Gap:** Type and resolve system, node, classifier, composer and summary prompt slots.
- **Check:** Draft prompt edits cannot change published agents or past run evidence.

### 12. JSONB flow configuration

- **Recommendation:** Retain graph documents instead of flow micro-tables.
- **Decision and reason: accept.** Validated JSONB owns node prompts/actions/transitions;
  relational bindings constrain referenced tools and KB identities.
- **Gap:** Ensure migration type parity and shared validation. Preserve tested node-only
  prompt replacement; global-plus-node composition remains explicit opt-in.
- **Check:** Invalid graph/dependencies block publication; runtime enforces transitions.

### 13. Historical knowledge versions

- **Recommendation:** Pin published agent to a specific KB build.
- **Decision and reason: reject.** Mutable KB is intentional. Agent version pins KB
  selection and retrieval controls, not corpus content. Actual retrieval evidence
  explains previous answers without retaining historical chunks or source copies.
- **Gap:** State this limitation explicitly in API/UI contracts and resolved snapshots.
- **Check:** KB update changes subsequent retrieval without republishing the agent;
  old evidence survives source deletion without depending on chunk foreign keys.

### 14. Build foreign key

- **Recommendation:** Make build_id reference a KnowledgeBuild entity.
- **Decision and reason: reject mandatory historical build table.** Current token
  fences stale work; rename it `ingestion_token` to clarify operational purpose.
- **Gap:** Introduce ingestion jobs only when durable worker claiming/recovery needs
  them. Operational jobs must not become published corpus revisions or agent bindings.
- **Check:** Stale/deleted-source work cannot activate; failed rebuild preserves current
  chunks, successful replacement removes obsolete chunks.

### 15. Embedding dimensions

- **Recommendation:** Generalize fixed Vector(768).
- **Decision and reason: retain explicit 768 restriction.** Initial supported adapter
  uses normalized Gemini embeddings at 768 dimensions; mixed-vector infrastructure
  is unnecessary. A future dimension/model-family change requires migration/rebuild.
- **Gap:** Validate compatibility before ingestion and query execution.
- **Check:** Wrong model/dimensions cannot activate or silently query incompatible data.

### 16. Retrieval tables

- **Recommendation:** Add Retrieval/RetrievalHit for RAG evidence.
- **Decision and reason: accept evidence, reject duplicate tables initially.** Typed
  tool payloads hold query, KB ID/name, exact excerpts, ranks and score provenance.
- **Gap:** Unify contracts; separate agent retrieval from KB ingestion settings; apply
  supported thresholds/budgets and label reciprocal-rank scores accurately.
- **Check:** Evidence survives corpus mutation/deletion; cosine, keyword, fusion and
  reranker scores are not conflated. No historical chunk FK required.

### 17. ContactPoint

- **Recommendation:** Support multiple addresses and workspace-scoped uniqueness.
- **Decision and reason: defer expansion.** One normalized phone per contact meets
  current single-workspace POC; multiple channels/tenancy need actual workflows first.
- **Gap:** Normalize phone and validate contact timezone. Unknown timezone stays absent:
  neutral greeting and clarification before confirming a local callback time.
- **Check:** Equivalent phone formatting cannot create duplicates; invalid timezone
  rejected; historical destination snapshots remain unchanged.

### 18. Callback claiming/retries

- **Recommendation:** Add leases/attempts and resolve latest agent at execution.
- **Decision and reason: accept claim/recovery safety; retain pinned agent version.**
  Preserve agreed scheduling semantics: automation off, one automatic attempt within
  configured due window, initially 15 minutes.
- **Gap:** Add claim identity, lease/recovery state, attempt/outcome timestamps and atomic
  manual/automatic claiming. Expired lease cannot authorize redial of uncertain calls.
- **Check:** Races produce one attempt; disabled/missed windows do not auto-launch;
  restart never blindly redials; manual retry is explicit.

### 19. Universal Asset for recordings

- **Recommendation:** Replace recording paths with shared asset/recording tables.
- **Decision and reason: adapt through run_artifacts; defer universal schema.** Existing
  artifacts can own recording/debug metadata; shared safe file utilities avoid duplicate
  storage mechanics without polymorphic asset joins.
- **Gap:** Complete ORM/runtime wiring, track/media metadata, checksum, expiry/deletion
  and safe access. Keep legacy recording paths readable during migration.
- **Check:** Three tracks resolve securely; expiration removes files but retains deletion
  evidence, never presenting deleted artifacts as available.

### 20. ProviderMedia replaces IntegrationMedia

- **Recommendation:** Split file identity from provider media ID in new tables.
- **Decision and reason: retain IntegrationMedia; defer generic split.** Reusable media
  has different retention from calls and may represent imported IDs without source files.
- **Gap:** Share safe storage utilities, preserve content checksum across reuploads,
  distinguish template-creation handles from message-send media IDs.
- **Check:** Reupload changes provider ID without changing content identity; unavailable
  imports need replacement; call retention cannot delete reusable integration files.

### 21. Managed secret storage

- **Recommendation:** Prefer managed secret references over database ciphertext.
- **Decision and reason: retain Fernet and environment keyring.** Authenticated encryption
  suits local deployment. This is not envelope encryption; key_id selects a key outside
  the ciphertext database. Managed services remain future deployment work.
- **Gap:** Test config loading, rotation, operator-only writes, redaction and fail-closed use.
- **Check:** Wrong/missing key blocks use; rotated credentials work; neither plaintext nor
  ciphertext leaks through responses, browser storage, snapshots or traces.

### 22. Provider-neutral telephone metadata

- **Recommendation:** Replace modem_start/modem_end with stable provider fields.
- **Decision and reason: accept.** Call owns provider/connection, nullable external call
  ID, direction, endpoint reference, transport/codec/rate and telephone lifecycle;
  unusual diagnostics remain validated provider-specific snapshots.
- **Gap:** Persist internal call ID before dial. Generated modem correlation ID differs
  from external call ID; recycled modem call index is not a durable provider identity.
  Define shared adapter lifecycle without adding cloud implementations in this step.
- **Check:** Modem/fake-cloud events identify correct Call; failed dial still has ID;
  browser-only Run requires no telephone metadata.

### 23. Analysis history

- **Recommendation:** Add session-level analysis records instead of Call verdict fields.
- **Decision and reason: accept through planned classifications, context_summaries and
  contact_facts.** Different consumers need source boundaries, configuration identity
  and supersession. A generic additional analysis table is unnecessary initially.
- **Gap:** Implement these missing records and runtime persistence.
- **Check:** Reruns preserve prior results; provider failure is never a verdict; stale
  compaction preserves newer messages; facts link to original evidence.

### 24. Final session state

- **Recommendation:** Keep state separate from transcript; snapshot it on completion.
- **Decision and reason: accept sanitized final Run state.** In-memory live state suffices;
  no Redis or state-event table needed to avoid transcript parsing.
- **Gap:** Define final-state payload and abnormal-termination completeness.
- **Check:** Normal completion saves state; crash leaves incomplete/unknown state rather
  than fabricated final values; credentials excluded.

### 25. Complete proposed hierarchy

- **Recommendation:** Adopt the review's full authoring/runtime/files hierarchy.
- **Decision and reason: adapt selectively.** Run owns conversation evidence with optional
  Call. Authoring owns agent/tool versions and mutable KBs. Avoid tenancy, prompt releases,
  deployments, KB history and messaging tables added only for diagram completeness.
- **Gap:** Enforce ownership across message, exchange, span, visit and tool relationships.
- **Check:** Browser and phone share timeline representation; cross-run references fail.

### 26. JSONB versus relational fields

- **Recommendation:** Normalize queried/constrained data, retain variable payloads as JSONB.
- **Decision and reason: accept principle, not every proposed table.** Stable identities,
  timestamps, ordering and graphed metrics need explicit columns; validated config and
  provider/tool evidence fit JSONB. A queryable property alone does not require a subsystem.
- **Gap:** Correct migration JSON/ORM JSONB mismatch; add checks and relevant indexes.
- **Check:** Database introspection matches model invariants; timeline and callback queries
  have stable ordering and suitable indexes; receipt updates remain transactional.

### 27. UUIDs, timestamp defaults and indexes

- **Recommendation:** Convert IDs to native UUID, use server defaults and composite indexes.
- **Decision and reason: accept defaults/indexes; defer UUID conversion.** Preserve current
  IDs and avoid unrelated migration risk. Database creation time and runtime occurrence
  time are separate facts; elapsed operation timing uses monotonic measurement.
- **Gap:** Add lifecycle checks, database defaults, foreign-key/composite indexes and
  scheduled-callback partial index. Migration omits some ORM constraints, including
  Call run uniqueness.
- **Check:** Direct inserts obey guarantees; IDs survive; ingestion time never silently
  replaces event time; unknown historical timestamps/metrics stay unknown.

### 28. Storage systems

- **Recommendation:** PostgreSQL/pgvector plus object storage and optional runtime services.
- **Decision and reason: adapt to PostgreSQL/pgvector, local files and memory for POC.**
  Object storage, Redis, external OTel and analytics backends wait for deployment need.
- **Gap:** Finish artifact access, retention and bounded idempotent spool replay; keep
  OTel identities so later export does not redefine conversation identity.
- **Check:** Audio/debug files stay outside DB payloads; retention targets only intended
  artifacts; incomplete evidence is reported and replay does not duplicate records.

### 29. Immediate implementation sequence

- **Recommendation:** Rename root/turns, add multiple tables and pin KB history first.
- **Decision and reason: revise.** Prioritize integrity and ownership before new runtime
  dispatch so calls do not accumulate ambiguous history. Retain KB and exchange decisions.
- **Gap/order:** Database integrity -> provider-neutral Run/Call ownership -> evidence
  links -> analysis/callback safety -> runtime wiring.
- **Check:** Each slice has preserving migrations where needed, meaningful acceptance
  tests and accurate shipped-state documentation; protected demo remains unchanged.

## Verified gaps at reviewed baseline

- Migration uses JSON where models declare JSONB; several ORM checks/indexes/unique
  constraints do not reach PostgreSQL.
- Published configuration and bindings lack promised database guards.
- Binding updates lack expected-revision checks.
- KB API duplicates runtime contracts and incorrectly owns agent retrieval settings.
- Classification, summary and contact-fact persistence remains missing.
- Recording artifacts exist in migration without complete model/runtime wiring.
- Existing passing tests do not establish these new concurrency, immutability, recovery
  and end-to-end evidence guarantees. Migration success only proves applicability.

## Acceptance gate for subsequent implementation

Verify migration/model parity and existing-data preservation; immutable publication
and concurrent edits; browser Run without Call; modem identity before dial; interrupted
exchanges and parallel operations; delayed result consumption; mutable KB rebuild/deletion;
receipt races; callback claims and restart uncertainty; secret/artifact retention and
spool replay. Preserve IDs and evidence; mark missing historical facts, never invent them.

Keep `scripts/demo_call.py` unchanged. No KB history, inbox, tenancy, new cloud infrastructure
or UI redesign in this amendment. Application implementation remains subsequent work.

## Sources and verification

Models, migration, API routes and installed Pipecat aggregator/metrics source were
inspected against `69523d2` on 2026-09-23. Review numbering follows supplied review.

- [Pipecat transcripts](https://docs.pipecat.ai/pipecat/fundamentals/saving-transcripts):
  finalized user/assistant turn events and interruption information; use installed SDK
  signatures and correct finalized-text event for selected runtime mode.
- [Pipecat tools](https://docs.pipecat.ai/pipecat/learn/function-calling): intermediate
  async results can enter context before final completion.
- [Pipecat metrics](https://docs.pipecat.ai/pipecat/fundamentals/metrics): per-request
  latency/usage, repeated inference after tool results and provider-specific availability.
  Repeated TTFB fields can describe the same measurement, not additive latency.
- [Pipecat nodes/messages](https://docs.pipecat.ai/pipecat/flows/nodes-and-messages):
  structured flow definitions support validated JSONB configuration.
