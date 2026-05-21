package com.agentic.smsbridge.receiver

import android.content.BroadcastReceiver
import android.content.Context
import android.content.Intent
import android.util.Log
import com.agentic.smsbridge.data.BridgeRepository
import com.agentic.smsbridge.service.BridgeService
import dagger.hilt.android.AndroidEntryPoint
import javax.inject.Inject

private const val TAG = "BootReceiver"

@AndroidEntryPoint
class BootReceiver : BroadcastReceiver() {

    @Inject
    lateinit var repository: BridgeRepository

    override fun onReceive(context: Context, intent: Intent) {
        val action = intent.action ?: return
        if (action !in listOf(
                Intent.ACTION_BOOT_COMPLETED,
                Intent.ACTION_MY_PACKAGE_REPLACED,
            )
        ) return

        if (!repository.prefs.isConfigured()) {
            Log.d(TAG, "Not configured — skipping auto-start on $action")
            return
        }

        Log.i(TAG, "Starting BridgeService on $action")
        BridgeService.start(context)
    }
}
