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
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.res.painterResource
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.input.PasswordVisualTransformation
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.unit.Dp
import androidx.compose.ui.unit.dp
import androidx.compose.ui.viewinterop.AndroidView
import androidx.core.content.ContextCompat
import androidx.hilt.navigation.compose.hiltViewModel
import androidx.lifecycle.compose.LocalLifecycleOwner
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import com.agentic.smsbridge.R
import com.google.mlkit.vision.barcode.BarcodeScanning
import com.google.mlkit.vision.barcode.common.Barcode
import com.google.mlkit.vision.common.InputImage
import java.util.concurrent.Executors

// ── App logo composable (reused across screens) ───────────────────────────────

@Composable
private fun AppLogo(modifier: Modifier = Modifier, size: Dp = 48.dp) {
    Box(
        modifier = modifier
            .size(size)
            .background(color = Color(0xFF1A237E), shape = CircleShape),
        contentAlignment = Alignment.Center,
    ) {
        Icon(
            painter = painterResource(R.drawable.ic_bridge_notification),
            contentDescription = "SMS Bridge",
            tint = Color.White,
            modifier = Modifier.size(size * 0.55f),
        )
    }
}

// ── Root screen ───────────────────────────────────────────────────────────────

@Composable
fun OnboardingScreen(
    onConfigured: () -> Unit,
    viewModel: OnboardingViewModel = hiltViewModel(),
) {
    val step by viewModel.step.collectAsStateWithLifecycle()

    when (val s = step) {
        is OnboardingStep.Welcome            -> WelcomeStep(viewModel)
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

// ── Step: Welcome ─────────────────────────────────────────────────────────────

@Composable
private fun WelcomeStep(viewModel: OnboardingViewModel) {
    Column(
        modifier = Modifier
            .fillMaxSize()
            .padding(32.dp),
        horizontalAlignment = Alignment.CenterHorizontally,
        verticalArrangement = Arrangement.Center,
    ) {
        Spacer(Modifier.weight(1f))

        AppLogo(size = 88.dp)

        Spacer(Modifier.height(28.dp))

        Text(
            text = "SMS Bridge",
            style = MaterialTheme.typography.displaySmall,
            fontWeight = FontWeight.Bold,
            textAlign = TextAlign.Center,
        )
        Spacer(Modifier.height(8.dp))
        Text(
            text = "AI-powered SMS gateway",
            style = MaterialTheme.typography.titleMedium,
            color = MaterialTheme.colorScheme.primary,
            textAlign = TextAlign.Center,
        )

        Spacer(Modifier.height(32.dp))

        Text(
            text = "Connect this phone to your AI agent framework. Once set up, your agents can send and receive SMS through this device — no carrier API required.",
            style = MaterialTheme.typography.bodyLarge,
            textAlign = TextAlign.Center,
            color = MaterialTheme.colorScheme.onSurfaceVariant,
        )

        Spacer(Modifier.weight(1f))

        Button(
            onClick = { viewModel.onGetStarted() },
            modifier = Modifier
                .fillMaxWidth()
                .height(52.dp),
        ) {
            Text("Get Started", style = MaterialTheme.typography.titleMedium)
        }

        Spacer(Modifier.height(16.dp))

        Text(
            text = "You'll need your gateway server running and ready.",
            style = MaterialTheme.typography.bodySmall,
            color = MaterialTheme.colorScheme.outline,
            textAlign = TextAlign.Center,
        )

        Spacer(Modifier.height(8.dp))
    }
}

// ── Step: QR Scanner ─────────────────────────────────────────────────────────

@androidx.annotation.OptIn(androidx.camera.core.ExperimentalGetImage::class)
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
        modifier = Modifier
            .fillMaxSize()
            .padding(horizontal = 24.dp, vertical = 16.dp),
        horizontalAlignment = Alignment.CenterHorizontally,
    ) {

        // ── Top bar: logo + app name ──────────────────────────────────────
        Row(
            verticalAlignment = Alignment.CenterVertically,
            modifier = Modifier.fillMaxWidth(),
        ) {
            AppLogo(size = 36.dp)
            Spacer(Modifier.width(10.dp))
            Text(
                text = "SMS Bridge",
                style = MaterialTheme.typography.titleLarge,
                fontWeight = FontWeight.SemiBold,
            )
        }

        Spacer(Modifier.height(32.dp))

        // ── Instruction ───────────────────────────────────────────────────
        Text(
            text = "Scan SMS Gateway Server\nConfig QR Code",
            style = MaterialTheme.typography.headlineSmall,
            fontWeight = FontWeight.Medium,
            textAlign = TextAlign.Center,
            modifier = Modifier.fillMaxWidth(),
        )

        Spacer(Modifier.height(8.dp))

        Text(
            text = "Run  sms-bridge qr  on your server to display the code.",
            style = MaterialTheme.typography.bodySmall,
            color = MaterialTheme.colorScheme.outline,
            textAlign = TextAlign.Center,
        )

        Spacer(Modifier.weight(1f))

        // ── Camera viewfinder (centred) ───────────────────────────────────
        if (hasCameraPermission) {
            val executor = remember { Executors.newSingleThreadExecutor() }

            Box(
                modifier = Modifier
                    .fillMaxWidth()
                    .aspectRatio(1f),          // square viewfinder
                contentAlignment = Alignment.Center,
            ) {
                AndroidView(
                    modifier = Modifier.fillMaxSize(),
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
                                                    .addOnSuccessListener(
                                                        ContextCompat.getMainExecutor(ctx)
                                                    ) { barcodes ->
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

                // Corner bracket overlay
                ScannerBrackets()
            }
        } else {
            // Camera permission denied / not yet granted
            Box(
                modifier = Modifier
                    .fillMaxWidth()
                    .aspectRatio(1f),
                contentAlignment = Alignment.Center,
            ) {
                Card(modifier = Modifier.fillMaxWidth()) {
                    Text(
                        text = "Camera permission is required to scan the QR code.",
                        modifier = Modifier.padding(24.dp),
                        textAlign = TextAlign.Center,
                        style = MaterialTheme.typography.bodyMedium,
                    )
                }
            }
        }

        Spacer(Modifier.weight(1f))

        TextButton(onClick = { showManualEntry = true }) {
            Text("Enter server details manually ›")
        }

        Spacer(Modifier.height(8.dp))
    }
}

/** Four corner brackets drawn over the viewfinder to guide framing. */
@Composable
private fun ScannerBrackets() {
    val color = Color.White
    val strokeWidth = 4.dp
    val bracketLength = 32.dp
    val inset = 24.dp

    Box(modifier = Modifier.fillMaxSize()) {
        // Top-left
        BracketCorner(Alignment.TopStart, color, strokeWidth, bracketLength, inset)
        // Top-right
        BracketCorner(Alignment.TopEnd, color, strokeWidth, bracketLength, inset)
        // Bottom-left
        BracketCorner(Alignment.BottomStart, color, strokeWidth, bracketLength, inset)
        // Bottom-right
        BracketCorner(Alignment.BottomEnd, color, strokeWidth, bracketLength, inset)
    }
}

@Composable
private fun BoxScope.BracketCorner(
    alignment: Alignment,
    color: Color,
    strokeWidth: Dp,
    length: Dp,
    inset: Dp,
) {
    val isTop    = alignment == Alignment.TopStart || alignment == Alignment.TopEnd
    val isLeft   = alignment == Alignment.TopStart || alignment == Alignment.BottomStart

    Box(
        modifier = Modifier
            .align(alignment)
            .padding(inset)
    ) {
        // Horizontal arm
        Box(
            modifier = Modifier
                .width(length)
                .height(strokeWidth)
                .align(if (isLeft) Alignment.TopStart else Alignment.TopEnd)
                .background(color)
        )
        // Vertical arm
        Box(
            modifier = Modifier
                .width(strokeWidth)
                .height(length)
                .align(if (isLeft) Alignment.TopStart else Alignment.TopEnd)
                .background(color)
        )
    }
}

// ── Manual entry dialog ───────────────────────────────────────────────────────

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

// ── Step: Connecting ──────────────────────────────────────────────────────────

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

// ── Step: Connection Error ────────────────────────────────────────────────────

@Composable
private fun ConnectionErrorStep(message: String, viewModel: OnboardingViewModel) {
    Column(
        modifier = Modifier
            .fillMaxSize()
            .padding(24.dp),
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

// ── Step: Permissions ─────────────────────────────────────────────────────────

@Composable
private fun PermissionsStep(viewModel: OnboardingViewModel) {
    var receiveSmsGranted by remember { mutableStateOf(false) }
    var sendSmsGranted    by remember { mutableStateOf(false) }

    val multiPermissionLauncher = rememberLauncherForActivityResult(
        ActivityResultContracts.RequestMultiplePermissions()
    ) { results ->
        receiveSmsGranted = results[Manifest.permission.RECEIVE_SMS] == true
        sendSmsGranted    = results[Manifest.permission.SEND_SMS]    == true
    }

    val allGranted = receiveSmsGranted && sendSmsGranted

    LaunchedEffect(Unit) {
        multiPermissionLauncher.launch(
            arrayOf(Manifest.permission.RECEIVE_SMS, Manifest.permission.SEND_SMS)
        )
    }

    Column(
        modifier = Modifier
            .fillMaxSize()
            .padding(24.dp),
        verticalArrangement = Arrangement.spacedBy(16.dp),
    ) {
        Spacer(Modifier.height(32.dp))
        Text("Grant permissions", style = MaterialTheme.typography.headlineMedium)
        Text("These are required for the bridge to work reliably.", style = MaterialTheme.typography.bodyMedium)

        PermissionRow("Receive SMS",   receiveSmsGranted) {
            multiPermissionLauncher.launch(arrayOf(Manifest.permission.RECEIVE_SMS))
        }
        PermissionRow("Send SMS",      sendSmsGranted) {
            multiPermissionLauncher.launch(arrayOf(Manifest.permission.SEND_SMS))
        }
        PermissionRow("Start on boot", true, canGrant = false) {}

        Text(
            "Start on boot ensures the bridge restarts automatically after the device reboots.",
            style = MaterialTheme.typography.bodySmall,
            color = MaterialTheme.colorScheme.outline,
        )

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
            text = if (granted) "✓  $label" else "○  $label",
            style = MaterialTheme.typography.bodyLarge,
        )
        if (!granted && canGrant) {
            OutlinedButton(onClick = onGrant) { Text("Grant") }
        }
    }
}

// ── Step: Battery Optimisation ────────────────────────────────────────────────

@Composable
private fun BatteryStep(onComplete: () -> Unit) {
    val context = LocalContext.current

    Column(
        modifier = Modifier
            .fillMaxSize()
            .padding(24.dp),
        verticalArrangement = Arrangement.spacedBy(16.dp),
    ) {
        Spacer(Modifier.height(32.dp))
        Text("Allow background activity", style = MaterialTheme.typography.headlineMedium)
        Text(
            "Android may put this app to sleep to save battery. Disabling this ensures reliable message delivery.",
            style = MaterialTheme.typography.bodyMedium,
        )

        Card(
            colors = CardDefaults.cardColors(
                containerColor = MaterialTheme.colorScheme.errorContainer,
            )
        ) {
            Text(
                text = "⚠ Without this, Android may delay message delivery by up to 15 minutes during Doze mode. The FCM fallback will still wake the app, but with higher latency.",
                modifier = Modifier.padding(16.dp),
                style = MaterialTheme.typography.bodySmall,
                color = MaterialTheme.colorScheme.onErrorContainer,
            )
        }

        Spacer(Modifier.weight(1f))

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
