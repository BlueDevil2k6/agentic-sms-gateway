package com.agentic.smsbridge.model

import org.json.JSONObject
import java.util.UUID

/** Messages sent from Android → Server over WebSocket */
sealed class OutboundMessage {
    abstract fun toJson(): String

    /** Sent once on WebSocket connect to register the device */
    data class DeviceHello(
        val deviceId: String,
        val deviceName: String,
        val fcmToken: String,
        val androidVersion: Int = android.os.Build.VERSION.SDK_INT,
    ) : OutboundMessage() {
        override fun toJson(): String = JSONObject().apply {
            put("type",            "device.hello")
            put("id",              UUID.randomUUID().toString())
            put("ts",              System.currentTimeMillis())
            put("device_id",       deviceId)
            put("device_name",     deviceName)
            put("fcm_token",       fcmToken)
            put("android_version", androidVersion)
        }.toString()
    }

    /** Forwarded incoming SMS */
    data class SmsReceived(
        val from: String,
        val body: String,
        val deviceId: String,
    ) : OutboundMessage() {
        override fun toJson(): String = JSONObject().apply {
            put("type",      "sms.received")
            put("id",        UUID.randomUUID().toString())
            put("ts",        System.currentTimeMillis())
            put("from",      from)
            put("body",      body)
            put("device_id", deviceId)
        }.toString()
    }

    /** Delivery status report for an outbound SMS */
    data class SmsStatus(
        val refId: String,
        val status: String,   // "sent" | "delivered" | "failed"
        val error: String? = null,
    ) : OutboundMessage() {
        override fun toJson(): String = JSONObject().apply {
            put("type",   "sms.status")
            put("id",     UUID.randomUUID().toString())
            put("ts",     System.currentTimeMillis())
            put("ref_id", refId)
            put("status", status)
            if (error != null) put("error", error)
        }.toString()
    }
}

/** Messages received from Server → Android over WebSocket */
sealed class InboundCommand {
    /** Send an SMS to an external number */
    data class SendSms(
        val id: String,
        val to: String,
        val body: String,
        val simSlot: Int = 0,
    ) : InboundCommand()

    object Ping : InboundCommand()
    object Unknown : InboundCommand()

    companion object {
        fun fromJson(raw: String): InboundCommand {
            return try {
                val json = JSONObject(raw)
                when (json.optString("type")) {
                    "sms.send" -> SendSms(
                        id      = json.getString("id"),
                        to      = json.getString("to"),
                        body    = json.getString("body"),
                        simSlot = json.optInt("sim_slot", 0),
                    )
                    "ping" -> Ping
                    else   -> Unknown
                }
            } catch (e: Exception) {
                Unknown
            }
        }
    }
}
