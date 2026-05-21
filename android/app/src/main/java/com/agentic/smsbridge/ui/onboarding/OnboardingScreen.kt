package com.agentic.smsbridge.ui.onboarding

import android.Manifest
import android.content.Intent
import android.net.Uri
import android.provider.Settings
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.result.contract.ActivityResultContracts
import androidx.camera.core.CameraSelector
import androidx.camera.core.ImageAnalysis
import androidx.camera.core.Preview
import androidx.camera.lifecycle.ProcessCameraProvider
import androidx.camera.view.PreviewView
import androidx.compose.foundation.layout.*
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.platform.LocalLifecycleOwner
import androidx.compose.ui.text.input.PasswordVisualTransformation
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.unit.dp
import androidx.compose.ui.viewinterop.AndroidView
import androidx.core.content.ContextCompat
import androidx.hilt.navigation.compose.hiltViewModel
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import com.google.mlkit.vision.barcode.BarcodeScanning
import com.google.mlkit.vision.barcode.common.Barcode
import com.google.mlkit.vision.common.InputImage
import java.util.concurrent.Executors

@Composable
fun OnboardingScreen(
    onConfigured: () -> Unit,
    viewModel: OnboardingViewModel = hiltViewModel(),
) {
    val step by viewModel.step.collectAsStateWithLifecycle()

    // Navigate away when battery step completes
    LaunchedEffect(step) {
        if (step is OnboardingStep.BatteryOptimisation) {
            // Battery step is shown; completion triggers onConfigured
        }
    }

    when (val s = step) {
        is OnboardingStep.QrScanner          -> QrScannerStep(viewModel)
        is OnboardingStep.Connecting         -> ConnectingStep(s.url)
        is OnboardingStep.ConnectionError    -> ConnectionErrorStep(s.message, viewModel)
        is OnboardingStep.Permissions        -> PermissionsStep(viewModel)
        is OnboardingStep.BatteryOptimisation -> BatteryStep(
            onComplete = {
                viewModel.onBatteryStepComplete()
                onConfigured()
            }
        )
    }
}

// ── Step: QR Scanner ─────────────────────────────────────────────────────────

@Composable
private fun QrScannerStep(viewModel: OnboardingViewModel) {
    val context = LocalContext.current
    val lifecycleOwner = LocalLifecycleOwner.current
    var showManualEntry by remember { mutableStateOf(false) }
    var hasCameraPermission by remember { mutableStateOf(false) }
    var scanned by remember { mutableStateOf(false) }

    val cameraPermissionLauncher = rememberLauncherForActivityResult(
        ActivityResultContracts.RequestPermission()
    ) { granted -> hasCameraPermission = granted }

    LaunchedEffect(Unit) {
        cameraPermissionLauncher.launch(Manifest.permission.CAMERA)
    }

    if (showManualEntry) {
        ManualEntrySheet(
            onDismiss = { showManualEntry = false },
            onConfirm = { url, key -> viewModel.onManualEntry(url, key) }
        )
    }

    Column(
        modifier = Modifier.fillMaxSize().padding(24.dp),
        horizontalAlignment = Alignment.CenterHorizontally,
        verticalArrangement = Arrangement.spacedBy(16.dp),
    ) {
        Spacer(Modifier.height(32.dp))
        Text("Agentic SMS Bridge", style = MaterialTheme.typography.headlineMedium)
        Text(
            "Scan the QR code from your gateway server to connect.",
            style = MaterialTheme.typography.bodyMedium,
            textAlign = TextAlign.Center,
        )

        if (hasCameraPermission) {
            val executor = remember { Executors.newSingleThreadExecutor() }
            AndroidView(
                modifier = Modifier.fillMaxWidth().height(320.dp),
                factory = { ctx ->
                    val previewView = PreviewView(ctx)
                    val cameraProviderFuture = ProcessCameraProvider.getInstance(ctx)
                    cameraProviderFuture.addListener({
                        val cameraProvider = cameraProviderFuture.get()
                        val preview = Preview.Builder().build()
                            .also { it.setSurfaceProvider(previewView.surfaceProvider) }
                        val scanner = BarcodeScanning.getClient()
                        val analysis = ImageAnalysis.Builder()
                            .setBackpressureStrategy(ImageAnalysis.STRATEGY_KEEP_ONLY_LATEST)
                            .build().also { ia ->
                                ia.setAnalyzer(executor) { proxy ->
                                    if (!scanned) {
                                        val mediaImage = proxy.image
                                        if (mediaImage != null) {
                                            val image = InputImage.fromMediaImage(
                                                mediaImage, proxy.imageInfo.rotationDegrees
                                            )
                                            scanner.process(image)
                                                .addOnSuccessListener { barcodes ->
                                                    barcodes.firstOrNull {
                                                        it.format == Barcode.FORMAT_QR_CODE
                                                    }?.rawValue?.let { raw ->
                                                        scanned = true
                                                        viewModel.onQrScanned(raw)
                                                    }
                                                }
                                                .addOnCompleteListener { proxy.close() }
                                        } else {
                                            proxy.close()
                                        }
                                    } else {
                                        proxy.close()
                                    }
                                }
                            }
                        cameraProvider.unbindAll()
                        cameraProvider.bindToLifecycle(
                            lifecycleOwner,
                            CameraSelector.DEFAULT_BACK_CAMERA,
                            preview, analysis,
                        )
                    }, ContextCompat.getMainExecutor(ctx))
                    previewView
                }
            )
        } else {
            Card(modifier = Modifier.fillMaxWidth()) {
                Text(
                    "Camera permission required to scan QR code.",
                    modifier = Modifier.padding(16.dp),
                    textAlign = TextAlign.Center,
                )
            }
        }

        TextButton(onClick = { showManualEntry = true }) {
            Text("Enter manually ›")
        }
    }
}

