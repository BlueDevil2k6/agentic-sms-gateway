# Android App Setup Guide

## Requirements

- Android 14 (API 34) or higher
- Google Play Services (required for FCM wake-up)
- A gateway server already running (see server setup)

---

## Installation

1. Download and install the APK on your Android device
2. Open the app — a setup wizard will guide you through the remaining steps

---

## Setup Wizard

### Step 1 — Set as Default SMS App

The app must be the default SMS app to intercept incoming messages.

- Tap **Set as Default** — this opens Android's Default Apps settings
- Select **Agentic SMS Gateway** as the SMS app
- Return to the setup wizard

> The app will not receive incoming SMS until this step is completed.

### Step 2 — Grant Permissions

The app requires the following permissions:

| Permission | Why |
|---|---|
| `RECEIVE_SMS` | Receive incoming SMS messages |
| `SEND_SMS` | Send outbound SMS on behalf of the agent |
| `READ_CONTACTS` | Resolve phone numbers to contact names |
| `READ_PHONE_STATE` | Detect SIM slot availability |
| `RECEIVE_BOOT_COMPLETED` | Restart the bridge service after reboot |

Tap **Grant Permissions** and accept each prompt.

### Step 3 — Battery Optimization

This is the most important step for reliable operation.

Android's Doze mode can restrict network access for background apps. Exempting the app ensures the WebSocket connection stays alive and FCM wake-ups are delivered promptly.

Tap **Exempt from Battery Optimization** — this opens the system battery settings for the app. Select **Unrestricted**.

> You can skip this step, but the bridge may experience delays of up to 15 minutes when waking from Doze. FCM will still deliver wake-ups, but with higher latency.

### Step 4 — Connect to Gateway Server

Enter your server details:

| Field | Example |
|---|---|
| Server URL | `wss://your-server.com:8765` |
| API Key | `sk-bridge-xxxxxxxxxxxxxxxx` |

Tap **Test Connection** — the app will attempt to connect and show a result:
- **Connected** — setup is complete
- **Connection refused** — check the server URL and that the server is running
- **Unauthorized** — check the API key

### Step 5 — Done

The app shows a status dashboard. All indicators should be green:

```
● Connected          wss://your-server.com
● Default SMS app    Yes
● Battery exempt     Yes
● FCM               Ready
● Last seen          Just now
```

---

## Status Dashboard

The main screen shows live bridge status at a glance:

| Indicator | Meaning |
|---|---|
| Connected / Disconnected | WebSocket connection to gateway server |
| Default SMS app | Whether the app is set as the system default |
| Battery exempt | Whether battery optimization is disabled |
| FCM Ready | Whether FCM wake-up is registered |
| Last activity | Timestamp of last message sent or received |
| Messages relayed | Total count since install |

---

## Notifications

The app shows a persistent foreground notification while the bridge is active:

```
SMS Bridge — Connected
Tap to open  ·  wss://your-server.com
```

This notification is required by Android to keep the background service alive. It cannot be dismissed while the bridge is running. You can minimise its appearance in Android notification settings (silent, no sound, collapsed).

---

## Multi-SIM Devices

If your device has two SIM cards, the gateway server can specify which SIM to use per message via the `sim_slot` field (0 or 1). The app defaults to SIM slot 0 if not specified.

The SIM slots available on the device are reported to the server in the `device.hello` message on connection.

---

## Troubleshooting

**Bridge disconnects frequently**
- Check that battery optimization is set to Unrestricted for the app
- Some manufacturer overlays (Samsung, Xiaomi, OPPO) have additional battery management beyond Android's standard Doze — check your device's own battery or app management settings for an additional "allow background activity" toggle

**Incoming SMS not forwarded**
- Confirm the app is set as the default SMS app (Step 1)
- Check the status dashboard — if WebSocket shows Disconnected, the app cannot forward messages

**Outbound SMS delayed**
- If the WebSocket is not connected, the gateway uses FCM to wake the app. FCM delivery is typically 1–3 seconds but can take longer on some networks
- If FCM shows "Not Ready" in the status dashboard, ensure Google Play Services is up to date

**App not starting after reboot**
- Grant the `RECEIVE_BOOT_COMPLETED` permission if prompted
- Some devices require the app to be opened at least once after reboot before auto-start is permitted — open the app manually once after the first reboot

---

## Security Notes

- The API key is stored in Android's `EncryptedSharedPreferences` — it is not accessible to other apps
- All WebSocket traffic is encrypted via TLS (`wss://`)
- FCM push payloads contain only a wake signal — no message content is sent through Google's infrastructure
- The app does not upload SMS content to any third-party service
