package com.agentic.smsbridge.ui.theme

import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.darkColorScheme
import androidx.compose.material3.lightColorScheme
import androidx.compose.runtime.Composable
import androidx.compose.ui.graphics.Color

private val Green   = Color(0xFF4CAF50)
private val Amber   = Color(0xFFFFC107)
private val Red     = Color(0xFFF44336)
private val Primary = Color(0xFF1976D2)

val LightColors = lightColorScheme(
    primary   = Primary,
    secondary = Color(0xFF455A64),
    surface   = Color(0xFFFAFAFA),
    background = Color(0xFFF5F5F5),
)

val DarkColors = darkColorScheme(
    primary   = Color(0xFF90CAF9),
    secondary = Color(0xFF90A4AE),
    surface   = Color(0xFF1E1E1E),
    background = Color(0xFF121212),
)

// Status colours used across screens
object StatusColor {
    val Connected    = Green
    val Warning      = Amber
    val Error        = Red
    val Disconnected = Red
}

@Composable
fun SmsBridgeTheme(
    darkTheme: Boolean = false,
    content: @Composable () -> Unit,
) {
    MaterialTheme(
        colorScheme = if (darkTheme) DarkColors else LightColors,
        content     = content,
    )
}
