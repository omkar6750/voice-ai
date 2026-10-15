---
id: ADR-0063
title: Seed a tenant-owned demo agent and redacted historical run
status: Accepted
version: 1
date: 2026-10-15
related: [ADR-0031, ADR-0006, ADR-0007]
---

# Decision

New organizations receive **Ritu — Project demo v1 as an inactive draft** and one completed example
run during the existing organization provisioning transaction. This replaces
the previous empty starter agent for new organizations. Existing organizations
with seed manifest v1 keep their catalog unchanged.

The example projects the completed October 10 Project Assistant v13 call into
a packaged, reviewed fixture. It contains 12 exchanges, 22 messages, 66 measured
speech/model/playback/flow spans and four flow visits. Phone numbers are removed.
Raw model contexts, external-action evidence, private recordings, transport logs,
contacts, credentials and integration records are excluded. The seed performs no
network requests and needs no storage or provider credentials.

The starter configuration is an adaptation, not a reconstruction of the original
execution snapshot. Both the version note and run view disclose that distinction.
Historical timing values are retained without inventing inputs, outputs or delivery
receipts. Original message interruption flags and playback timestamps remain intact.
No claim of complete replay evidence is made.

Each organization gets fresh IDs for its agent, version, run and child evidence.
The seeded snapshot pins that organization's version and receives its own canonical
hash. No foreign tenant IDs serve as references. The original run ID is provenance
text only. No Call, endpoint lease or contact is created.

The starter uses native transitions and a terminal `end_conversation` action. It
has no external tool bindings, knowledge bases, credential references, classifier,
composer or summarizer. It selects Sarvam Conversations, realtime Saaras v3 and
Bulbul v3/Ritu. The organization adds its own credentials before publishing and
activating the starter. Production publication revalidates credential references,
including when the draft has not been edited since seeding. The existing development
compatibility path is unchanged. Historical spans retain the models that actually executed.

The demo run remains completed and viewable while its linked starter is a draft.
Its stored snapshot is independent of later draft edits. Seeding neither publishes
nor activates an agent and is never performed on every login.

The existing organization row lock serializes seeding. Manifest v2 is written only
after all rows flush. Provisioning commits everything together; an error rolls back
the organization and demo. Repeated registration does not duplicate the example or
restore a demo the operator deleted. No migration, backfill or new environment
variable is needed. Organization-creation feature gates remain in effect.

# Verification

- [Unit tests](../../tests/unit/test_organization_demo.py): typed configuration,
  terminating graph, fixed evidence selection and private-field exclusion.
- [PostgreSQL integration tests](../../tests/integration/test_organization_seed.py):
  publication/foreign-key guards, production credential independence, run/timeline
  reads, idempotency, independent tenant IDs and preservation of existing catalogs.

Provider speech quality and real call behavior require separate live acceptance.