@Composable
private fun ManualEntrySheet(onDismiss: () -> Unit, onConfirm: (url: String, key: String) -> Unit) {
    var url by remember { mutableStateOf("") }
    var key by remember { mutableStateOf("") }

    AlertDialog(
        onDismissRequest = onDismiss,
        title = { Text("Manual setup") },
        text = {
            Column(verticalArrangement = Arrangement.spacedBy(12.dp)) {
                OutlinedTextField(
                    value = url,
                    onValueChange = { url = it },
                    label = { Text("Server URL") },
                    placeholder = { Text("wss://your-server.com:8765") },
                    singleLine = true,
                    modifier = Modifier.fillMaxWidth(),
                )
                OutlinedTextField(
                    value = key,
                    onValueChange = { key = it },
                    label = { Text("API Key") },
                    placeholder = { Text("sk-bridge-…") },
                    visualTransformation = PasswordVisualTransformation(),
                    singleLine = true,
                    modifier = Modifier.fillMaxWidth(),
                )
            }
        },
        confirmButton = {
            TextButton(
                onClick = { if (url.isNotBlank() && key.isNotBlank()) onConfirm(url, key) },
            ) { Text("Connect") }
        },
        dismissButton = { TextButton(onClick = onDismiss) { Text("Cancel") } },
    )
}

// ── Step: Connecting ─────────────────────────────────────────────────────────

@Composable
private fun ConnectingStep(url: String) {
    Column(
        modifier = Modifier.fillMaxSize(),
        horizontalAlignment = Alignment.CenterHorizontally,
        verticalArrangement = Arrangement.Center,
    ) {
        CircularProgressIndicator()
        Spacer(Modifier.height(24.dp))
        Text("Connecting to server…", style = MaterialTheme.typography.bodyLarge)
        Spacer(Modifier.height(8.dp))
        Text(url, style = MaterialTheme.typography.bodySmall, color = MaterialTheme.colorScheme.outline)
    }
}

// ── Step: Connection Error ───────────────────────────────────────────────────

@Composable
private fun ConnectionErrorStep(message: String, viewModel: OnboardingViewModel) {
    Column(
        modifier = Modifier.fillMaxSize().padding(24.dp),
        horizontalAlignment = Alignment.CenterHorizontally,
        verticalArrangement = Arrangement.Center,
    ) {
        Text("Connection failed", style = MaterialTheme.typography.headlineSmall)
        Spacer(Modifier.height(12.dp))
        Text(message, textAlign = TextAlign.Center, style = MaterialTheme.typography.bodyMedium)
        Spacer(Modifier.height(24.dp))
        Button(onClick = { viewModel.retryConnection() }) { Text("Try again") }
        Spacer(Modifier.height(8.dp))
        OutlinedButton(onClick = { viewModel.retryFromQr() }) { Text("Re-scan QR code") }
    }
}

