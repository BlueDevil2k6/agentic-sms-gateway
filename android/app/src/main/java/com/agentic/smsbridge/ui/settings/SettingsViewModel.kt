package com.agentic.smsbridge.ui.settings

import androidx.lifecycle.ViewModel
import com.agentic.smsbridge.data.BridgeRepository
import com.agentic.smsbridge.service.BridgeService
import dagger.hilt.android.lifecycle.HiltViewModel
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import javax.inject.Inject

@HiltViewModel
class SettingsViewModel @Inject constructor(
    private val repository: BridgeRepository,
) : ViewModel() {

    val serverUrl: String get() = repository.prefs.getConfig()?.serverUrl ?: ""
    val apiKeyMasked: String get() {
        val key = repository.prefs.getConfig()?.apiKey ?: return ""
        return if (key.length > 12) key.take(10) + "••••••••" else "••••••••"
    }

    private val _deviceName = MutableStateFlow(repository.prefs.getConfig()?.deviceName ?: "SMS Bridge")
    val deviceName: StateFlow<String> = _deviceName.asStateFlow()

    fun updateDeviceName(name: String) {
        _deviceName.value = name
        repository.prefs.updateDeviceName(name)
    }

    fun disconnectAndReset(context: android.content.Context) {
        BridgeService.stop(context)
        repository.prefs.clearConfig()
        repository.updateConnectionState(com.agentic.smsbridge.model.ConnectionState.IDLE)
    }
}
