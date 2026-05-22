package com.agentic.smsbridge.ui.onboarding

import android.util.Log
import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import com.agentic.smsbridge.data.BridgeConfig
import com.agentic.smsbridge.data.BridgeRepository
import com.agentic.smsbridge.service.BridgeService
import dagger.hilt.android.lifecycle.HiltViewModel
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.launch
import okhttp3.OkHttpClient
import okhttp3.Request
import okhttp3.Response
import okhttp3.WebSocket
import okhttp3.WebSocketListener
import org.json.JSONObject
import java.util.UUID
import javax.inject.Inject

private const val TAG = "OnboardingVM"

sealed class OnboardingStep {
    object Welcome : OnboardingStep()
    object QrScanner : OnboardingStep()
    data class Connecting(val url: String) : OnboardingStep()
    data class ConnectionError(val message: String) : OnboardingStep()
    object Permissions : OnboardingStep()
    object BatteryOptimisation : OnboardingStep()
}

@HiltViewModel
class OnboardingViewModel @Inject constructor(
    private val repository: BridgeRepository,
    private val okHttpClient: OkHttpClient,
) : ViewModel() {

    private val _step = MutableStateFlow<OnboardingStep>(OnboardingStep.Welcome)
    val step: StateFlow<OnboardingStep> = _step.asStateFlow()

    private var parsedConfig: BridgeConfig? = null

    // ── Welcome step ──────────────────────────────────────────────────────

    fun onGetStarted() {
        _step.value = OnboardingStep.QrScanner
    }

    // ── QR scanning ───────────────────────────────────────────────────────

    /**
     * Called when the QR scanner detects a code.
     * Parses the payload and attempts a test connection.
     */
    fun onQrScanned(rawValue: String) {
        Log.d(TAG, "QR scanned: ${rawValue.take(60)}")
        val config = parseQrPayload(rawValue)
        if (config == null) {
            _step.value = OnboardingStep.ConnectionError("Invalid QR code — use the code from your gateway server")
            return
        }
        parsedConfig = config
        testConnection(config)
    }

    fun onManualEntry(serverUrl: String, apiKey: String, deviceName: String = "SMS Bridge") {
        val config = BridgeConfig(
            serverUrl  = serverUrl.trim(),
            apiKey     = apiKey.trim(),
            deviceId   = UUID.randomUUID().toString(),
            deviceName = deviceName,
        )
        parsedConfig = config
        testConnection(config)
    }

    fun retryFromQr() {
        _step.value = OnboardingStep.Welcome
    }

    fun retryConnection() {
        parsedConfig?.let { testConnection(it) } ?: run {
            _step.value = OnboardingStep.QrScanner
        }
    }

    // ── Permissions step ──────────────────────────────────────────────────

    fun onPermissionsGranted() {
        _step.value = OnboardingStep.BatteryOptimisation
    }

    // ── Battery step ──────────────────────────────────────────────────────

    fun onBatteryStepComplete() {
        val config = parsedConfig ?: return
        repository.prefs.saveConfig(config)
        // onConfigured callback handled in the screen via step observation
    }

    // ── Private helpers ───────────────────────────────────────────────────

    private fun parseQrPayload(raw: String): BridgeConfig? {
        return try {
            val json = JSONObject(raw)
            BridgeConfig(
                serverUrl  = json.getString("url"),
                apiKey     = json.getString("key"),
                deviceId   = UUID.randomUUID().toString(),
                deviceName = json.optString("name", "SMS Bridge"),
            )
        } catch (e: Exception) {
            Log.w(TAG, "QR parse failed: ${e.message}")
            null
        }
    }

    private fun testConnection(config: BridgeConfig) {
        _step.value = OnboardingStep.Connecting(config.serverUrl)

        viewModelScope.launch {
            val request = Request.Builder()
                .url(config.serverUrl)
                .header("Authorization", "Bearer ${config.apiKey}")
                .build()

            okHttpClient.newWebSocket(request, object : WebSocketListener() {
                override fun onOpen(webSocket: WebSocket, response: Response) {
                    webSocket.close(1000, "Test OK")
                    _step.value = OnboardingStep.Permissions
                }

                override fun onFailure(webSocket: WebSocket, t: Throwable, response: Response?) {
                    val msg = when (response?.code) {
                        401  -> "Invalid API key — re-scan the QR code"
                        else -> "Could not connect: ${t.message ?: "Unknown error"}"
                    }
                    _step.value = OnboardingStep.ConnectionError(msg)
                }
            })
        }
    }
}
