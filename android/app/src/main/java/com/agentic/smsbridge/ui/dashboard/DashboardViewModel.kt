package com.agentic.smsbridge.ui.dashboard

import androidx.lifecycle.ViewModel
import com.agentic.smsbridge.data.BridgeRepository
import com.agentic.smsbridge.model.ConnectionState
import dagger.hilt.android.lifecycle.HiltViewModel
import kotlinx.coroutines.flow.StateFlow
import javax.inject.Inject

@HiltViewModel
class DashboardViewModel @Inject constructor(
    private val repository: BridgeRepository,
) : ViewModel() {

    val connectionState: StateFlow<ConnectionState> = repository.connectionState
    val reconnectAttempt: StateFlow<Int>            = repository.reconnectAttempt
    val inboundCount:    StateFlow<Int>             = repository.inboundCount
    val outboundCount:   StateFlow<Int>             = repository.outboundCount
    val lastActivity:    StateFlow<Long>            = repository.lastActivity

    fun getServerUrl(): String =
        repository.prefs.getConfig()?.serverUrl
            ?.removePrefix("wss://")
            ?.removePrefix("ws://")
            ?: "Not configured"

    fun getDeviceName(): String =
        repository.prefs.getConfig()?.deviceName ?: "—"


    fun isBatteryOptimised(context: android.content.Context): Boolean {
        val pm = context.getSystemService(android.os.PowerManager::class.java)
        return !pm.isIgnoringBatteryOptimizations(context.packageName)
    }

    fun hasSmsPermissions(context: android.content.Context): Boolean {
        val pm = context.packageManager
        return pm.checkPermission(android.Manifest.permission.RECEIVE_SMS, context.packageName) ==
                android.content.pm.PackageManager.PERMISSION_GRANTED &&
               pm.checkPermission(android.Manifest.permission.SEND_SMS, context.packageName) ==
                android.content.pm.PackageManager.PERMISSION_GRANTED
    }

    fun isFcmReady(): Boolean =
        repository.prefs.getFcmToken() != null
}
