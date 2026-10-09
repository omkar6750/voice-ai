# Flat contact prompt variables

Contact prompts use first_name, last_name, business, source, query, timezone,
language and explicitly selected metadata directly. There is no name prompt
variable or nested contact namespace. Full name remains a display label for
directory/calendar/history consumers; contact editing uses first and last parts.

Migration 0050 repairs missing name components using the first whitespace token
as first name and the remaining tokens as last name, without overwriting already
supplied components. This is a mechanical split, not an inference of cultural
name structure; operators can correct the fields.

Chat snapshots include the same first/last components as browser and phone calls.
Selected missing fields render empty. Legacy immutable snapshots can derive name
parts from their display name. Agent contract loading translates old name and
contact.field placeholders to canonical flat placeholders on a copy.
Published configuration and historical evidence are not rewritten. Local drafts
are updated with revision increments using migrate_flat_contact_prompts.py.

Prompt editors and the variable catalog expose only canonical flat variables.
The runtime retains no nested contact state for prompting. This prevents a
missing nested property from failing flow initialization when a selected field
has no value.
