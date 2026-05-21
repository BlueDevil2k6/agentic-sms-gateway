# SMS Bridge — Gateway Server

The Python server that sits between AI agents (via MCP) and an Android device (via WebSocket).

## Prerequisites

- Docker + Docker Compose, **or** Python 3.11+
- A Firebase project with Cloud Messaging enabled (for FCM wake-up)
- A domain name with a valid TLS certificate (for production)

---

## Quick Start (Docker)

```bash
# 1. Copy and fill in the config
cp .env.example .env
$EDITOR .env

# 2. Place your Firebase service account file here
cp ~/Downloads/my-project-firebase-adminsdk.json ./fcm-service-account.json

# 3. Start the server
docker compose up -d

# 4. Check it's running
curl http://localhost:8080/health
# → {"status": "ok", "devices_connected": 0}

# 5. Get the Android setup QR code
curl -H "Authorization: Bearer YOUR_API_KEY" \
     http://localhost:8080/setup/qr \
     --output setup.png
open setup.png    # scan this with the Android app
```

---

## Quick Start (Python / local dev)

```bash
# 1. Create a virtual environment
python -m venv .venv && source .venv/bin/activate

# 2. Install dependencies
pip install -e ".[dev]"

# 3. Copy and fill in the config
cp .env.example .env
$EDITOR .env   # at minimum: set API_KEY

# 4. Run
sms-bridge
```

---

## Configuration

All settings are in `.env`. Copy `.env.example` to get started.

| Variable | Required | Default | Description |
|---|---|---|---|
| `API_KEY` | **Yes** | — | Shared secret used by both the Android app and the agent framework |
| `WS_URL` | **Yes** | `ws://localhost:8765` | Public WebSocket URL embedded in the setup QR code |
| `MCP_PORT` | No | `8080` | Port for the MCP SSE server (agent-facing) |
| `WS_PORT` | No | `8765` | Port for the WebSocket server (Android-facing) |
| `FCM_SERVICE_ACCOUNT_PATH` | No | `/secrets/fcm-service-account.json` | Path to Firebase service account JSON |
| `DATA_DIR` | No | `data` | Directory for the file-based message queue |
| `MESSAGE_RETENTION_DAYS` | No | `7` | Days before completed messages are deleted |
| `MAX_SEND_ATTEMPTS` | No | `5` | Retry limit before a message moves to `failed/` |
| `LOG_LEVEL` | No | `INFO` | `DEBUG`, `INFO`, `WARNING`, `ERROR` |

### Generating an API key

```bash
python -c "import secrets; print('sk-bridge-' + secrets.token_hex(32))"
```

### Firebase setup

1. Go to [Firebase Console](https://console.firebase.google.com) → your project → Project Settings → Service Accounts
2. Click **Generate new private key** → download the JSON file
3. Place it at the path set in `FCM_SERVICE_ACCOUNT_PATH`

FCM is used only to send high-priority wake signals to the Android device when the WebSocket is not connected. No SMS content transits through Firebase.

---

## Endpoints

### Agent-facing (MCP)

| Endpoint | Method | Description |
|---|---|---|
| `/mcp` | GET | MCP SSE connection (agent connects here) |
| `/mcp/messages` | POST | MCP message endpoint |
| `/health` | GET | Health check — no auth required |
| `/setup/qr` | GET | Setup QR code PNG — requires `Authorization: Bearer <key>` |

### MCP Tools exposed to agents

| Tool | Description |
|---|---|
| `send_sms(to, body, device_id?)` | Queue an outbound SMS |
| `get_messages(from_number, limit?)` | Get recent messages from a number |
| `list_conversations(limit?)` | List recent conversation threads |
| `list_devices()` | List connected Android devices |

---

## Connecting Hermes

Add to your Hermes config:

```yaml
mcp_servers:
  sms-bridge:
    transport: sse
    url: http://your-server.com:8080/mcp
    headers:
      Authorization: "Bearer YOUR_API_KEY"
```

See [../docs/mcp-integration.md](../docs/mcp-integration.md) for full details.

---

## Data Directory

```
data/
├── outbound/
│   ├── pending/     Queued by agent, waiting for Android
│   ├── sending/     Dispatched to Android, awaiting confirmation
│   ├── done/        Confirmed sent — auto-deleted after 7 days
│   └── failed/      Max retries exceeded — never auto-deleted
├── inbound/
│   ├── pending/     Received from Android, agent not yet notified
│   ├── processing/  MCP notification in flight
│   ├── done/        Agent received it — auto-deleted after 7 days
│   └── failed/      Not consumed within 7 days — never auto-deleted
└── fcm_tokens.json  Persisted FCM tokens (survives server restarts)
```

Inspect the queue at any time with standard file tools:

```bash
ls -la data/outbound/pending/     # see queued messages
cat data/outbound/failed/*.json   # inspect failures
ls data/inbound/done/ | wc -l     # count processed inbound messages
```

---

## Running Tests

```bash
pip install -e ".[dev]"
pytest
```

---

## Production Checklist

- [ ] `WS_URL` set to `wss://` (not `ws://`)
- [ ] TLS certificate on your domain (Let's Encrypt works)
- [ ] `API_KEY` is a long random secret (not the example value)
- [ ] FCM service account file in place
- [ ] `data/` directory on a persistent volume (not ephemeral container storage)
- [ ] Firewall: port 8080 open for agent traffic, port 8765 open for Android device
