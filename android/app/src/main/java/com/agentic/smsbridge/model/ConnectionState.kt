package com.agentic.smsbridge.model

enum class ConnectionState {
    IDLE,           // Not configured or service not started
    CONNECTING,     // First connect attempt in progress
    CONNECTED,      // WebSocket is open
    RECONNECTING,   // Dropped connection, retrying with backoff
    FAILED,         // Auth failure or permanent error — no auto-retry
}
