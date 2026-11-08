package dev.edilson.wololo

import android.app.Application
import dev.edilson.wololo.storage.DownloadRepository
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.SupervisorJob
import kotlinx.coroutines.launch

class WololoApplication : Application() {
    val scope = CoroutineScope(SupervisorJob() + Dispatchers.IO)
    val repository by lazy { DownloadRepository(this, scope) }

    override fun onCreate() {
        super.onCreate()
        scope.launch { repository.reconcilePending() }
    }
}
