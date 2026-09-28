# Decision index

| ID | Decision | Status |
| --- | --- | --- |
| [ADR-0001](docs/adr/ADR-0001-runtime-boundaries.md) | Keep API, runtime, and modem edges as explicit local modules | Accepted |
| [ADR-0002](docs/adr/ADR-0002-sqlalchemy-postgres-foundation.md) | Use async SQLAlchemy and Alembic for the first database slice | Accepted |
| [ADR-0003](docs/adr/ADR-0003-provider-adapters.md) | Keep OpenAI and telephony SDK imports behind adapters | Accepted |
| [ADR-0004](docs/adr/ADR-0004-demo-provider-stack.md) | Use Sarvam STT, Groq Llama 3.1 8B Instant, and Cartesia TTS for the demo agent | Accepted |
| [ADR-0005](docs/adr/ADR-0005-voice-test-runtime.md) | Native PCM test lifecycle and available Groq Qwen model; supersedes ADR-0004 | Accepted |
| [ADR-0006](docs/adr/ADR-0006-versioned-configuration.md) | Published configuration, draft concurrency and mutable KB; revision 2 per user request | Accepted |
| [ADR-0007](docs/adr/ADR-0007-exchanges-and-integration-secrets.md) | Run-owned evidence, provider-neutral calls and encrypted integrations; revision 2 per user request | Accepted |
| [ADR-0017](docs/adr/ADR-0017-on-demand-endpoint-probing.md) | On-demand modem probe with five-second monitoring while connected | Accepted |
| [ADR-0020](docs/adr/ADR-0020-node-scoped-transition-tool-schemas.md) | Scope `change_node` destinations to each flow node's transitions | Accepted |
| [ADR-0021](docs/adr/ADR-0021-typed-evidence-and-shared-delivery.md) | Validate evidence events end-to-end, unify final draining, and recover durable spool records safely | Accepted |
