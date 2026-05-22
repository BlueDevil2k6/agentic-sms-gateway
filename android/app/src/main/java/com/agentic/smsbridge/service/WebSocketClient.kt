package com.agentic.smsbridge.service

import android.util.Log
import com.agentic.smsbridge.data.BridgeConfig
import com.agentic.smsbridge.data.BridgeRepository
import com.agentic.smsbridge.model.ConnectionState
import com.agentic.smsbridge.model.InboundCommand
import com.agentic.smsbridge.model.OutboundMessage
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.Job
import kotlinx.coroutines.delay
import kotlinx.coroutines.launch
import okhttp3.OkHttpClient
import okhttp3.Request
import okhttp3.Response
import okhttp3.WebSocket
import okhttp3.WebSocketListener
import okio.ByteString
import javax.inject.Inject
import javax.inject.Singleton
import kotlin.math.min
import kotlin.math.pow

private const val TAG = "WebSocketClient"

/** Backoff delays in ms: 2s, 4s, 8s, 16s, 30s (capped) */
private fun backoffMs(attempt: Int): Long =
    min(2.0.pow(attempt).toLong() * 1000L, 30_000L)

@Singleton
class WebSocketClient @Inject constructor(
    private val okHttpClient: OkHttpClient,
    private val repository: BridgeRepository,
) {
    private var ws: WebSocket? = null
    private var reconnectJob: Job? = null
    private var outboundJob: Job? = null
    private val scope = CoroutineScope(Dispatchers.IO)

    /** Callback invoked when the server sends an InboundCommand */
    var onCommand: ((InboundCommand) -> Unit)? = null

    // ── Connection lifecycle ──────────────────────────────────────────────

    fun connect(config: BridgeConfig) {
        disconnect()
        repository.updateConnectionState(ConnectionState.CONNECTING)
        repository.updateReconnectAttempt(0)
        doConnect(config, attempt = 0)
        startOutboundPump()
    }

    fun disconnect() {
        reconnectJob?.cancel()
        reconnectJob = null
        outboundJob?.cancel()
        outboundJob = null
        ws?.close(1000, "Disconnecting")
        ws = null
        repository.updateConnectionState(ConnectionState.IDLE)
    }

    fun send(message: OutboundMessage) {
        val json = message.toJson()
        if (ws?.send(json) == true) {
            Log.i(TAG, "→ Sent to server: ${json.take(200)}")
        } else {
            Log.w(TAG, "WebSocket send failed — message dropped: ${json.take(80)}")
        }
    }

    // ── Internal connection logic ─────────────────────────────────────────

    private fun doConnect(config: BridgeConfig, attempt: Int) {
        val request = Request.Builder()
            .url(config.serverUrl)
            .header("Authorization", "Bearer ${config.apiKey}")
            .header("X-Device-ID",   config.deviceId)
            .build()

        ws = okHttpClient.newWebSocket(request, object : WebSocketListener() {
            override fun onOpen(webSocket: WebSocket, response: Response) {
                Log.i(TAG, "Connected to ${config.serverUrl}")
                repository.updateConnectionState(ConnectionState.CONNECTED)
                repository.updateReconnectAttempt(0)

                // Register device with server
                webSocket.send(
                    OutboundMessage.DeviceHello(
                        deviceId   = config.deviceId,
                        deviceName = config.deviceName,
                        fcmToken   = repository.prefs.getFcmToken() ?: "",
                    ).toJson()
                )
            }

            override fun onMessage(webSocket: WebSocket, text: String) {
                Log.d(TAG, "← $text")
                val cmd = InboundCommand.fromJson(text)
                if (cmd is InboundCommand.Ping) {
                    // Respond to application-level ping (OkHttp handles WS ping frames)
                    webSocket.send("""{"type":"pong","ts":${System.currentTimeMillis()}}""")
                } else {
                    onCommand?.invoke(cmd)
                }
            }

            override fun onMessage(webSocket: WebSocket, bytes: ByteString) {
                // Binary frames not used — ignore
            }

            override fun onFailure(webSocket: WebSocket, t: Throwable, response: Response?) {
                val statusCode = response?.code
                Log.w(TAG, "Connection failure (attempt $attempt): ${t.message}, status=$statusCode")

                // 401 = bad API key — don't retry
                if (statusCode == 401) {
                    Log.e(TAG, "Unauthorized — check API key. Not retrying.")
                    repository.updateConnectionState(ConnectionState.FAILED)
                    return
                }

                scheduleReconnect(config, attempt + 1)
            }

            override fun onClosed(webSocket: WebSocket, code: Int, reason: String) {
                Log.i(TAG, "Connection closed: code=$code reason=$reason")
                if (code != 1000) {
                    // Unexpected close — reconnect
                    scheduleReconnect(config, attempt + 1)
                } else {
                    repository.updateConnectionState(ConnectionState.IDLE)
                }
            }
        })
    }

    private fun scheduleReconnect(config: BridgeConfig, attempt: Int) {
        repository.updateConnectionState(ConnectionState.RECONNECTING)
        repository.updateReconnectAttempt(attempt)
        val delay = backoffMs(attempt)
        Log.i(TAG, "Reconnecting in ${delay}ms (attempt $attempt)")

        reconnectJob = scope.launch {
            delay(delay)
            doConnect(config, attempt)
        }
    }

    // ── Outbound pump ─────────────────────────────────────────────────────
    //
    // Reads from BridgeRepository.outboundChannel and sends over WebSocket.
    // Runs for the lifetime of the connection.

    private fun startOutboundPump() {
        outboundJob = scope.launch {
            for (message in repository.outboundChannel) {
                Log.i(TAG, "Outbound dequeued: ${message::class.simpleName}")
                if (repository.connectionState.value == ConnectionState.CONNECTED) {
                    send(message)
                } else {
                    Log.w(TAG, "Dropped outbound message (not connected): ${message::class.simpleName}")
                }
            }
        }
    }
}
