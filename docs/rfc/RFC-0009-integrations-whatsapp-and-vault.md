---
id: RFC-0009
title: Action integrations, WhatsApp Cloud API, and secret vault surface
status: Proposed
version: 1
date: 2026-09-23
authored_by: omkar
related: [RFC-0001, RFC-0003, RFC-0004]
---

# RFC-0009 · Action integrations, WhatsApp Cloud API, and secret vault surface

## Implementation amendment, 2026-09-24

- Secrets are write-only. Show configured/needs-rotation state, never reveal saved token. Transient input clears after submission.
- Connection edit and test-send need backend routes. Test-send is explicit external action with confirmation and recorded result.
- Tool evidence stores exact template parameters, media ID/checksum, destination and provider message ID. Acceptance, delivery and read differ. No inbound archive or inbox. Unknown direct-message window defaults to template.

## 1. Context

Autonomous voice agents trigger real-world actions during and after calls, notably dispatching catalogs, booking confirmations, and summaries via the **Meta WhatsApp Cloud API**.

To maintain strict security:
- Provider credentials (e.g. `access_token`) are write-only encrypted in PostgreSQL using Fernet keys (ADR-0007).
- The dashboard never receives, stores, or renders decrypted secrets.
- WhatsApp media assets require local handle mapping (`IntegrationMedia`) because Meta does not provide a general media listing API.
- Direct-message eligibility uses transient latest-inbound state. Unknown window state defaults to a template.

## 2. Goals

- Provide a management interface for action connections (WhatsApp Cloud API, webhook endpoints).
- Support write-only secret submission (`PUT /secrets/{name}`) with status badges indicating credential presence without revealing ciphertext or plaintext.
- Enable media asset upload (images, catalogs, PDFs) and Meta Media ID generation for template headers.
- Provide an integrated WhatsApp test dispatch tool to verify outbound delivery to a test mobile number.

## 3. Non-Goals

- General customer support chat inbox (inbound message bodies are not archived in DB; webhooks only update 24-hour window timestamps and message delivery receipts).

## 4. Routes

- `/integrations` — List of all configured action connections, provider types, and enablement toggles.
- `/integrations/:connId` — Connection detail view:
  - `?tab=config` — Phone Number ID, WABA ID, API version, and Webhook verification token.
  - `?tab=secrets` — Write-only credential vault manager (`access_token`).
  - `?tab=media` — Uploaded media catalog for template headers.
  - `?tab=test` — Live test message and template dispatcher.

## 5. API Dependencies

### Consumed Existing APIs
- `GET /api/v1/integrations` — List all connections and configured secret names.
- `POST /api/v1/integrations` — Create a new integration connection.
- `PUT /api/v1/integrations/{id}/secrets/{name}` — Save Fernet-encrypted write-only secret.
- `GET /api/v1/integrations/{id}/media` — List uploaded media items and checksums.
- `POST /api/v1/integrations/{id}/media/upload` — Upload image/PDF to Meta Graph API.
- `POST /api/v1/integrations/{id}/media/import` — Import an existing Meta Media ID.

### Required Backend Additions
- `PUT /api/v1/integrations/{id}` — Update connection configuration.
- An explicit test-send route with recorded provider outcome.

## 6. Layout & Feature Components

### 6.1 Integration Detail Layout
```text
┌────────────────────────────────────────────────────────────────────────┐
│ [← Integrations] Meta WhatsApp Cloud API  [🟢 Enabled]  [ID: conn_01]   │
├────────────────────────────────────────────────────────────────────────┤
│ [⚙ Settings & Webhook]  [🔐 Secret Vault]  [🖼 Media Catalog]  [🧪 Test] │
├────────────────────────────────────────────────────────────────────────┤
│ Secret Vault:                                                          │
│ ┌────────────────────────────────────────────────────────────────────┐ │
│ │ • access_token: [🟢 Configured & Encrypted]  [Update Secret]       │ │
│ └────────────────────────────────────────────────────────────────────┘ │
│                                                                        │
│ Live WhatsApp Test Dispatch:                                           │
│ Target Mobile Number: [+91 73875 01703       ]                         │
│ Message Mode: (•) Approved template  ( ) Direct Message             │
│ [🚀 Send Test WhatsApp Message]                                        │
│                                                                        │
│ Result: [🟢 Message Sent • Meta ID: wamid.HBgMOTE3Mzg3NTAxNzAzFQIA...] │
└────────────────────────────────────────────────────────────────────────┘
```

### 6.2 Key Components
- `SecretInputModal.tsx`: Modal dialog for entering new API tokens, warning the user that secrets are write-only and cannot be viewed after saving.
- `WhatsAppTemplatePreview.tsx`: Visual preview card simulating WhatsApp message rendering with header image, dynamic parameters (`{{1}}`, `{{2}}`), and footer buttons.
- `MediaUploadManager.tsx`: Drag-and-drop media uploader validating file size and sending direct uploads to Meta via the backend proxy.

## 7. Open Questions & Iteration Notes

1. *Webhook Verification URL helper*: The UI may copy the callback URL. A saved verification token is never shown; an operator enters or rotates it through a write-only form.
