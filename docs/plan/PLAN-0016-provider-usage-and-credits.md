# PLAN-0016 · Provider usage and credits

Status: removed

## Decision

The provider usage/credits dashboard feature was removed during development.
The configured provider credentials do not expose a supported, consistent
account usage or remaining-credit API that this application can safely present.

## Removed surface

- `GET /api/v1/usage` and its API router registration
- Usage Pydantic schemas and service
- Usage dashboard page, route, and navigation item
- Usage unit tests and generated OpenAPI/TypeScript contracts

## Retained behavior

Provider errors and per-call evidence remain part of the normal run and
diagnostic views. Token/audio fields that are already recorded in trace spans
remain evidence for that call; they are not converted into account credits or
provider balances.

## Non-goals

- No provider-console scraping
- No inferred provider balance from local evidence
- No credential editing or billing workflow

See [ADR-0016](../adr/ADR-0016-provider-usage-observability.md) for the
historical implementation decision and its supersession.
