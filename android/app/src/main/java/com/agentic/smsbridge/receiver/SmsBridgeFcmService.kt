package com.agentic.smsbridge.receiver

import android.util.Log
import com.agentic.smsbridge.data.BridgeRepository
import com.agentic.smsbridge.service.BridgeService
import com.google.firebase.messaging.FirebaseMessagingService
import com.google.firebase.messaging.RemoteMessage
import dagger.hilt.android.AndroidEntryPoint
import javax.inject.Inject

private const val TAG = "FcmService"

/**
 * Handles FCM messages from the gateway server.
 *
 * The server sends a high-priority data message with action="wake_connect"
 * when it has a queued outbound SMS and the WebSocket is not open.
 * FCM bypasses Doze mode and wakes this service.
 *
 * IMPORTANT: FCM payloads carry only the wake signal — never SMS content.
 */
@AndroidEntryPoint
class SmsBridgeFcmService : FirebaseMessagingService() {

    @Inject
    lateinit var repository: BridgeRepository

    override fun onMessageReceived(message: RemoteMessage) {
        val action = message.data["action"]
        Log.i(TAG, "FCM message received: action=$action")

        if (action == "wake_connect") {
            if (!repository.prefs.isConfigured()) {
                Log.w(TAG, "FCM wake received but app is not configured")
                return
            }
            Log.i(TAG, "FCM wake — starting BridgeService")
            BridgeService.start(applicationContext)
        }
    }

    override fun onNewToken(token: String) {
        Log.i(TAG, "FCM token refreshed")
        repository.prefs.saveFcmToken(token)
        // If the bridge is already connected, the token will be sent
        // in the next device.hello (on reconnect). For immediate update,
        // we could send a token refresh message over the open WebSocket,
        // but for simplicity we rely on the next reconnect.
    }
}
