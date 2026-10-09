# Terminal outcomes and callback preferences

Accepted 2026-10-08, following explicit user direction.

A successfully entered terminal node marks the conversation objective completed
once execution ends, including caller hang-up during closing. Preserve the actual
termination cause and playback facts separately. A failed node setup does not count
as entry. Cleanup uncertainty still prevents final run completion and keeps the
modem fenced; entering closing does not prove transport release.

Fallback callbacks are unconfirmed human follow-up requests. Preserve the caller's
day/time phrase without adding a clock time. The backend's due_at and requested
window are eligibility/indexing boundaries, not promised appointment times.
scheduled_start remains absent until a real calendar booking. Human requests are
excluded from automatic dialing. Display their original preference and pending
time confirmation rather than the internal due_at boundary.

Ritu sends one WhatsApp confirmation after any successful callback action, honoring
explicit refusal. Fallback messages state that the team will confirm a suitable
time later. Provider failures remain visible; no automatic message retries.

Transcript tool/message events are ordered by their recorded occurrence timestamps
within each exchange. This order conveys chronology, not an inferred exact link
between a tool and a message; the original operation/result links remain authoritative.
