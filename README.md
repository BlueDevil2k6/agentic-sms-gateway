# Agentic SMS Gateway

An Android-based SMS bridge that lets AI agent frameworks (Hermes, OpenClaw, or any MCP-compatible agent) send and receive real SMS messages through a physical Android device.

## What It Does

The system has three components that work together:

```
Hermes / OpenClaw          SMS Gateway Server         Android Device
(AI Agent)                 (Python + MCP)             (SMS Bridge App)

send_sms() ──MCP──▶  queue outbound  ──WSS──▶  SmsManager ──SMS──▶ External
           ◀──MCP──  notify inbound  ◀──WSS──  SMS_DELIVER ◀──SMS── External
```

- **Android app** — runs as the default SMS app, maintains a persistent WebSocket connection to the gateway server, receives wake-up pushes via FCM when the connection is idle
- **Gateway server** — MCP server that exposes SMS as tools to AI agents; manages the WebSocket connection to the Android device and a file-based message queue
- **MCP integration** — agents connect via standard Model Context Protocol over SSE; no custom adapters or SDKs required

## Key Design Decisions

- **Android is the WebSocket client** — outbound connections only, works through any NAT or firewall
- **MCP over SSE** — standard protocol, compatible with Hermes, Claude, and any MCP-capable agent
- **FCM as wake-up fallback** — if the WebSocket is idle, the server sends an FCM high-priority push to reconnect the device before delivering a queued message
- **File-based queue** — inbound and outbound messages are stored as JSON files; simple, inspectable, zero extra dependencies
- **7-day retention** — completed messages are deleted after 7 days; failed messages are never auto-deleted

## Tech Stack

| Component | Technology |
|---|---|
| Gateway server | Python 3.11+, FastAPI, MCP SDK |
| WebSocket server | `websockets` (Android-facing) |
| MCP server | `mcp` SDK, SSE transport (agent-facing) |
| FCM push | `firebase-admin` |
| Message queue | File-based JSON (no database) |
| Deployment | Docker Compose |
| Android app | Kotlin, Jetpack Compose, OkHttp |
| Android keep-alive | Foreground Service, `PARTIAL_WAKE_LOCK` |
| Android wake-up | Firebase Cloud Messaging (FCM) |

## Repository Structure

```
agentic-sms-gateway/
├── server/                  Python SMS Gateway server
│   ├── src/sms_bridge/
│   │   ├── websocket/       WebSocket server (Android-facing)
│   │   ├── mcp/             MCP server (agent-facing)
│   │   ├── fcm/             FCM push notification client
│   │   ├── queue/           File-based message queue
│   │   └── router/          Core message routing logic
│   ├── docker-compose.yml
│   └── pyproject.toml
├── android/                 Android SMS Bridge app
│   └── app/
├── docs/
│   ├── architecture.md      System architecture and component overview
│   ├── flows.md             Inbound and outbound message flow diagrams
│   ├── mcp-integration.md   Connecting Hermes / OpenClaw
│   └── android-setup.md     Android app setup guide
└── README.md
```

## Quick Start

### 1. Run the gateway server

```bash
cd server
cp .env.example .env
# Edit .env — add your API key and FCM credentials
docker compose up -d
```

### 2. Connect the Android app

Install the Android app on your device, open it, and follow the setup wizard:
- Set as default SMS app
- Enter your server URL and API key
- Exempt from battery optimization when prompted

### 3. Connect your agent

Add the SMS bridge to your Hermes config:

```yaml
mcp_servers:
  sms-bridge:
    transport: sse
    url: https://your-server.com/mcp
    headers:
      Authorization: "Bearer sk-bridge-xxxxxxxx"
```

Your agent now has `send_sms`, `get_messages`, and `list_conversations` tools available.

## Documentation

- [Architecture](docs/architecture.md) — full system design and rationale
- [Message Flows](docs/flows.md) — inbound and outbound flow diagrams
- [MCP Integration](docs/mcp-integration.md) — connecting Hermes and OpenClaw
- [Android Setup](docs/android-setup.md) — device configuration guide

## Status

Early development. Not yet production-ready.
