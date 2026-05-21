package com.agentic.smsbridge.data

data class BridgeConfig(
    val serverUrl: String,   // wss://host:port
    val apiKey: String,
    val deviceId: String,    // stable UUID generated on first run
    val deviceName: String,
)
