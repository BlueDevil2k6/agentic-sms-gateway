package com.agentic.smsbridge.ui.dashboard

import android.app.Activity
import androidx.activity.compose.BackHandler
import androidx.compose.foundation.layout.*
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.Settings
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.unit.dp
import androidx.hilt.navigation.compose.hiltViewModel
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import com.agentic.smsbridge.model.ConnectionState
import com.agentic.smsbridge.service.BridgeService
import com.agentic.smsbridge.ui.theme.StatusColor
import java.text.SimpleDateFormat
import java.util.*

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun DashboardScreen(
    onOpenSettings: () -> Unit,
    viewModel: DashboardViewModel = hiltViewModel(),
) {
    val context          = LocalContext.current
    val activity         = context as? Activity
    val connectionState  by viewModel.connectionState.collectAsStateWithLifecycle()
    val reconnectAttempt by viewModel.reconnectAttempt.collectAsStateWithLifecycle()

    // Start BridgeService when dashboard is shown
    LaunchedEffect(Unit) {
        BridgeService.start(context)
    }

    // Minimize to background on Back instead of finishing the Activity.
    // This keeps the foreground service running and lets the user reopen
    // the app from the launcher or notification without losing state.
    BackHandler {
        activity?.moveTaskToBack(true)
    }

    Scaffold(
        topBar = {
            TopAppBar(
                title = { Text("SMS Bridge") },
                actions = {
                    IconButton(onClick = onOpenSettings) {
                        Icon(Icons.Default.Settings, contentDescription = "Settings")
                    }
                }
            )
        }
    ) { padding ->
        Column(
            modifier = Modifier
                .fillMaxSize()
                .padding(padding)
                .padding(16.dp),
            verticalArrangement = Arrangement.spacedBy(12.dp),
        ) {
            // ── Connection card ──────────────────────────────────────────
            ConnectionCard(
                state          = connectionState,
                serverUrl      = viewModel.getServerUrl(),
                reconnectAttempt = reconnectAttempt,
            )

            // ── Status indicators ────────────────────────────────────────
            StatusCard {
                StatusRow(
                    label  = "SMS permissions",
                    ok     = viewModel.hasSmsPermissions(context),
                    okText = "Granted",
                    errText = "Denied",
                )
                StatusRow(
                    label   = "FCM wake-up",
                    ok      = viewModel.isFcmReady(),
                    okText  = "Ready",
                    errText = "Unavailable",
                )
                StatusRow(
                    label   = "Battery exempt",
                    ok      = !viewModel.isBatteryOptimised(context),
                    okText  = "Unrestricted",
                    errText = "Restricted — may delay messages",
                    isWarning = true,
                )
            }

            // ── Activity counters ────────────────────────────────────────
            ActivityCard(
                inboundCount  = viewModel.getInboundCount(),
                outboundCount = viewModel.getOutboundCount(),
                lastActivity  = viewModel.getLastActivity(),
            )

            // ── Device name ──────────────────────────────────────────────
            Card(modifier = Modifier.fillMaxWidth()) {
                Row(
                    modifier = Modifier.padding(16.dp).fillMaxWidth(),
                    horizontalArrangement = Arrangement.SpaceBetween,
                ) {
                    Text("Device name", style = MaterialTheme.typography.bodyMedium)
                    Text(viewModel.getDeviceName(), style = MaterialTheme.typography.bodyMedium,
                        color = MaterialTheme.colorScheme.outline)
                }
            }
        }
    }
}

@Composable
private fun ConnectionCard(state: ConnectionState, serverUrl: String, reconnectAttempt: Int) {
    val (color, label) = when (state) {
        ConnectionState.CONNECTED    -> StatusColor.Connected to "Connected"
        ConnectionState.CONNECTING   -> StatusColor.Warning   to "Connecting…"
        ConnectionState.RECONNECTING -> StatusColor.Warning   to "Reconnecting… (attempt $reconnectAttempt)"
        ConnectionState.FAILED       -> StatusColor.Error     to "Connection failed — check API key"
        ConnectionState.IDLE         -> Color.Gray            to "Idle"
    }

    Card(modifier = Modifier.fillMaxWidth()) {
        Column(modifier = Modifier.padding(16.dp), verticalArrangement = Arrangement.spacedBy(4.dp)) {
            Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                StatusDot(color)
                Text(label, style = MaterialTheme.typography.titleMedium)
            }
            Text(serverUrl, style = MaterialTheme.typography.bodySmall, color = MaterialTheme.colorScheme.outline)
        }
    }
}

@Composable
private fun StatusCard(content: @Composable ColumnScope.() -> Unit) {
    Card(modifier = Modifier.fillMaxWidth()) {
        Column(modifier = Modifier.padding(16.dp), verticalArrangement = Arrangement.spacedBy(12.dp)) {
            content()
        }
    }
}

@Composable
private fun StatusRow(
    label: String,
    ok: Boolean,
    okText: String,
    errText: String,
    isWarning: Boolean = false,
) {
    val color = when {
        ok         -> StatusColor.Connected
        isWarning  -> StatusColor.Warning
        else       -> StatusColor.Error
    }
    Row(
        modifier = Modifier.fillMaxWidth(),
        horizontalArrangement = Arrangement.SpaceBetween,
        verticalAlignment = Alignment.CenterVertically,
    ) {
        Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(8.dp)) {
            StatusDot(color)
            Text(label, style = MaterialTheme.typography.bodyMedium)
        }
        Text(
            if (ok) okText else errText,
            style = MaterialTheme.typography.bodySmall,
            color = color,
        )
    }
}

@Composable
private fun ActivityCard(inboundCount: Int, outboundCount: Int, lastActivity: Long) {
    Card(modifier = Modifier.fillMaxWidth()) {
        Column(modifier = Modifier.padding(16.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
            Text("Activity", style = MaterialTheme.typography.titleSmall)
            ActivityRow("Inbound forwarded",  inboundCount.toString())
            ActivityRow("Outbound sent",       outboundCount.toString())
            ActivityRow(
                "Last activity",
                if (lastActivity == 0L) "Never"
                else SimpleDateFormat("MMM d, HH:mm", Locale.getDefault()).format(Date(lastActivity))
            )
        }
    }
}

@Composable
private fun ActivityRow(label: String, value: String) {
    Row(modifier = Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceBetween) {
        Text(label, style = MaterialTheme.typography.bodyMedium)
        Text(value, style = MaterialTheme.typography.bodyMedium, color = MaterialTheme.colorScheme.outline)
    }
}

@Composable
private fun StatusDot(color: Color) {
    Surface(shape = MaterialTheme.shapes.small, color = color, modifier = Modifier.size(10.dp)) {}
}
