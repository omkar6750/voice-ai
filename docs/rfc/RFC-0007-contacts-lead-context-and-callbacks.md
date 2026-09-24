---
id: RFC-0007
title: Contacts, lead context, and callback scheduling surface
status: Proposed
version: 1
date: 2026-09-23
authored_by: omkar
related: [RFC-0001, RFC-0003, RFC-0004, RFC-0006]
---

# RFC-0007 · Contacts, lead context, and callback scheduling surface

## Implementation amendment, 2026-09-24

- Contact timezone owns greeting and callback interpretation. Unknown timezone requires clarification before confirming local time.
- Contact list/create exist; edit, detail/facts and filtered history need backend routes. Callback create/launch exist; list/status/detail need backend routes.
- Show confirmed due time, timezone, pinned agent version, claim state and resulting call. Request acceptance is not call success.

## 1. Context

In the Voice AI platform, a `Contact` represents an individual or business lead (e.g. Deepankar Paria @ Neotribe). Contacts own:
- E.164 normalized phone numbers.
- Timezone context (e.g. `Asia/Kolkata`) which governs time-of-day greetings and callback scheduling.
- Immutable contact snapshots captured at run creation.
- Extracted `ContactFact` entries accumulated across multiple conversation runs.
- `Callback` records representing commitments to reconnect.

## 2. Goals

- Provide a searchable, filterable directory of contacts and leads.
- Display a comprehensive Contact Profile highlighting extracted facts, past conversation runs, lead classifications, and pending callbacks.
- Offer an integrated **Callback Management Queue** allowing manual launch or inspection of automatic dispatch windows.
- Provide a one-click "Dial Contact" action with agent version selection.

## 3. Non-Goals

- Full CRM email marketing or multi-channel inbox (the platform is focused on voice AI calls and direct WhatsApp follow-ups).
- Multiple phone numbers per contact record in initial single-workspace POC.

## 4. Routes

- `/contacts` — Contacts list with search (by name, phone, business), language, and timezone tags.
- `/contacts/:contactId` — Contact profile detail:
  - `?tab=overview` — Profile info, business details, timezone clock, and quick dial.
  - `?tab=facts` — Extracted structured knowledge facts and history.
  - `?tab=runs` — Paginated list of historical voice calls and browser runs.
  - `?tab=callbacks` — Scheduled, queued, and completed callbacks.
- `/callbacks` — Global callback dispatch queue across all contacts.

## 5. API Dependencies

### Consumed Existing APIs
- `GET /api/v1/contacts` — List all contacts.
- `POST /api/v1/contacts` — Create new contact with normalized phone number.
- `POST /api/v1/calls` — Initiate an outbound phone call to a contact.
- `POST /api/v1/callbacks` — Schedule a new callback for a contact.
- `POST /api/v1/callbacks/{callback_id}/launch` — Manually launch a scheduled callback.
- `GET /api/v1/runs` & `GET /api/v1/runs/{id}/analysis` — Lookup runs and extracted contact facts.

### Required Backend Additions
- `GET /api/v1/contacts/{contact_id}` — Retrieve single contact profile.
- `PATCH /api/v1/contacts/{contact_id}` — Update contact details (name, business, timezone, language).
- `DELETE /api/v1/contacts/{contact_id}` — Archive or delete a contact.
- `GET /api/v1/callbacks` — List all scheduled callbacks across the workspace with filtering by status and due date.

## 6. Layout & Feature Components

### 6.1 Contact Detail Layout
```text
┌────────────────────────────────────────────────────────────────────────┐
│ [← Contacts] Deepankar Paria  [Neotribe]   [Asia/Kolkata • 21:45 IST]  │
├────────────────────────────────────────────────────────────────────────┤
│ Phone: +91 73875 01703 │ Language: en-IN │ Status: 🔥 Hot Lead (85%)   │
│ [📞 Start Voice Call]     [⏱ Schedule Callback]     [💬 Send WhatsApp] │
├────────────────────────────────────────────────────────────────────────┤
│ [Overview & Facts]  [Conversation History (3)]  [Scheduled Callbacks (1)]│
├────────────────────────────────────────────────────────────────────────┤
│ Extracted Contact Facts:                                               │
│ • Brand Aesthetic: Modern Indian Desi Maximalism (from Run 43638018)   │
│ • Stock Status: Acquired (from Run 43638018)                           │
│ • Target Launch: Diwali Campaign (from Run 43638018)                   │
│                                                                        │
│ Recent Calls:                                                          │
│ • 23 Sep 2026, 21:18 IST — Duration: 4m 12s • Maya v1 • [Completed]   │
└────────────────────────────────────────────────────────────────────────┘
```

### 6.2 Key Components
- `ContactFactCard.tsx`: Displays key-value facts extracted by post-call LLM analysis with links to the source conversation turn.
- `ScheduleCallbackDialog.tsx`: Date/time picker respecting contact's IANA timezone and computing UTC due dates.
- `CallbackQueueTable.tsx`: List of pending callbacks with countdown timers, due window indicators, and "Launch Now" trigger.
- `ContactDialerDialog.tsx`: Fast call launcher pre-selecting the contact, allowing endpoint and agent version override.

## 7. Open Questions & Iteration Notes

1. *Fact Merging & Conflict Resolution*: When multiple calls extract conflicting facts (e.g. changed budget or timeline), the UI displays fact supersession lineage using `ContactFact.supersedes_id`.
