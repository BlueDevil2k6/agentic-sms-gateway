package com.agentic.smsbridge

import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.activity.enableEdgeToEdge
import androidx.navigation.compose.rememberNavController
import com.agentic.smsbridge.data.BridgeRepository
import com.agentic.smsbridge.ui.navigation.NavGraph
import com.agentic.smsbridge.ui.navigation.Routes
import com.agentic.smsbridge.ui.theme.SmsBridgeTheme
import dagger.hilt.android.AndroidEntryPoint
import javax.inject.Inject

@AndroidEntryPoint
class MainActivity : ComponentActivity() {

    @Inject
    lateinit var repository: BridgeRepository

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        enableEdgeToEdge()

        val startDestination = if (repository.prefs.isConfigured()) {
            Routes.DASHBOARD
        } else {
            Routes.ONBOARDING
        }

        setContent {
            SmsBridgeTheme {
                val navController = rememberNavController()
                NavGraph(
                    navController    = navController,
                    startDestination = startDestination,
                )
            }
        }
    }
}
