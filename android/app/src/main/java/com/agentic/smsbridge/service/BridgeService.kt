package com.agentic.smsbridge.service

import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.PendingIntent
import android.content.Context
import android.content.Intent
import android.content.pm.ServiceInfo
import android.os.PowerManager
import android.util.Log
import androidx.core.app.NotificationCompat
import androidx.lifecycle.Lifecycle
import androidx.lifecycle.LifecycleService
import androidx.lifecycle.lifecycleScope
import androidx.lifecycle.repeatOnLifecycle
import kotlinx.coroutines.launch
import com.agentic.smsbridge.MainActivity
import com.agentic.smsbridge.R
import com.agentic.smsbridge.data.BridgeRepository
import com.agentic.smsbridge.model.ConnectionState
import com.agentic.smsbridge.model.InboundCommand
import dagger.hilt.android.AndroidEntryPoint
import javax.inject.Inject

private const val TAG               = "BridgeService"
private const val NOTIFICATION_ID   = 1001
private const val CHANNEL_ID        = "bridge_status"

@AndroidEntryPoint
class BridgeService : LifecycleService() {

    @Inject lateinit var wsClient:    WebSocketClient
    @Inject lateinit var smsHandler:  SmsHandler
    @Inject lateinit var repository:  BridgeRepository

    private var wakeLock: PowerManager.WakeLock? = null

    // Guard against double-initialisation: onStartCommand is called every time
    // startForegroundService() is called, even when the service is already running.
    // Without this flag a second connect() + coroutine would fire on every
    // DashboardScreen recomposition, causing a disconnect/reconnect storm.
    @Volatile private var isStarted = false

    // ── Service lifecycle ─────────────────────────────────────────────────

    override fun onCreate() {
        super.onCreate()
        createNotificationChannel()
        Log.i(TAG, "BridgeService created")
    }

    override fun onStartCommand(intent: Intent?, flags: Int, startId: Int): Int {
        super.onStartCommand(intent, flags, startId)

        startForeground(
            NOTIFICATION_ID,
            buildNotification("Connecting…"),
            ServiceInfo.FOREGROUND_SERVICE_TYPE_REMOTE_MESSAGING,
        )

        if (!isStarted) {
            isStarted = true
            acquireWakeLock()
            startBridge()
        } else {
            Log.d(TAG, "onStartCommand: already running — skipping re-init")
        }

        return START_STICKY   // OS restarts the service if killed
    }

    override fun onDestroy() {
        isStarted = false
        wsClient.disconnect()
        releaseWakeLock()
        Log.i(TAG, "BridgeService destroyed")
        super.onDestroy()
    }

    // ── Bridge initialisation ─────────────────────────────────────────────

    private fun startBridge() {
        val config = repository.prefs.getConfig()
        if (config == null) {
            Log.w(TAG, "No config — stopping service")
            stopSelf()
            return
        }

        // Wire the WebSocket command handler → SmsHandler
        wsClient.onCommand = { cmd ->
            when (cmd) {
                is InboundCommand.SendSms -> {
                    Log.i(TAG, "sms.send received: to=${cmd.to} id=${cmd.id}")
                    smsHandler.sendSms(
                        messageId = cmd.id,
                        to        = cmd.to,
                        body      = cmd.body,
                    )
                }
                is InboundCommand.Ping -> { /* handled in WebSocketClient */ }
                is InboundCommand.Unknown -> { /* logged in WebSocketClient */ }
            }
        }

        // Update notification when connection state changes
        lifecycleScope.launch {
            repeatOnLifecycle(Lifecycle.State.STARTED) {
                repository.connectionState.collect { state ->
                    val statusText = when (state) {
                        ConnectionState.CONNECTED    -> "Connected · ${config.serverUrl.removePrefix("wss://").removePrefix("ws://")}"
                        ConnectionState.CONNECTING   -> "Connecting…"
                        ConnectionState.RECONNECTING -> {
                            val attempt = repository.reconnectAttempt.value
                            "Reconnecting… (attempt $attempt)"
                        }
                        ConnectionState.FAILED  -> "Connection failed — check API key"
                        ConnectionState.IDLE    -> "Idle"
                    }
                    updateNotification(statusText)
                }
            }
        }

        wsClient.connect(config)
        Log.i(TAG, "Bridge started → ${config.serverUrl}")
    }

    // ── WakeLock ──────────────────────────────────────────────────────────

    private fun acquireWakeLock() {
        val pm = getSystemService(Context.POWER_SERVICE) as PowerManager
        wakeLock = pm.newWakeLock(
            PowerManager.PARTIAL_WAKE_LOCK,
            "SmsBridge::WakeLock"
        ).apply { acquire() }
        Log.d(TAG, "WakeLock acquired")
    }

    private fun releaseWakeLock() {
        wakeLock?.let {
            if (it.isHeld) it.release()
        }
        wakeLock = null
        Log.d(TAG, "WakeLock released")
    }

    // ── Notification ──────────────────────────────────────────────────────

    private fun createNotificationChannel() {
        val channel = NotificationChannel(
            CHANNEL_ID,
            "Bridge Status",
            NotificationManager.IMPORTANCE_LOW,    // silent, no heads-up
        ).apply {
            description = "Shows the SMS bridge connection status"
            setShowBadge(false)
        }
        val nm = getSystemService(NotificationManager::class.java)
        nm.createNotificationChannel(channel)
    }

    private fun buildNotification(statusText: String) = NotificationCompat
        .Builder(this, CHANNEL_ID)
        .setSmallIcon(R.drawable.ic_bridge_notification)
        .setContentTitle("SMS Bridge")
        .setContentText(statusText)
        .setOngoing(true)
        .setSilent(true)
        .setContentIntent(
            PendingIntent.getActivity(
                this, 0,
                Intent(this, MainActivity::class.java).apply {
                    // Bring existing task to front rather than creating a new instance.
                    flags = Intent.FLAG_ACTIVITY_SINGLE_TOP or Intent.FLAG_ACTIVITY_CLEAR_TOP
                },
                PendingIntent.FLAG_IMMUTABLE or PendingIntent.FLAG_UPDATE_CURRENT,
            )
        )
        .build()

    private fun updateNotification(statusText: String) {
        val nm = getSystemService(NotificationManager::class.java)
        nm.notify(NOTIFICATION_ID, buildNotification(statusText))
    }

    // ── Static helpers ────────────────────────────────────────────────────

    companion object {
        fun start(context: Context) {
            val intent = Intent(context, BridgeService::class.java)
            context.startForegroundService(intent)
        }

        fun stop(context: Context) {
            context.stopService(Intent(context, BridgeService::class.java))
        }
    }
}
