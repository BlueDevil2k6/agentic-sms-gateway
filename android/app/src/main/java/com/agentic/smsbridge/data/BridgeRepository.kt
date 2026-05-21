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
        _outboundChannel.trySend(message)
    }
}
