# Repository state

This repository uses the workflow in [AIDLC.md](AIDLC.md).

Current implementation: separate API/runtime services, versioned agent authoring,
organization access, browser/text testing, local modem calls and linked run evidence.
Reviewed against `42f7b10` on October 15, 2026. This is not fresh deployment acceptance.

Read order for a new session:

1. Git status and recent history.
2. [Decision index](architecture/decision-index.md) and [documentation navigation](README.md).
3. `MEMORY.md`, `DECISIONS.md`, the owning plan and applicable ADRs.
4. Relevant code and tests.

At session end, reconcile code, tests, `MEMORY.md`, `DECISIONS.md`, and the README. Draft or untracked work is not shipped work.
