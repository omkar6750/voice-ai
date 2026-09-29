---
id: ADR-0025
title: Model selects callback role; backend assigns calendar owner
status: Accepted
version: 1
date: 2026-09-29
related: [RFC-0007, ADR-0007]
---

The callback tool schema is built from the pinned agent snapshot. Its `role`
parameter is an enum of enabled roles that have an enabled bookable person, with
the configured role labels and descriptions included as model guidance. The
model selects a role and time; it never selects a person or calendar. Callback
tools are omitted from the node when callback scheduling is disabled or no
usable role/person pairing exists. API validation remains authoritative.

Availability time phrases are interpreted once using the contact's IANA
timezone, consistent with RFC-0007. Missing or invalid timezones do not fall
back to a bookable person's/calendar timezone. Booking revalidates that the
contact timezone still matches the signed slot so a stale slot must be checked
again.

Each enabled person/calendar is checked independently. Disconnected or failing
calendars do not hide slots from healthy calendars; responses distinguish
partial results, all-calendar failure, and confirmed no availability. The
backend assigns each returned interval to the earliest available person, using
configured person order for ties, deduplicates equivalent intervals, and keeps
the assignment inside the signed slot. Booking rechecks that slot and persists
the selected role/person/calendar with the calendar event.

The availability endpoint now has strict typed success and error responses for
partial/unavailable calendars, missing contact timezone, invalid timeframe,
configuration errors, and true no-availability. OpenAPI and dashboard types are
regenerated through the repository flow.

Verification: 31 focused tests pass; Ruff passes; OpenAPI export, dashboard type
generation, and production build pass. A live Google Calendar OAuth/Freebusy and
event-creation test remains dependent on connected test credentials. Async tool
completion delivery is explicitly out of scope and remains PLAN-0035.
