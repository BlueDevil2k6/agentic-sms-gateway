# Message Flows

## INBOUND — External → Android → Gateway → Agent

An external phone number sends an SMS to the Android device. The gateway receives it and notifies the AI agent via MCP.

```
External phone
  │
  │  SMS (cellular)
  ▼
Android Device
  [OS delivers SMS_DELIVER broadcast to default SMS app]
  [SmsReceiver.onReceive() called — goAsync() extends window]
  │
  │  WebSocket  →  sms.received event
  │  {
  │    "id": "uuid",
  │    "type": "sms.received",
  │    "from": "+14155551234",
  │    "body": "Is the meeting still on?",
  │    "device_id": "my-gateway-phone",
  │    "ts": 1716192000000
  │  }
  ▼
SMS Gateway Server
  [writes to  inbound/pending/{ts}_{id}.json]
  [pushes MCP notification to connected agent]
  │
  │  MCP notification  →  notifications/sms_received
  │  {
  │    "from": "+14155551234",
  │    "body": "Is the meeting still on?",
  │    "timestamp": 1716192000000,
  │    "device_id": "my-gateway-phone"
  │  }
  │  [moves file:  pending/ → processing/]
  ▼
Hermes / OpenClaw Agent
  [agent reacts — reads context, decides on a reply]
  [calls send_sms tool if a response is needed]
  │
  [Gateway receives agent acknowledgement]
  [moves file:  processing/ → done/]
```

**Inbound queue states:**

| File location | Meaning |
|---|---|
| `inbound/pending/` | Received from Android; agent not yet notified |
| `inbound/processing/` | MCP notification sent; awaiting agent acknowledgement |
| `inbound/done/` | Agent processed it — auto-deleted after 7 days |
| `inbound/failed/` | Agent never consumed within 7 days — manual review |

---

## OUTBOUND — Agent → Gateway → Android → External

The AI agent wants to send an SMS to an external phone number.

```
Hermes / OpenClaw Agent
  [calls send_sms MCP tool]
  │
  │  MCP tool call
  │  send_sms(to="+14155558888", body="Yes, 3pm still works.")
  ▼
SMS Gateway Server
  [writes to  outbound/pending/{ts}_{id}.json]
  │
  ├── Is WebSocket connection open for this device?
  │
  │   YES (fast path — ~milliseconds)
  │   │
  │   │  WebSocket  →  sms.send
  │   │  [moves file:  pending/ → sending/]
  │   │
  │   NO (FCM wake path — ~1-3 seconds)
  │   │
  │   └── Send FCM high-priority push to device FCM token
  │       payload: { "action": "wake_connect" }
  │       [no SMS content in FCM payload]
  │       │
  │       ▼
  │       Android wakes (FCM bypasses Doze mode)
  │       BridgeService starts, opens WebSocket
  │       sends device.hello to Gateway
  │       │
  │       Gateway sees WebSocket reconnect
  │       scans outbound/pending/ for this device_id
  │       [atomic rename:  pending/ → sending/]
  │       │
  │       WebSocket  →  sms.send
  │
  ▼
Android Device
  [BridgeService receives sms.send]
  [SmsManager.sendTextMessage() called]
  │
  │  SMS (cellular)
  ▼
External phone
  │
  [Android receives delivery report from carrier]
  │
  │  WebSocket  →  sms.status
  │  {
  │    "type": "sms.status",
  │    "ref_id": "original-message-uuid",
  │    "status": "delivered"
  │  }
  ▼
SMS Gateway Server
  [moves file:  sending/ → done/]
  [auto-deleted after 7 days]
```

**Outbound queue states:**

| File location | Meaning |
|---|---|
| `outbound/pending/` | Queued by agent; Android not yet reached |
| `outbound/sending/` | Android received it; SMS dispatch in progress |
| `outbound/done/` | Confirmed sent by Android — auto-deleted after 7 days |
| `outbound/failed/` | Max retries exceeded or expired — manual review, never auto-deleted |

---

## FCM Wake Sequence (Detail)

FCM is only used as a wake-up signal — never to carry SMS content.

```
Gateway: WebSocket not open
  │
  └── POST https://fcm.googleapis.com/v1/projects/{id}/messages:send
      Authorization: Bearer {firebase-service-account-token}
      {
        "message": {
          "token": "{device-fcm-token}",
          "android": { "priority": "HIGH" },
          "data": { "action": "wake_connect" }
        }
      }
      │
      FCM delivers to Android (bypasses Doze)
      │
      FcmService.onMessageReceived() fires
      │
      Starts BridgeService (if not running)
      BridgeService opens WebSocket to Gateway
      Sends device.hello
      │
      Gateway: WebSocket now open
      Dequeues pending/ messages for this device_id
      Pushes via WebSocket as normal
```

---

## WebSocket Message Reference

### Android → Gateway

```json
// Device registration (sent on every connect)
{ "type": "device.hello", "id": "uuid", "ts": 0,
  "device_name": "My Gateway Phone",
  "android_version": 14,
  "phone_numbers": ["+14155559999"],
  "fcm_token": "fcm-token-string" }

// Incoming SMS
{ "type": "sms.received", "id": "uuid", "ts": 0,
  "from": "+14155551234",
  "body": "Message text",
  "device_id": "my-gateway-phone" }

// Delivery status
{ "type": "sms.status", "id": "uuid", "ts": 0,
  "ref_id": "original-send-message-uuid",
  "status": "sent | delivered | failed",
  "error": null }
```

### Gateway → Android

```json
// Send an SMS
{ "type": "sms.send", "id": "uuid", "ts": 0,
  "to": "+14155558888",
  "body": "Your appointment is confirmed.",
  "sim_slot": 0 }

// Heartbeat
{ "type": "ping", "id": "uuid", "ts": 0 }
```
