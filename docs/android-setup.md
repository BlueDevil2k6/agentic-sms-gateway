# Android App Setup Guide

## Requirements

- Android 14 (API 34) or higher
- Google Play Services (required for FCM wake-up)
- A gateway server already running (see server setup)
- A SIM card in the device

> **Note:** This app does **not** need to be set as the default SMS app. It runs as a background bridge alongside your existing messaging app.

---

## Get the Setup QR Code

On your gateway server, open a browser and navigate to:

```
https://your-server.com/setup/qr
```

You will be prompted for your API key. The page returns a QR code PNG — keep this on screen or print it.

> Treat the QR code like a password. It contains your API key. Do not screenshot or share it.

---

## Installation

1. Install the APK on your Android device
2. Open the app — you will see the QR scanner immediately

---

## Setup (takes about 60 seconds)

### Step 1 — Scan QR Code

Point the camera at the QR code from your server. The app detects it automatically — no button to tap.

If the camera is unavailable, tap **Enter manually** to type the server URL and API key directly.

### Step 2 — Grant Permissions

The app requests three permissions:

| Permission | Why |
|---|---|
| Receive SMS | Forward incoming messages to the server |
| Send SMS | Deliver outbound messages from the server |
| Start on boot | Restart the bridge automatically after reboot |

All three are required. If a permission is denied, the app explains how to grant it from Android Settings.

### Step 3 — Battery Optimisation

Tap **Disable battery optimisation** and select **Unrestricted** in the system dialog.

This prevents Android from suspending the app's network connection during Doze mode. You can skip this step — the FCM fallback will still wake the app when needed, but with slightly higher latency (a few extra seconds).

### Done

The app shows the Status Dashboard with green indicators. The bridge is active.

---

## Status Dashboard

```
●  Connected          wss://your-server.com
●  SMS permissions    Granted
●  FCM                Ready
⚠  Battery exempt     Not set  [Fix →]

Inbound forwarded     142
Outbound sent          87
Last activity       2 min ago
```

| Indicator | What it means |
|---|---|
| Connected (green) | WebSocket open, bridge is live |
| Reconnecting (amber) | Temporary disconnect, retrying |
| Disconnected (red) | Cannot reach server |
| SMS permissions (red) | Receive or Send SMS permission was revoked |
| FCM (green) | Wake-up push notifications are working |
| Battery exempt (amber) | App may be delayed by Doze — tap Fix to resolve |

---

## Settings

Tap the gear icon on the Status Dashboard.

- **Re-scan QR code** — update server connection (e.g. after API key rotation)
- **Device name** — the label shown in the server's device registry
- **Battery optimisation** — shortcut to the system setting
- **Disconnect and reset** — wipes stored credentials, stops the bridge, returns to QR scanner

---

## Troubleshooting

**Bridge disconnects repeatedly**
- Go to Settings → Battery → App battery usage → find this app → set to Unrestricted
- Some manufacturers (Samsung, Xiaomi, OPPO) have additional background app controls beyond standard Android — check your device's own battery or app management settings

**Incoming SMS not forwarded**
- Confirm the `Receive SMS` permission is granted (Settings → Permissions)
- Some default SMS apps abort the `SMS_RECEIVED` broadcast before it reaches this app — this is rare with Google Messages or Samsung Messages but possible with third-party SMS apps

**Outbound SMS not delivered**
- Check the gateway server's `outbound/failed/` directory for error details
- Confirm the `Send SMS` permission is granted

**App not restarting after reboot**
- Confirm the `Start on boot` permission is granted
- On some devices, you must open the app manually once after the first reboot before auto-start is permitted

**QR code not detected**
- Ensure the QR code fills most of the viewfinder
- Try better lighting
- Use the **Enter manually** fallback if needed

---

## Known Limitations

- **SMS_RECEIVED ordering:** The bridge listens on the `SMS_RECEIVED` broadcast, which is delivered to all apps with the permission. If another SMS app on the device aborts this broadcast first, the bridge will not see the message. This is uncommon with modern SMS apps. Using the device as a dedicated gateway (with no competing SMS apps) eliminates this entirely.
- **MMS:** Not supported in this version. Only SMS is bridged.
- **Self-signed TLS certificates:** The app uses Android's default CA trust store. Self-signed server certificates are not supported in this version.
