# Tools authoring workspace

## Workflow

The catalog shows one row per logical tool, its copyable ID, latest published
version, and draft count. Opening a tool shows Drafts, Published versions, and
Used by agents. Version lists use pages of 20 summary records, newest first.
Opening a version loads that configuration separately.

Create draft offers existing drafts and a new draft based on the selected
published version. Successful cloning navigates to the returned version ID.
Server clone allocation and revision checks are unchanged.

Draft editing has its own URL:
`/tools/:toolId/versions/:versionId/edit`. Definition, Parameters, Execution,
and Advanced sections share one in-memory draft. Saving keeps the editor open
and uses the returned revision for subsequent saves. Save & validate persists
dirty input before calling the existing saved-version validation endpoint.

Publication is available on the saved version overview and draft history rows.
Its dialog validates an exact saved version/revision before publication.
The publish API rejects stale revisions. Publication does not update agent
bindings automatically.

Tool ID, Version ID, Agent ID, Agent Version ID, and binding names are visible
and copyable where applicable. Agent binding identity remains the composite
(agent version, binding name); no extra binding UUID is introduced.

## Compatibility

Default `GET /tools` and `GET /tools/{id}/versions` responses remain unchanged.
Existing agent binding pickers retain the full version contract.
The new dashboard uses `?view=summary`; version summaries accept
`status`, `before_version`, and `limit` (20 by default, maximum 100).
Single-version retrieval requires the matching logical `tool_id`.
Usage reads paginate persisted bindings without loading agent configs.
New reads retain tenant guards and member access rules.

Save, clone, publish, validation, deletion, and runtime execution business logic
are unchanged. Structured parameter editing preserves nested schemas, enums,
references, defaults, and root constraints.

The existing nested routes now run inside a root data router, enabling the
supported React Router navigation blocker. Dirty navigation offers Stay,
Discard changes, or Save & leave; section changes preserve the draft.
Browser reload/close uses the native unsaved-change warning.
Published versions stay read-only. External publication during a dirty edit
retains text for inspection and disables all writes.

Queries are scoped by user, organization, and support session, use cancellation,
and stay in memory. Mutations invalidate workspace summaries and legacy
tool-resource queries used by agent binding pickers.

## Verification

- `npm run test:tools`: DOM unit tests with mocked APIs; no browser automation.
- `npm run build`: TypeScript and production bundle checks.
- `uv run pytest tests/integration/test_tool_workspace.py`: requires an isolated
  migrated `VOICE_TEST_DATABASE_URL`; all fixture writes roll back.
- Existing tool contracts, registry, authorization inventory, deletion cleanup,
  and hosted cleanup boundary tests are included in regression verification.

No schema migration or stored-data rewrite is needed. UI appearance has not
been checked in a browser, in accordance with the repository's automation rule.
Hardware/provider behavior is outside this static authoring change.
