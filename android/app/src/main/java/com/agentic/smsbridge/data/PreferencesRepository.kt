package com.agentic.smsbridge.data

import android.content.Context
import android.content.SharedPreferences
import androidx.security.crypto.EncryptedSharedPreferences
import androidx.security.crypto.MasterKey
import dagger.hilt.android.qualifiers.ApplicationContext
import java.util.UUID
import javax.inject.Inject
import javax.inject.Singleton

@Singleton
class PreferencesRepository @Inject constructor(
    @ApplicationContext private val context: Context,
) {
    // Sensitive values (server URL, API key, device ID, FCM token)
    private val encrypted: SharedPreferences by lazy {
        val masterKey = MasterKey.Builder(context)
            .setKeyScheme(MasterKey.KeyScheme.AES256_GCM)
            .build()
        EncryptedSharedPreferences.create(
            context,
            "bridge_secure_prefs",
            masterKey,
            EncryptedSharedPreferences.PrefKeyEncryptionScheme.AES256_SIV,
            EncryptedSharedPreferences.PrefValueEncryptionScheme.AES256_GCM,
        )
    }

    // Non-sensitive values (device name, counters, last activity)
    private val plain: SharedPreferences by lazy {
        context.getSharedPreferences("bridge_prefs", Context.MODE_PRIVATE)
    }

    // ── Configuration ─────────────────────────────────────────────────────

    fun isConfigured(): Boolean =
        encrypted.contains(KEY_SERVER_URL) && encrypted.contains(KEY_API_KEY)

    fun saveConfig(config: BridgeConfig) {
        encrypted.edit()
            .putString(KEY_SERVER_URL, config.serverUrl)
            .putString(KEY_API_KEY,    config.apiKey)
            .putString(KEY_DEVICE_ID,  config.deviceId)
            .apply()
        plain.edit()
            .putString(KEY_DEVICE_NAME, config.deviceName)
            .apply()
    }

    fun getConfig(): BridgeConfig? {
        val url  = encrypted.getString(KEY_SERVER_URL, null) ?: return null
        val key  = encrypted.getString(KEY_API_KEY,    null) ?: return null
        val id   = encrypted.getString(KEY_DEVICE_ID,  null) ?: generateAndSaveDeviceId()
        val name = plain.getString(KEY_DEVICE_NAME, "SMS Bridge") ?: "SMS Bridge"
        return BridgeConfig(serverUrl = url, apiKey = key, deviceId = id, deviceName = name)
    }

    fun updateDeviceName(name: String) {
        plain.edit().putString(KEY_DEVICE_NAME, name).apply()
    }

    fun clearConfig() {
        encrypted.edit().clear().apply()
        plain.edit()
            .remove(KEY_DEVICE_NAME)
            .remove(KEY_INBOUND_COUNT)
            .remove(KEY_OUTBOUND_COUNT)
            .remove(KEY_LAST_ACTIVITY)
            .apply()
    }

    // ── FCM token ─────────────────────────────────────────────────────────

    fun saveFcmToken(token: String) {
        encrypted.edit().putString(KEY_FCM_TOKEN, token).apply()
    }

    fun getFcmToken(): String? =
        encrypted.getString(KEY_FCM_TOKEN, null)

    // ── Activity counters ─────────────────────────────────────────────────

    fun incrementInboundCount() {
        val count = plain.getInt(KEY_INBOUND_COUNT, 0)
        plain.edit().putInt(KEY_INBOUND_COUNT, count + 1).apply()
        touchLastActivity()
    }

    fun incrementOutboundCount() {
        val count = plain.getInt(KEY_OUTBOUND_COUNT, 0)
        plain.edit().putInt(KEY_OUTBOUND_COUNT, count + 1).apply()
        touchLastActivity()
    }

    fun getInboundCount(): Int  = plain.getInt(KEY_INBOUND_COUNT,  0)
    fun getOutboundCount(): Int = plain.getInt(KEY_OUTBOUND_COUNT, 0)
    fun getLastActivity(): Long = plain.getLong(KEY_LAST_ACTIVITY, 0L)

    private fun touchLastActivity() {
        plain.edit().putLong(KEY_LAST_ACTIVITY, System.currentTimeMillis()).apply()
    }

    // ── Helpers ───────────────────────────────────────────────────────────

    private fun generateAndSaveDeviceId(): String {
        val id = UUID.randomUUID().toString()
        encrypted.edit().putString(KEY_DEVICE_ID, id).apply()
        return id
    }

    companion object {
        private const val KEY_SERVER_URL    = "server_url"
        private const val KEY_API_KEY       = "api_key"
        private const val KEY_DEVICE_ID     = "device_id"
        private const val KEY_DEVICE_NAME   = "device_name"
        private const val KEY_FCM_TOKEN     = "fcm_token"
        private const val KEY_INBOUND_COUNT = "inbound_count"
        private const val KEY_OUTBOUND_COUNT = "outbound_count"
        private const val KEY_LAST_ACTIVITY = "last_activity"
    }
}
