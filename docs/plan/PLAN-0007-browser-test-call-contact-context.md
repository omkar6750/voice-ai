# PLAN-0007: Browser Test Call with Contact Context & WhatsApp Delivery

## Executive Summary
Currently, test calls launched from the dashboard browser interface (`POST /api/v1/browser-sessions` using Pipecat SmallWebRTC) run in isolation without contact identity:
- `Run.contact_id` is `None`
- `Run.contact_snapshot` is `{}`
- No destination phone number is attached to the runtime snapshot (`target_snapshot` is empty)

As a result:
1. Contact prompt variables (e.g. `{{ name }}`, `{{ source }}`, `{{ query }}`, `{{ business }}`, `{{ greeting_phrase }}`) cannot interpolate real values.
2. Tools that deliver messages outside the voice call (such as `#whatsapp_template_*`, `#send_whatsapp_message`, or `#schedule_callback`) fail because no valid recipient phone number or contact ID is available in the runtime execution snapshot.

This plan enriches browser test sessions so operators can:
1. **Select an existing Contact** from the CRM/Contacts catalog, or **enter a custom test phone number & profile**.
2. Optionally **override the destination phone number** to receive WhatsApp messages on their own device while testing.
3. Have all prompt variables, temporal greeting phrases, WhatsApp dispatches, and callback bookings execute live in real time while conversing through the browser microphone/speakers.

---

## Architectural Workflow

```
Dashboard: TestAgentModal
   │
   ├── 1. Operator selects Agent (Active / Published / Draft)
   ├── 2. Operator selects Contact (e.g. "Omkar Pawar - +917304058886")
   │      OR enters Test Phone Number (e.g. "+919876543210") & Test Variables
   ├── 3. Optional: WhatsApp Delivery Override Number
   │
   ▼ POST /api/v1/browser-sessions
{
   "agent_version_id": "...",
   "contact_id": "1be38512-...",
   "phone_number": "+917304058886",
   "contact_variables": { "query": "E-commerce platform", "source": "LinkedIn" }
}
   │
   ▼ voice_api: create_browser_session()
   │
   ├── Fetch or synthesize Contact Snapshot:
   │      id: contact.id or "test-contact-..."
   │      name, phone_number, timezone, business, source, language, metadata_json
   │
   ├── Create Run:
   │      channel = "browser"
   │      transport_provider = "dashboard"
   │      contact_id = contact.id (links run to CRM contact history)
   │      contact_snapshot = <hydrated contact dictionary>
   │
   ├── Inject into Runtime Snapshot:
   │      snapshot["_resolved"]["contact"] = contact_snapshot
   │      snapshot["contact_snapshot"] = contact_snapshot
   │      snapshot["target_snapshot"] = phone_number
   │      snapshot["contact_id"] = contact_id
   │
   ▼ WebRTC Session Created & Connected (SmallWebRTCTransport)
   │
   ▼ NativePipelineHost.prepare(snapshot, tracker, transport=SmallWebRTC)
   │
   ├── 1. resolve_local_time_context(timezone) -> {{ greeting_phrase }}, {{ local_time_12h }}
   ├── 2. sanitize_contact_variables(contact, allowed_vars) -> {{ name }}, {{ query }}, etc.
   ├── 3. flow.state populated with temporal & contact variables
   ├── 4. Audio runs via Browser Microphone & Speaker (Echo cancellation + VAD)
   │
   └── When Agent invokes tools:
          ├── whatsapp_template_dialtone_followup(caller_name=...)
          │     ──> Recipient = phone_number (+917304058886)
          │     ──> Live Meta WhatsApp API dispatches template to phone!
          │
          └── schedule_callback(time="tomorrow at 3pm")
                ──> Creates Callback linked to contact_id in DB!
```

---

## Key Components & Changes

### 1. Backend API Contracts (`voice_api`)

#### File: `apps/api/voice_api/schemas/browser_session.py`
Extend `CreateBrowserSessionRequest` to accept contact context and phone parameters:
```python
class CreateBrowserSessionRequest(BaseModel):
    agent_version_id: str | None = None
    contact_id: str | None = None
    phone_number: str | None = None
    contact_variables: dict[str, Any] | None = None
    logging_override: bool | None = None
```

#### File: `apps/api/voice_api/services/browser_session_service.py`
Update `create_browser_session`:
- If `contact_id` is supplied:
  - Query `session.get(Contact, contact_id)`. Raise 404 if not found.
  - Hydrate `contact_snapshot` with all fields (`id`, `name`, `phone_number`, `timezone`, `business`, `source`, `language`, `metadata_json`).
  - Allow `phone_number` parameter to override the recipient number for test delivery.
  - Merge any explicit `contact_variables` into `metadata_json` and top-level fields.
- If `contact_id` is not supplied, but `phone_number` or `contact_variables` is provided:
  - Generate a test contact snapshot (`test-contact-<hash>`) with the test phone number, name, and variables.
- Attach to `Run`:
  - `run.contact_id = contact.id if contact_id else None`
  - `run.contact_snapshot = contact_snapshot`
