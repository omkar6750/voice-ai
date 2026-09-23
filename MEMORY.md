# Working state

Phase: configurable runtime control-plane slice.

Completed: typed runtime configs, versioned agents/tools, integration vault/media catalog, mutable
pgvector knowledge, evidence models/spool, compact dashboard, and schema migration.

Next slice: connect queued calls and evidence spool to modular Pipecat runtime, then finish agent
and knowledge form editors. Do not edit `scripts/demo_call.py`.

Known blockers: SIM7600 audio mapping remains hardware-dependent. Existing DB at 55432 is plain
PostgreSQL and cannot run pgvector migration. Provider keys remain local-only.
