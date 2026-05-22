package com.agentic.smsbridge.service

import android.app.PendingIntent
import android.content.BroadcastReceiver
import android.content.Context
import android.content.Intent
import android.content.IntentFilter
import android.os.Build
import android.telephony.SmsManager
import android.util.Log
import com.agentic.smsbridge.data.BridgeRepository
import com.agentic.smsbridge.model.OutboundMessage
import dagger.hilt.android.qualifiers.ApplicationContext
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.launch
import javax.inject.Inject
import javax.inject.Singleton

private const val TAG = "SmsHandler"
private const val ACTION_SMS_SENT      = "com.agentic.smsbridge.SMS_SENT"
private const val ACTION_SMS_DELIVERED = "com.agentic.smsbridge.SMS_DELIVERED"
private const val EXTRA_MESSAGE_ID     = "message_id"

@Singleton
class SmsHandler @Inject constructor(
    @ApplicationContext private val context: Context,
    private val repository: BridgeRepository,
) {
    private val scope = CoroutineScope(Dispatchers.IO)

    /**
     * Send an SMS and report status back to the server via BridgeRepository.
     *
     * @param messageId  The server-assigned ID from the sms.send command
     * @param to         Destination phone number (E.164)
     * @param body       SMS text content
     */
    fun sendSms(messageId: String, to: String, body: String) {
        val smsManager = if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.S) {
            context.getSystemService(SmsManager::class.java)
        } else {
            @Suppress("DEPRECATION")
            SmsManager.getDefault()
        }

        val sentIntent = buildStatusIntent(ACTION_SMS_SENT, messageId)
        val deliveredIntent = buildStatusIntent(ACTION_SMS_DELIVERED, messageId)

        // Register one-shot receivers
        registerStatusReceiver(ACTION_SMS_SENT, messageId, "sent")
        registerStatusReceiver(ACTION_SMS_DELIVERED, messageId, "delivered")

        try {
            // SMS body > 160 chars needs to be split into multi-part
            val parts = smsManager.divideMessage(body)
            if (parts.size == 1) {
                smsManager.sendTextMessage(to, null, body, sentIntent, deliveredIntent)
            } else {
                val sentIntents     = ArrayList(List(parts.size) { if (it == 0) sentIntent else null })
                val deliveredIntents = ArrayList(List(parts.size) { if (it == parts.size - 1) deliveredIntent else null })
                smsManager.sendMultipartTextMessage(to, null, parts, sentIntents, deliveredIntents)
            }
            Log.i(TAG, "SMS queued to $to (id=$messageId)")
        } catch (e: Exception) {
            Log.e(TAG, "Failed to send SMS to $to: ${e.message}")
            reportStatus(messageId, "failed", e.message)
        }
    }

    // ── Status reporting ──────────────────────────────────────────────────

    private fun buildStatusIntent(action: String, messageId: String): PendingIntent {
        val intent = Intent(action).apply {
            setPackage(context.packageName)
            putExtra(EXTRA_MESSAGE_ID, messageId)
        }
        return PendingIntent.getBroadcast(
            context,
            messageId.hashCode(),
            intent,
            PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_IMMUTABLE,
        )
    }

    private fun registerStatusReceiver(action: String, messageId: String, status: String) {
        val receiver = object : BroadcastReceiver() {
            override fun onReceive(ctx: Context, intent: Intent) {
                ctx.unregisterReceiver(this)
                val id = intent.getStringExtra(EXTRA_MESSAGE_ID) ?: messageId
                when (resultCode) {
                    android.app.Activity.RESULT_OK -> reportStatus(id, status)
                    else -> reportStatus(id, "failed", "resultCode=$resultCode")
                }
            }
        }
        val filter = IntentFilter(action)
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.TIRAMISU) {
            context.registerReceiver(receiver, filter, Context.RECEIVER_NOT_EXPORTED)
        } else {
            context.registerReceiver(receiver, filter)
        }
    }

    private fun reportStatus(messageId: String, status: String, error: String? = null) {
        Log.i(TAG, "SMS status: id=$messageId status=$status error=$error")
        scope.launch {
            repository.sendToServer(
                OutboundMessage.SmsStatus(
                    refId  = messageId,
                    status = status,
                    error  = error,
                )
            )
        }
        if (status == "sent") {
            repository.incrementOutbound()
        }
    }
}
