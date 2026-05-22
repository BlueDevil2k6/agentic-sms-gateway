package com.agentic.smsbridge.data

import com.agentic.smsbridge.model.ConnectionState
import com.agentic.smsbridge.model.OutboundMessage
import kotlinx.coroutines.channels.Channel
import kotlinx.coroutines.channels.ReceiveChannel
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import javax.inject.Inject
import javax.inject.Singleton

/**
 * Shared state hub between BridgeService and the UI layer.
 *
 * - BridgeService writes connection state and reads the outbound channel.
 * - SmsReceiver writes to the outbound channel.
 * - ViewModels observe connection state and counter flows.
 */
@Singleton
class BridgeRepository @Inject constructor(
    val prefs: PreferencesRepository,
) {
    // ── Connection state (observed by UI) ─────────────────────────────────

    private val _connectionState = MutableStateFlow(ConnectionState.IDLE)
    val connectionState: StateFlow<ConnectionState> = _connectionState.asStateFlow()

    fun updateConnectionState(state: ConnectionState) {
        _connectionState.value = state
    }

    // ── Reconnect attempt counter (shown in UI during RECONNECTING) ────────

    private val _reconnectAttempt = MutableStateFlow(0)
    val reconnectAttempt: StateFlow<Int> = _reconnectAttempt.asStateFlow()

    fun updateReconnectAttempt(attempt: Int) {
        _reconnectAttempt.value = attempt
    }

    // ── Activity counters (reactive — UI observes these) ──────────────────
    //
    // Seeded from SharedPreferences on first access so the last-seen counts
    // survive process death. Updated via incrementInbound/incrementOutbound
    // so the Dashboard recomposes immediately on each new message.

    private val _inboundCount  = MutableStateFlow(prefs.getInboundCount())
    private val _outboundCount = MutableStateFlow(prefs.getOutboundCount())
    private val _lastActivity  = MutableStateFlow(prefs.getLastActivity())

    val inboundCount:  StateFlow<Int>  = _inboundCount.asStateFlow()
    val outboundCount: StateFlow<Int>  = _outboundCount.asStateFlow()
    val lastActivity:  StateFlow<Long> = _lastActivity.asStateFlow()

    fun incrementInbound() {
        prefs.incrementInboundCount()
        _inboundCount.value = prefs.getInboundCount()
        _lastActivity.value  = prefs.getLastActivity()
    }

    fun incrementOutbound() {
        prefs.incrementOutboundCount()
        _outboundCount.value = prefs.getOutboundCount()
        _lastActivity.value  = prefs.getLastActivity()
    }

    // ── Outbound channel (Android → Server) ───────────────────────────────
    //
    // SmsReceiver and BridgeService both write here.
    // BridgeService reads from here to forward messages over WebSocket.

    private val _outboundChannel = Channel<OutboundMessage>(Channel.BUFFERED)
    val outboundChannel: ReceiveChannel<OutboundMessage> = _outboundChannel

    suspend fun sendToServer(message: OutboundMessage) {
        _outboundChannel.send(message)
    }

    // ── Convenience: send without suspend (from BroadcastReceiver) ────────

    fun sendToServerBlocking(message: OutboundMessage) {
        val result = _outboundChannel.trySend(message)
        if (result.isFailure) {
            android.util.Log.e(
                "BridgeRepository",
                "sendToServerBlocking: channel full or closed — message dropped: ${message::class.simpleName}"
            )
        }
    }
}
