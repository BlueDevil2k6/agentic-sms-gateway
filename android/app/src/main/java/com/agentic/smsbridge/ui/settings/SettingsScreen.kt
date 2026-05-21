package com.agentic.smsbridge.ui.settings

import android.content.Intent
import android.net.Uri
import android.provider.Settings
import androidx.compose.foundation.layout.*
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.filled.ArrowBack
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.unit.dp
import androidx.hilt.navigation.compose.hiltViewModel
import androidx.lifecycle.compose.collectAsStateWithLifecycle

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun SettingsScreen(
    onBack: () -> Unit,
    onReset: () -> Unit,
    viewModel: SettingsViewModel = hiltViewModel(),
) {
    val context    = LocalContext.current
    val deviceName by viewModel.deviceName.collectAsStateWithLifecycle()
    var showResetDialog by remember { mutableStateOf(false) }

    if (showResetDialog) {
        AlertDialog(
            onDismissRequest = { showResetDialog = false },
            title   = { Text("Disconnect and reset?") },
            text    = { Text("This will erase your server configuration and stop the bridge. You will need to re-scan the QR code to reconnect.") },
            confirmButton = {
                TextButton(onClick = {
                    viewModel.disconnectAndReset(context)
                    showResetDialog = false
                    onReset()
                }) { Text("Reset", color = MaterialTheme.colorScheme.error) }
            },
            dismissButton = { TextButton(onClick = { showResetDialog = false }) { Text("Cancel") } },
        )
    }

    Scaffold(
        topBar = {
            TopAppBar(
                title = { Text("Settings") },
                navigationIcon = {
                    IconButton(onClick = onBack) {
                        Icon(Icons.AutoMirrored.Filled.ArrowBack, contentDescription = "Back")
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
            verticalArrangement = Arrangement.spacedBy(16.dp),
        ) {
            // ── Connection ───────────────────────────────────────────────
            SettingsSection("Connection") {
                SettingsReadOnlyRow("Server",  viewModel.serverUrl)
                SettingsReadOnlyRow("API Key", viewModel.apiKeyMasked)
            }

            // ── Device ───────────────────────────────────────────────────
            SettingsSection("Device") {
                OutlinedTextField(
                    value         = deviceName,
                    onValueChange = { viewModel.updateDeviceName(it) },
                    label         = { Text("Device name") },
                    singleLine    = true,
                    modifier      = Modifier.fillMaxWidth(),
                )
            }

            // ── System ───────────────────────────────────────────────────
            SettingsSection("System") {
                OutlinedButton(
                    onClick  = {
                        val intent = Intent(Settings.ACTION_APPLICATION_DETAILS_SETTINGS).apply {
                            data = Uri.parse("package:${context.packageName}")
                        }
                        context.startActivity(intent)
                    },
                    modifier = Modifier.fillMaxWidth(),
                ) { Text("Battery optimisation settings") }
            }

            // ── App info ─────────────────────────────────────────────────
            SettingsSection("About") {
                SettingsReadOnlyRow("Version", "0.1.0")
            }

            Spacer(Modifier.weight(1f))

            // ── Danger zone ──────────────────────────────────────────────
            Button(
                onClick  = { showResetDialog = true },
                colors   = ButtonDefaults.buttonColors(containerColor = MaterialTheme.colorScheme.error),
                modifier = Modifier.fillMaxWidth(),
            ) { Text("Disconnect and reset") }
        }
    }
}

@Composable
private fun SettingsSection(title: String, content: @Composable ColumnScope.() -> Unit) {
    Card(modifier = Modifier.fillMaxWidth()) {
        Column(modifier = Modifier.padding(16.dp), verticalArrangement = Arrangement.spacedBy(12.dp)) {
            Text(title, style = MaterialTheme.typography.labelLarge, color = MaterialTheme.colorScheme.primary)
            content()
        }
    }
}

@Composable
private fun SettingsReadOnlyRow(label: String, value: String) {
    Row(modifier = Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceBetween) {
        Text(label, style = MaterialTheme.typography.bodyMedium)
        Text(value, style = MaterialTheme.typography.bodySmall, color = MaterialTheme.colorScheme.outline,
            maxLines = 1)
    }
}
