package com.agentic.smsbridge.receiver

import android.content.BroadcastReceiver
import android.content.Context
import android.content.Intent
import android.provider.Telephony
import android.util.Log
import com.agentic.smsbridge.data.BridgeRepository
import com.agentic.smsbridge.model.OutboundMessage
import dagger.hilt.android.AndroidEntryPoint
import javax.inject.Inject

private const val TAG = "SmsReceiver"

/**
 * Receives incoming SMS via the SMS_RECEIVED broadcast.
 *
 * Does NOT require the app to be the default SMS app.
 *
 * Note: SMS_RECEIVED is an ordered broadcast. If another app (the default SMS app)
 * aborts it before we receive it, we won't see the message. Modern default apps
 * (Google Messages, Samsung Messages) do not abort this broadcast.
 */
@AndroidEntryPoint
class SmsReceiver : BroadcastReceiver() {

    @Inject
    lateinit var repository: BridgeRepository

    override fun onReceive(context: Context, intent: Intent) {
        Log.d(TAG, "onReceive: action=${intent.action}")
        if (intent.action != Telephony.Sms.Intents.SMS_RECEIVED_ACTION &&
            intent.action != Telephony.Sms.Intents.SMS_DELIVER_ACTION) return

        // goAsync() extends our processing window so we can do async work
        // without the system reclaiming the WakeLock before we finish.
        val pendingResult = goAsync()

        try {
            val messages = Telephony.Sms.Intents.getMessagesFromIntent(intent)
            if (messages.isNullOrEmpty()) {
                pendingResult.finish()
                return
            }

            // Multi-part SMS arrives as multiple SmsMessage objects with the same
            // originating address. Join them into a single body.
            val from = messages[0].originatingAddress ?: "unknown"
            val body = messages.joinToString("") { it.messageBody ?: "" }

            Log.i(TAG, "SMS received from $from (${body.length} chars)")

            val deviceId = repository.prefs.getConfig()?.deviceId ?: "unknown"
            val message = OutboundMessage.SmsReceived(
                from     = from,
                body     = body,
                deviceId = deviceId,
            )

            Log.d(TAG, "Forwarding to repository: $message")
            repository.sendToServerBlocking(message)
            repository.incrementInbound()
            Log.d(TAG, "Inbound count incremented")

        } catch (e: Exception) {
            Log.e(TAG, "Error processing SMS: ${e.message}")
        } finally {
            pendingResult.finish()
        }
    }
}
