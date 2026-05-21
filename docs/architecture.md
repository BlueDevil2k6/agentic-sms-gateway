# System Architecture

## Overview

Agentic SMS Gateway bridges AI agent frameworks and real-world SMS through a physical Android device. The system has three layers:

1. **Android SMS Bridge App** — the physical SMS gateway
2. **SMS Gateway Server** — the coordination layer
3. **MCP Interface** — the agent integration layer

```
┌────────────────────────────────────────────────────────────────┐
│  AI Agent (Hermes / OpenClaw / Claude)                         │
│                                                                │
│  Uses MCP tools: send_sms, get_messages, list_conversations    │
└────────────────────────────┬───────────────────────────────────┘
                             │  MCP over SSE (HTTPS)
                             │  Authorization: Bearer <api-key>
┌────────────────────────────▼───────────────────────────────────┐
│  SMS Gateway Server                                            │
│                                                                │
│  ┌──────────────────┐   ┌───────────────────────────────────┐  │
│  │  MCP Server      │   │  WebSocket Server                 │  │
│  │  (agent-facing)  │   │  (Android-facing)                 │  │
│  │                  │   │                                   │  │
│  │  SSE transport   │   │  wss://:8765                      │  │
│  │  Tools +         │   │  API key validated on connect     │  │
│  │  Notifications   │   │  Heartbeat ping every 30s         │  │
│  └────────┬─────────┘   └──────────────┬────────────────────┘  │
│           │                            │                        │
│  ┌────────▼────────────────────────────▼────────────────────┐  │
│  │                   Message Router                         │  │
│  │                                                          │  │
│  │  • Device registry  { device_id → ws_connection,        │  │
│  │                        fcm_token }                       │  │
│  │  • Outbound queue   (file-based, with FCM fallback)     │  │
│  │  • Inbound queue    (file-based, MCP notification push)  │  │
│  │  • Retry logic      (exponential backoff, 7-day expiry) │  │
│  └───────────────────────────────────────────────────────────┘  │
│                                                                │
│  ┌───────────────────────────────────────────────────────────┐  │
│  │  FCM Client  (firebase-admin)                            │  │
│  │  Sends high-priority wake push if WebSocket is not open  │  │
│  └───────────────────────────────────────────────────────────┘  │
└────────────────────────────┬───────────────────────────────────┘
                             │  WSS (WebSocket Secure)
                             │  + FCM high-priority push (fallback)
┌────────────────────────────▼───────────────────────────────────┐
│  Android Device                                                │
│                                                                │
│  ┌───────────────────────────────────────────────────────────┐  │
│  │  BridgeService  (Foreground Service)                     │  │
│  │  • Maintains persistent WebSocket connection             │  │
│  │  • Holds PARTIAL_WAKE_LOCK                               │  │
│  │  • Reconnects with exponential backoff on drop           │  │
│  │  • Sends device.hello on connect (registers FCM token)   │  │
│  └───────────────────────────────────────────────────────────┘  │
│                                                                │
│  ┌───────────────────────────────────────────────────────────┐  │
│  │  SmsReceiver  (BroadcastReceiver)                        │  │
│  │  • Woken by OS via SMS_DELIVER (default SMS app only)    │  │
│  │  • Uses goAsync() to extend processing window           │  │
│  │  • Forwards incoming SMS to BridgeService → WebSocket    │  │
│  └───────────────────────────────────────────────────────────┘  │
│                                                                │
│  ┌───────────────────────────────────────────────────────────┐  │
│  │  FcmService  (FirebaseMessagingService)                  │  │
│  │  • Receives FCM high-priority wake push                  │  │
│  │  • Starts BridgeService if not running                   │  │
│  │  • Does NOT carry SMS content — wake signal only         │  │
│  └───────────────────────────────────────────────────────────┘  │
│                                                                │
│  ┌───────────────────────────────────────────────────────────┐  │
│  │  SmsManager  (Android API)                               │  │
│  │  • Executes outbound SMS send on BridgeService command   │  │
│  │  • Reports delivery status back via WebSocket            │  │
│  └───────────────────────────────────────────────────────────┘  │
└────────────────────────────────────────────────────────────────┘
```

---

## Why Android Is the WebSocket Client

The Android device initiates the WebSocket connection to the server — not the other way around. This is a deliberate choice:

- Android devices sit behind carrier-grade NAT and cannot accept inbound connections
- Outbound connections work through any firewall or network
- The server has a stable hostname and valid TLS certificate
- This matches the same pattern used by every mobile app connecting to a backend

---

## Connection Keep-Alive Stack

Android aggressively kills background processes to save battery. The app uses a full keep-alive stack:

| Mechanism | Purpose |
|---|---|
| Foreground Service | Elevates process priority; Android will not kill it |
| `PARTIAL_WAKE_LOCK` | Keeps CPU active when screen is off |
| Battery optimization exemption | Exempts app from Doze mode network restrictions |
| WebSocket ping every 30s | Keeps NAT tables and firewalls from dropping the connection |
| Exponential backoff reconnect | Recovers from network drops (2s, 4s, 8s, 16s, 30s cap) |
| `BOOT_COMPLETED` receiver | Restarts BridgeService after device reboot |
| FCM fallback | Wakes a killed/idle app when the server has a queued message |

---

## Message Queue

Messages are stored as JSON files on the server filesystem. No database required.

```
data/
├── outbound/
│   ├── pending/     Queued by agent, waiting for Android
│   ├── sending/     Android has it, SMS dispatch in progress
│   ├── done/        Confirmed sent — deleted after 7 days
│   └── failed/      Max retries exceeded — never auto-deleted
└── inbound/
    ├── pending/     Received from Android, agent not yet notified
    ├── processing/  MCP notification in flight
    ├── done/        Agent acknowledged — deleted after 7 days
    └── failed/      Agent never consumed — never auto-deleted
```

File naming: `{unix_timestamp_ms}_{message_id}.json`
Timestamp prefix ensures natural chronological ordering via `ls`.

Atomic state transitions use `os.rename()`, which is atomic on POSIX filesystems. A message cannot be claimed by two processes simultaneously.

---

## Authentication

**Android → Server (WebSocket):**
API key sent in the HTTP upgrade request header:
```
Authorization: Bearer sk-bridge-xxxxxxxx
```

**Agent → Server (MCP/SSE):**
Same API key, same header format. Keys are generated on the server and configured in both the Android app and the agent framework.

**Server → Android (FCM):**
FCM uses a Firebase service account for server-to-server auth. The FCM payload carries only a wake signal — no message content transits through Google's infrastructure.

---

## Tech Stack

| Concern | Technology | Rationale |
|---|---|---|
| Agent protocol | MCP over SSE | Universal standard; Hermes, Claude, and most modern frameworks support it |
| Android ↔ Server | WebSocket (WSS) | Full-duplex; server can push commands; works through NAT |
| Wake-up fallback | FCM high-priority | Bypasses Doze; works even if app is killed |
| Server language | Python 3.11+ | MCP SDK is Python-first; matches AI framework ecosystem |
| Message storage | File-based JSON | Zero dependencies; fully inspectable; crash-safe via atomic rename |
| Deployment | Docker Compose | Single command; no infrastructure prerequisites |
| Android language | Kotlin + Jetpack Compose | Modern Android stack |
| Min Android version | API 34 (Android 14) | `foregroundServiceType="connectedDevice"` is well-supported |
