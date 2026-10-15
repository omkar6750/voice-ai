# Documentation

Reviewed against checkout `42f7b10` on October 15, 2026. Source review confirms
implementation, not live deployment or hardware acceptance.

## Start here

- [Decision index](architecture/decision-index.md): every ADR/RFC reviewed,
  current applicability and superseded sections.
- [Issue catalog](issues/README.md): incidents, fixes, exact tests and gaps.
- [Regression guide](testing/regression-tests.md): adding meaningful tests.

## Operational references

- [Runtime split](deployment/RUNTIME-SPLIT.md), [text tests](deployment/TEXT-TESTS.md)
  and [MCP access](deployment/MCP-ACCESS.md).
- [Deployment acceptance](deployment/ACCEPTANCE.md) is a dated checklist. Its old
  unchecked items require fresh verification; they do not prove a feature is absent.
- [Production sync](deployment/PRODUCTION-SYNC.md) records an October 4 operation.
  It is not today's inventory or proof of the later prepared import.
- [Runtime debugging](runtime-debugging.md), [voice path debugging](voice-path-debug.md)
  and [call performance diagnostics](call-performance-diagnostics.md).

## Historical records

`adr/`, `rfc/` and `plan/` preserve decisions and implementation plans. Numbering
gaps are intentional. Proposed RFCs remain proposals even when portions were
implemented. Supersession applies only to the identified section unless an
entire record explicitly names its replacement.

Keep [AIDLC.md](AIDLC.md) as the development workflow. This review adds retrospective
ADRs for implemented decisions; it introduces no new RFC or product policy.

## Updating documentation

For a fix, add the symptom, established cause, source/test links, verification
performed and remaining uncertainty under `issues/`. Do not commit raw calls,
private logs, phone numbers, keys or database dumps. Update the system design
when boundaries change, and link an ADR for a settled decision.

Record implementation, test results and deployment acceptance separately. An old
passing-test count is not a statement about today's checkout.
