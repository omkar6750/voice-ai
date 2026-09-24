---
id: RFC-0011
title: Runtime endpoints, hardware modem status, and reconciliation surface
status: Proposed
version: 1
date: 2026-09-23
authored_by: omkar
related: [RFC-0001, RFC-0002, RFC-0003, RFC-0004, RFC-0006]
---

# RFC-0011 · Runtime endpoints, hardware modem status, and reconciliation surface

## Implementation amendment, 2026-09-24

- Endpoint config currently supports SIM7600 only. SIP/WebRTC, endpoint list/detail/edit, live status and global reconciliation need backend work.
- Claim ownership lives on Run, not runtime_endpoints. Clearing a database lease cannot stop worker or modem call. Remove force-release behavior.
- Recovery: request stop, verify worker stopped and transport idle, then reconcile uncertain run or recover endpoint through existing verified routes. Never blindly redial. Diagnostics use owner runtime snapshot during active call, not a competing AT session.

## 1. Context

The initial voice path runs on a local SIM7600 endpoint with AT and raw USB PCM serial ports. SIP/WebRTC transport adapters are future work.

The run claim fences access to a physical endpoint. A stale claim requires verified worker and hardware state before recovery; database state alone cannot prove the modem idle.

## 2. Goals

- Provide a live **Runtime Endpoints Dashboard** for configured SIM7600 hardware. Future transports can join after their adapters exist.
- Display real-time endpoint status (`idle`, `busy`, `recovering`, `offline`), current active `run_id`, lease owner, and heartbeat time.
- Provide a dedicated **Operator Reconciliation Surface** for detecting orphaned runs, stale leases, and hardware errors.
- Support administrative manual actions:
  - Inspect run claims and request an orderly stop.
  - Inspect allowlisted modem status and signal checks through the owning runtime.
  - Reconcile an uncertain run after worker-stopped and transport-idle verification.

## 3. Non-Goals

- Direct raw shell terminal access into remote worker servers from the browser.
- Modifying physical hardware firmware directly via the browser dashboard.

## 4. Routes

- `/endpoints` — Runtime endpoints list with live status indicators, lease table, and quick actions.
- `/endpoints/:endpointId` — Hardware details, AT command logs, audio interface bindings, and historical run assignments.
- `/endpoints/reconciliation` — Operator reconciliation queue, stale lock detection, and manual cleanup tools.

## 5. API Dependencies

### Consumed Existing APIs
- `POST /api/v1/runtime-endpoints` — Register a SIM7600 endpoint.
- `POST /api/v1/runtime-endpoints/{id}/recover` — Recover after verified transport release.
- `POST /api/v1/runs/{run_id}/reconcile` — Resolve an uncertain run after required verification.

### Required Backend / API Additions
- `GET /api/v1/runtime-endpoints` and `GET /api/v1/runtime-endpoints/{id}` — List/detail for the dashboard.
- `PATCH /api/v1/runtime-endpoints/{id}` — Revision-checked configuration editing.
- An orderly stop request and status snapshot from the owning runtime.
- `GET /api/v1/runtime-endpoints/{id}/modem-diagnostics` — Fetch cellular signal strength (CSQ), network registration (CREG/CGREG), carrier info, and audio device status.
- Diagnostic audio test only after transport availability and safety are established.

## 6. Layout & Feature Components

### 6.1 Endpoints Grid & Lease Monitor
```text
┌────────────────────────────────────────────────────────────────────────┐
│ Runtime Endpoints & Telephony Hardware            [+ Register Endpoint] │
│ Auto-refreshing every 5s                                               │
├────────────────────────────────────────────────────────────────────────┤
│ ┌───────────────────────────┐ ┌───────────────────────────┐           │
│ │ SIM7600_COM9_PORT         │ │ SIP_GATEWAY_US_EAST       │           │
│ │ Status: [● IDLE]          │ │ Status: [● BUSY]          │           │
│ │ Carrier: Jio 4G VoLTE     │ │ Active Run: #run_98231    │           │
│ │ Signal: -73 dBm (31/31)   │ │ Lease Owner: worker-node-2│           │
│ │ Audio: AudioBox USB 96    │ │ Expires In: 04:12         │           │
│ │ [Test Dial] [Diagnostics] │ │ [View Run] [Recovery]     │           │
│ └───────────────────────────┘ └───────────────────────────┘           │
├────────────────────────────────────────────────────────────────────────┤
│ Operator Reconciliation & Stale Lock Monitor                          │
│ ┌────────────────────────────────────────────────────────────────────┐ │
│ │ 0 orphaned runs detected. All hardware leases healthy.             │ │
│ │ [Run Manual Reconciliation Pass]                                   │ │
│ └────────────────────────────────────────────────────────────────────┘ │
└────────────────────────────────────────────────────────────────────────┘
```

### 6.2 Key Components
- `EndpointCard`: Status dot, carrier name, signal bar icon, SIM7600 transport badge, and action menu.
- `LeaseStatusBadge`: Displays lock ownership, TTL countdown, and visual warning when a lease is expiring or orphaned.
- `ModemDiagnosticsDialog`: Modal showing live signal strength, SIM IMSI/ICCID (masked), VoLTE status, and recent AT commands (`AT+CSQ`, `AT+CPIN?`, `AT+COPS?`).
- `ReconciliationBanner`: High-visibility alert bar displayed if orphaned runs or deadlocked modems are detected across the workspace.

## 7. User Interactions & Safety Gates

1. **Recovering an uncertain run**:
   - Operator requests an orderly stop and checks the worker and modem.
   - Only after worker-stopped and transport-idle verification may the operator reconcile the uncertain run. The API records verification and outcome.
2. **Diagnosing a Modem**:
   - Operator opens Diagnostics to check if a SIM card is disconnected or signal is degraded before queuing batch calls.
