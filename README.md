# Agentic SMS Gateway

Self-hosted SMS gateway for AI agents. Android app + Python MCP server — pair with a QR code, then give Hermes, OpenClaw, or any MCP-compatible agent the ability to send and receive real SMS. No carrier API required.

## How It Works

```
Hermes / OpenClaw          SMS Gateway Server         Android Device
(AI Agent)                 (Python + MCP)             (SMS Bridge App)

send_sms() ──MCP──▶  queue outbound  ──WSS──▶  SmsManager ──SMS──▶ External
           ◀──MCP──  notify inbound  ◀──WSS──  SMS_DELIVER ◀──SMS── External
```

- **Android app** — background bridge that maintains a persistent WebSocket connection to the gateway server; receives FCM wake-up pushes when idle. Does not need to be the default SMS app.
- **Gateway server** — Python MCP server that exposes SMS as tools to AI agents; manages device connections and a file-based message queue
- **MCP integration** — agents connect via standard Model Context Protocol over SSE; no custom adapters required

## Key Design Decisions

- **Android is the WebSocket client** — outbound connections only, works through any NAT or firewall
- **MCP over SSE** — standard protocol, compatible with Hermes, OpenClaw, Claude, and any MCP-capable agent
- **FCM as wake-up fallback** — if the WebSocket drops, the server sends an FCM high-priority push to reconnect before delivering a queued message
- **File-based queue** — inbound and outbound messages stored as JSON files; simple, inspectable, zero extra dependencies
- **7-day retention** — completed messages auto-deleted after 7 days; failed messages never auto-deleted

## Tech Stack

| Component | Technology |
|---|---|
| Gateway server | Python 3.10+, FastAPI, MCP SDK |
| WebSocket server | `websockets` (Android-facing) |
| MCP server | `mcp` SDK, SSE transport (agent-facing) |
| FCM push | `firebase-admin` |
| Message queue | File-based JSON (no database) |
| Deployment | pip install or Docker Compose |
| Android app | Kotlin, Jetpack Compose, OkHttp |
| Android keep-alive | Foreground Service, `PARTIAL_WAKE_LOCK` |
| Android wake-up | Firebase Cloud Messaging (FCM) |

## Quick Start

### 1. Install the gateway server

```bash
pip install git+https://github.com/BlueDevil2k6/agentic-sms-gateway.git#subdirectory=server
```

### 2. Run the setup wizard

```bash
sms-bridge setup
```

The wizard will ask for your server's hostname, ports, and (optionally) your FCM credentials. Everything is saved to `~/.config/sms-bridge/config.json`.

### 3. Start the server

```bash
sms-bridge start
```

### 4. Pair the Android app

Generate the device pairing QR code:

```bash
sms-bridge qr
```

Install the **SMS Bridge** Android app on your device, open it, and scan the QR code. The app connects automatically — no manual URL or key entry needed.

### 5. Connect your AI agent

Add the SMS bridge to your Hermes config:

```yaml
mcp_servers:
  sms-bridge:
    transport: sse
    url: https://your-server.com:8080/mcp
    headers:
      Authorization: "Bearer sk-bridge-xxxxxxxx"
```

Your agent now has `send_sms`, `get_messages`, `list_conversations`, and `list_devices` tools available.

## Updating

```bash
pip install --upgrade git+https://github.com/BlueDevil2k6/agentic-sms-gateway.git#subdirectory=server
```

## CLI Reference

| Command | Description |
|---|---|
| `sms-bridge setup` | Interactive configuration wizard |
| `sms-bridge start` | Start the gateway server |
| `sms-bridge qr` | Display Android pairing QR code in terminal |
| `sms-bridge qr --save` | Also save QR code as PNG |
| `sms-bridge status` | Show current configuration |
| `sms-bridge reset` | Delete saved configuration |

## Docker (alternative)

```bash
cd server
cp .env.example .env
# Edit .env — set API_KEY, WS_URL, and FCM_SERVICE_ACCOUNT_PATH
docker compose up -d
```

## Firebase / FCM Setup

FCM enables the server to wake the Android app when the WebSocket is idle. Without it, the app still works — it just needs to maintain an active connection.

1. Create a project at [console.firebase.google.com](https://console.firebase.google.com)
2. Add an Android app with package name `com.agentic.smsbridge`
3. Download `google-services.json` → place in `android/app/`
4. Go to **Project Settings → Service accounts → Generate new private key**
5. Save the JSON file and provide its path during `sms-bridge setup`

## Repository Structure

```
agentic-sms-gateway/
├── server/                  Python SMS Gateway server
│   ├── src/sms_bridge/
│   │   ├── cli.py           CLI entry point (setup / start / qr / status)
│   │   ├── config.py        Configuration dataclass
│   │   ├── config_store.py  ~/.config/sms-bridge/config.json manager
│   │   ├── websocket/       WebSocket server (Android-facing)
│   │   ├── mcp/             MCP server (agent-facing)
│   │   ├── fcm/             FCM push notification client
│   │   ├── queue/           File-based message queue
│   │   └── router/          Core message routing logic
│   ├── tests/               28 unit tests
│   ├── docker-compose.yml
│   └── pyproject.toml
├── android/                 Android SMS Bridge app (Kotlin + Compose)
│   └── app/
├── docs/
│   ├── architecture.md      System architecture and component overview
│   ├── flows.md             Inbound and outbound message flow diagrams
│   ├── mcp-integration.md   Connecting Hermes / OpenClaw
│   └── android-setup.md     Android app setup guide
└── README.md
```

## Documentation

- [Architecture](docs/architecture.md) — full system design and rationale
- [Message Flows](docs/flows.md) — inbound and outbound flow diagrams
- [MCP Integration](docs/mcp-integration.md) — connecting Hermes and OpenClaw
- [Android Setup](docs/android-setup.md) — device configuration guide

## License

MIT — see [LICENSE](LICENSE)
