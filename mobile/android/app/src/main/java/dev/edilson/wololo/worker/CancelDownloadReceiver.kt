package dev.edilson.wololo.worker

import android.content.BroadcastReceiver
import android.content.Context
import android.content.Intent
import dev.edilson.wololo.WololoApplication
import kotlinx.coroutines.launch

class CancelDownloadReceiver : BroadcastReceiver() {
    override fun onReceive(context: Context, intent: Intent) {
        val id = intent.getStringExtra("record_id") ?: return
        val pending = goAsync()
        val app = context.applicationContext as WololoApplication
        app.scope.launch {
            try { app.repository.cancel(id) } finally { pending.finish() }
        }
    }
}
