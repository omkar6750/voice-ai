# AI-DLC

Work moves in one direction:

```text
RFC -> ADR -> PLAN -> CODE
```

- RFC: problem, options, tradeoffs, open questions. Lives in `docs/rfc/`.
- ADR: one settled decision. Accepted ADRs are immutable. Supersede them with a new ADR.
- PLAN: implementation order and evidence. Lives in `docs/plan/`.
- CODE: executable behavior plus tests.

Every RFC and ADR uses frontmatter with `id`, `title`, `status`, `version`, `date`, `authored_by`, `session`, `supersedes`, `superseded_by`, and `related`.

Rules:

1. Do not put unresolved questions in an Accepted ADR.
2. Keep one decision per ADR.
3. Stage files explicitly. Do not use `git add -A`.
4. Update `MEMORY.md`, `DECISIONS.md`, and the README when shipped state changes.
5. Keep each worktree focused on one decision or vertical slice.
