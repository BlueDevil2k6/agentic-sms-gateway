# MCP Integration Guide

The SMS Gateway exposes a standard Model Context Protocol (MCP) server over SSE transport. Any MCP-compatible agent framework can connect to it with a simple configuration entry.

## Connection Details

| Setting | Value |
|---|---|
| Transport | SSE (Server-Sent Events) |
| URL | `https://your-server.com/mcp` |
| Auth | `Authorization: Bearer <api-key>` |
| Protocol | MCP 1.0 |

---

## Connecting Hermes

Add the following to your Hermes configuration:

```yaml
mcp_servers:
  sms-bridge:
    transport: sse
    url: https://your-server.com/mcp
    headers:
      Authorization: "Bearer sk-bridge-xxxxxxxx"
    tools:
      - send_sms
      - get_messages
      - list_conversations
      - list_devices
```

Hermes will automatically discover the available tools via MCP's tool listing handshake. No additional code or adapters required.

---

## Available Tools

### `send_sms`

Send an SMS message via the connected Android device.

**Input:**
```json
{
  "to":        "+14155551234",   // required — E.164 format
  "body":      "Message text",  // required
  "device_id": "my-phone"       // optional — omit if only one device connected
}
```

**Output:**
```json
{
  "message_id": "uuid",
  "status": "queued"
}
```

`status` will be `"queued"` if the device WebSocket is not currently open (message will be delivered once the device wakes via FCM). It will be `"sent"` if the WebSocket was live and the command was dispatched immediately.

---

### `get_messages`

Retrieve recent SMS messages from a specific phone number.

**Input:**
```json
{
  "from_number": "+14155551234",  // required
  "limit": 20                     // optional — default 20, max 100
}
```

**Output:**
```json
[
  {
    "id": "uuid",
    "direction": "inbound | outbound",
    "from": "+14155551234",
    "to": "+14155559999",
    "body": "Message text",
    "timestamp": "2026-05-20T14:33:10Z",
    "status": "done | pending | failed"
  }
]
```

---

### `list_conversations`

List recent SMS conversations, grouped by contact number.

**Input:**
```json
{
  "limit": 20   // optional — default 20
}
```

**Output:**
```json
[
  {
    "contact": "+14155551234",
    "last_message": "Yes, 3pm works for me.",
    "last_message_at": "2026-05-20T14:33:10Z",
    "direction": "inbound",
    "unread": true
  }
]
```

---

### `list_devices`

List connected Android devices and their current status.

**Input:** none

**Output:**
```json
[
  {
    "device_id": "my-gateway-phone",
    "name": "My Gateway Phone",
    "connected": true,
    "phone_numbers": ["+14155559999"],
    "android_version": 14,
    "last_seen": "2026-05-20T14:30:00Z"
  }
]
```

---

## Inbound SMS Notifications

When an SMS arrives on the Android device, the gateway pushes an MCP notification to all connected agents:

```json
{
  "method": "notifications/sms_received",
  "params": {
    "id": "uuid",
    "from": "+14155551234",
    "body": "Is the meeting still on?",
    "timestamp": "2026-05-20T14:33:10Z",
    "device_id": "my-gateway-phone"
  }
}
```

Agents that support MCP notifications will receive this in real time. Agents that poll instead can use `get_messages` or `list_conversations`.

---

## API Key Management

API keys are configured in the server's `.env` file. Generate a key:

```bash
python -c "import secrets; print('sk-bridge-' + secrets.token_hex(32))"
```

Set it in `.env`:
```
API_KEY=sk-bridge-xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
```

The same key is used in:
1. The Android app (Server URL + API Key fields in setup)
2. The agent framework config (`Authorization: Bearer ...` header)

---

## OpenClaw Integration

If OpenClaw supports MCP (SSE transport), the configuration follows the same pattern as Hermes. Consult OpenClaw's MCP integration documentation for the exact config key names.

If OpenClaw uses a different tool integration pattern (HTTP plugin, function calling config, etc.), the gateway's REST fallback endpoints are:

```
POST /api/sms/send          — send an SMS
GET  /api/sms/messages      — list messages
GET  /api/sms/conversations — list conversations
GET  /api/devices           — list devices
```

All REST endpoints accept the same `Authorization: Bearer <api-key>` header.