// ── Step: Permissions ────────────────────────────────────────────────────────

@Composable
private fun PermissionsStep(viewModel: OnboardingViewModel) {
    var receiveSmsGranted by remember { mutableStateOf(false) }
    var sendSmsGranted    by remember { mutableStateOf(false) }
    var bootGranted       by remember { mutableStateOf(false) }

    val multiPermissionLauncher = rememberLauncherForActivityResult(
        ActivityResultContracts.RequestMultiplePermissions()
    ) { results ->
        receiveSmsGranted = results[Manifest.permission.RECEIVE_SMS] == true
        sendSmsGranted    = results[Manifest.permission.SEND_SMS]    == true
        bootGranted       = true  // RECEIVE_BOOT_COMPLETED is granted at install
    }

    val allGranted = receiveSmsGranted && sendSmsGranted

    LaunchedEffect(Unit) {
        multiPermissionLauncher.launch(
            arrayOf(Manifest.permission.RECEIVE_SMS, Manifest.permission.SEND_SMS)
        )
    }

    Column(
        modifier = Modifier.fillMaxSize().padding(24.dp),
        verticalArrangement = Arrangement.spacedBy(16.dp),
    ) {
        Spacer(Modifier.height(32.dp))
        Text("Grant permissions", style = MaterialTheme.typography.headlineMedium)
        Text("These are required for the bridge to work.", style = MaterialTheme.typography.bodyMedium)

        PermissionRow("Receive SMS",       receiveSmsGranted) {
            multiPermissionLauncher.launch(arrayOf(Manifest.permission.RECEIVE_SMS))
        }
        PermissionRow("Send SMS",          sendSmsGranted) {
            multiPermissionLauncher.launch(arrayOf(Manifest.permission.SEND_SMS))
        }
        PermissionRow("Start on boot",     true, canGrant = false) {}

        Spacer(Modifier.weight(1f))
        Button(
            onClick = { viewModel.onPermissionsGranted() },
            enabled = allGranted,
            modifier = Modifier.fillMaxWidth(),
        ) { Text("Continue") }
    }
}

@Composable
private fun PermissionRow(label: String, granted: Boolean, canGrant: Boolean = true, onGrant: () -> Unit) {
    Row(
        modifier = Modifier.fillMaxWidth(),
        verticalAlignment = Alignment.CenterVertically,
        horizontalArrangement = Arrangement.SpaceBetween,
    ) {
        Text(
            if (granted) "✓  $label" else "○  $label",
            style = MaterialTheme.typography.bodyLarge,
        )
        if (!granted && canGrant) {
            OutlinedButton(onClick = onGrant) { Text("Grant") }
        }
    }
}

// ── Step: Battery Optimisation ───────────────────────────────────────────────

@Composable
private fun BatteryStep(onComplete: () -> Unit) {
    val context = LocalContext.current

    Column(
        modifier = Modifier.fillMaxSize().padding(24.dp),
        verticalArrangement = Arrangement.spacedBy(16.dp),
    ) {
        Spacer(Modifier.height(32.dp))
        Text("Allow background activity", style = MaterialTheme.typography.headlineMedium)
        Text(
            "Android may put this app to sleep to save battery. Disabling this ensures reliable message delivery.",
            style = MaterialTheme.typography.bodyMedium,
        )

        Spacer(Modifier.height(8.dp))
        Button(
            onClick = {
                val intent = Intent(Settings.ACTION_REQUEST_IGNORE_BATTERY_OPTIMIZATIONS).apply {
                    data = Uri.parse("package:${context.packageName}")
                }
                context.startActivity(intent)
            },
            modifier = Modifier.fillMaxWidth(),
        ) { Text("Disable battery optimisation") }

        TextButton(
            onClick = onComplete,
            modifier = Modifier.fillMaxWidth(),
        ) { Text("Skip — I understand delivery may be delayed") }
    }
}
