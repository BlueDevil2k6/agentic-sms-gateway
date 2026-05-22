package com.agentic.smsbridge.ui.navigation

import androidx.compose.foundation.layout.safeDrawingPadding
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.runtime.Composable
import androidx.compose.ui.Modifier
import androidx.navigation.NavHostController
import androidx.navigation.compose.NavHost
import androidx.navigation.compose.composable
import com.agentic.smsbridge.ui.dashboard.DashboardScreen
import com.agentic.smsbridge.ui.onboarding.OnboardingScreen
import com.agentic.smsbridge.ui.settings.SettingsScreen

object Routes {
    const val ONBOARDING = "onboarding"
    const val DASHBOARD  = "dashboard"
    const val SETTINGS   = "settings"
}

@Composable
fun NavGraph(
    navController: NavHostController,
    startDestination: String,
) {
    NavHost(
        navController     = navController,
        startDestination  = startDestination,
        modifier          = Modifier
            .fillMaxSize()
            .safeDrawingPadding(),   // respects status bar (top) + nav bar (bottom)
    ) {
        composable(Routes.ONBOARDING) {
            OnboardingScreen(
                onConfigured = {
                    navController.navigate(Routes.DASHBOARD) {
                        popUpTo(Routes.ONBOARDING) { inclusive = true }
                    }
                }
            )
        }
        composable(Routes.DASHBOARD) {
            DashboardScreen(
                onOpenSettings = { navController.navigate(Routes.SETTINGS) }
            )
        }
        composable(Routes.SETTINGS) {
            SettingsScreen(
                onBack = { navController.popBackStack() },
                onReset = {
                    navController.navigate(Routes.ONBOARDING) {
                        popUpTo(0) { inclusive = true }
                    }
                }
            )
        }
    }
}