- Inject into resolved configuration snapshot:
  - `snapshot["_resolved"]["contact"] = contact_snapshot`
  - `snapshot["contact_snapshot"] = contact_snapshot`
  - `snapshot["target_snapshot"] = contact_snapshot.get("phone_number")`
  - `snapshot["contact_id"] = contact_snapshot.get("id")`
  - Recompute `run.config_hash = fingerprint(snapshot)`

#### File: `apps/api/voice_api/api/v1/endpoints/browser_sessions.py`
Pass `contact_id`, `phone_number`, and `contact_variables` from `CreateBrowserSessionRequest` into `create_browser_session()`.

---

### 2. Runtime Pipeline Host (`voice_runtime`)

#### File: `packages/voice_runtime/voice_runtime/execution/native.py`
Verify and optimize tool handlers for browser channel:
1. **WhatsApp Dispatch (`whatsapp_template_*` and `send_whatsapp_message`)**:
   - Both handlers already check:
     ```python
     contact = (
         self._snapshot.get("_resolved", {}).get("contact")
         or self._snapshot.get("contact_snapshot")
         or {}
     )
     raw_phone = (
         args.get("to")
         or contact.get("phone_number")
         or contact.get("phone_e164")
         or self._snapshot.get("target_snapshot", "")
     )
     ```
   - When running a browser session with a test phone number, the tool will automatically resolve `recipient` from `contact.phone_number` or `target_snapshot`.
2. **Callback Scheduling (`schedule_callback`)**:
   - Uses `contact_id = contact.get("id") or self._snapshot.get("contact_id")`.
   - Records the callback in the database linked to the contact.
3. **Prompt Variable Interpolation**:
   - `sanitize_contact_variables()` and temporal resolvers automatically populate `self.flow.state` with contact and ad fields so prompts like `{{ name }}` or `{{ query }}` interpolate naturally.

---

### 3. Frontend UI (`TestAgentModal.tsx`)

#### File: `apps/dashboard/src/app/TestAgentModal.tsx`
Enhance modal with contact selection and test configuration controls:

1. **Contact Mode Selector (Tabs / Segmented View)**:
   - **Mode A: "Existing Contact"**
     - Loads contacts via `useResource<{ contacts: ContactSummary[] }>("/contacts")`.
     - Dropdown / selection showing `Name · Phone · Business`.
     - Displays preview summary card of the selected contact's variables (`{{ name }}`, `{{ source }}`, `{{ query }}`).
     - Includes optional "WhatsApp Destination Override" input (defaulted to contact's phone number).
   - **Mode B: "Quick Custom Context"**
     - Test Phone Number input (E.164 formatted, e.g. `+917304058886`).
     - Test Contact Name input (e.g. `Omkar Pawar`).
     - Collapsible "Advanced Variables" section (e.g. `Query`: "E-commerce app", `Business`: "Acme Corp", `Source`: "LinkedIn").
2. **WhatsApp Integration Readiness Badge**:
   - Query `GET /api/v1/integrations` to check if a WhatsApp connection is active.
   - If active: shows green pill `WhatsApp Live Delivery Ready`.
   - If not active: shows muted pill `WhatsApp integration not connected (messages will simulate)`.
3. **Connecting & Connected States**:
   - Display active caller and contact info during the call:
     `Talking as: Omkar Pawar · +91 73040 58886 · WebRTC Active`.
4. **Post-Call Run Linkage**:
   - When call ends, offer a direct link: `View Run Details` and `View Contact Timeline` (if real contact was used).

---

## Verification & Testing Plan

### Automated Tests
1. **Unit Test in `tests/unit/test_browser_sessions.py`**:
   - Test creating browser session with `contact_id`:
     - Assert `run.contact_id == contact.id`
     - Assert `run.contact_snapshot["phone_number"] == contact.phone_number`
     - Assert `run.resolved_config["_resolved"]["contact"]["name"] == contact.name`
   - Test creating browser session with custom `phone_number` and `contact_variables`:
     - Assert synthetic contact snapshot contains phone and custom variables.
     - Assert `snapshot["target_snapshot"] == phone_number`.
2. **Runtime Tool Handler Test**:
   - Verify that when `whatsapp_template_*` is executed in `NativePipelineHost` with browser session snapshot, `recipient` is correctly resolved from `contact_snapshot.phone_number`.

### Manual End-to-End Verification
1. Open dashboard at `http://localhost:5173`.
2. Click **Test Agent** button in top bar.
3. Select agent `Ava @ Northstar Software Studio` or `Elevated Box agent`.
4. Select contact `Omkar Pawar (+917304058886)`.
5. Click **Start Test Call**.
6. Speak through browser mic: ask about pricing and portfolio catalog.
7. Agent triggers `#whatsapp_template_dialtone_followup`.
8. Verify that the WhatsApp message arrives on the actual phone number in real time while continuing conversation in browser.
9. End call and check `Run` details to confirm full exchange, transcript, and tool invocation recorded.
