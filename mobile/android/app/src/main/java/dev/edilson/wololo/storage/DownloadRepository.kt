package dev.edilson.wololo.storage

import android.content.Context
import androidx.datastore.preferences.core.edit
import androidx.datastore.preferences.core.stringPreferencesKey
import androidx.datastore.preferences.preferencesDataStore
import androidx.work.*
import dev.edilson.wololo.api.WololoApi
import dev.edilson.wololo.links.LinkParser
import dev.edilson.wololo.model.AppSettings
import dev.edilson.wololo.model.DownloadRecord
import dev.edilson.wololo.security.AccessKeyStore
import dev.edilson.wololo.worker.DownloadWorker
import java.util.UUID
import java.util.concurrent.TimeUnit
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.withTimeoutOrNull
import kotlinx.coroutines.flow.*
import kotlinx.serialization.encodeToString

private val Context.wololoDataStore by preferencesDataStore("wololo")

class DownloadRepository(private val context: Context, scope: CoroutineScope) {
    private val store = context.wololoDataStore
    private val historyKey = stringPreferencesKey("downloads")
    private val serverKey = stringPreferencesKey("server")
    private val qualityKey = stringPreferencesKey("quality")
    private val videoQualityKey = stringPreferencesKey("video_quality")
    val credentials = AccessKeyStore(context)
    val history = store.data.map { decode(it[historyKey]) }
        .stateIn(scope, SharingStarted.Eagerly, emptyList())
    val settings = store.data.map {
        AppSettings(it[serverKey] ?: AppSettings().server, it[qualityKey] ?: "720p", it[videoQualityKey] ?: "720p")
    }.stateIn(scope, SharingStarted.Eagerly, AppSettings())

    suspend fun currentSettings(): AppSettings {
        val value = store.data.first()
        return AppSettings(value[serverKey] ?: AppSettings().server, value[qualityKey] ?: "720p", value[videoQualityKey] ?: "720p")
    }

    suspend fun saveSettings(server: String, key: String, quality: String) {
        val address = server.trim().trimEnd('/')
        WololoApi(address, key)
        credentials.write(address, key)
        store.edit {
            it[serverKey] = address
            it[qualityKey] = quality
            if (quality != "mp3") it[videoQualityKey] = quality
        }
    }

    suspend fun rememberQuality(quality: String) {
        store.edit {
            it[qualityKey] = quality
            if (quality != "mp3") it[videoQualityKey] = quality
        }
    }

    suspend fun record(id: String): DownloadRecord? = decode(store.data.first()[historyKey]).find { it.id == id }

    suspend fun update(id: String, transform: (DownloadRecord) -> DownloadRecord) {
        store.edit { preferences ->
            val records = decode(preferences[historyKey]).map { if (it.id == id) transform(it) else it }
            preferences[historyKey] = WololoApi.json.encodeToString(trim(records))
        }
    }

    suspend fun updateActive(id: String, transform: (DownloadRecord) -> DownloadRecord) {
        update(id) { if (it.isTerminal) it else transform(it) }
    }

    suspend fun enqueue(text: String, quality: String, server: String? = null): String {
        val link = LinkParser.first(text) ?: throw IllegalArgumentException("Share or paste a supported video link.")
        val settings = currentSettings()
        val id = UUID.randomUUID()
        val record = DownloadRecord(id.toString(), link.url, if (link.platform == "music") "mp3" else quality, server ?: settings.server)
        store.edit { preferences ->
            preferences[historyKey] = WololoApi.json.encodeToString(trim(listOf(record) + decode(preferences[historyKey])))
        }
        schedule(record.id)
        return record.id
    }

    private fun schedule(recordId: String) {
        val request = OneTimeWorkRequestBuilder<DownloadWorker>()
            .setId(UUID.fromString(recordId))
            .setInputData(workDataOf("record_id" to recordId))
            .setConstraints(Constraints.Builder().setRequiredNetworkType(NetworkType.CONNECTED).build())
            .setBackoffCriteria(BackoffPolicy.EXPONENTIAL, 30, TimeUnit.SECONDS)
            .addTag("wololo-download")
            .build()
        WorkManager.getInstance(context).enqueueUniqueWork(recordId, ExistingWorkPolicy.KEEP, request)
    }

    suspend fun reconcilePending() {
        val manager = WorkManager.getInstance(context)
        for (record in decode(store.data.first()[historyKey]).filterNot { it.isTerminal }) {
            val work = manager.getWorkInfoById(UUID.fromString(record.id)).get()
            if (work == null) schedule(record.id)
            else if (work.state.isFinished) updateActive(record.id) {
                it.copy(status = "failed", error = context.getString(dev.edilson.wololo.R.string.interrupted), completedAt = System.currentTimeMillis())
            }
        }
    }

    suspend fun cancel(id: String) {
        update(id) { if (it.isTerminal) it else it.copy(status = "cancelled", completedAt = System.currentTimeMillis()) }
        WorkManager.getInstance(context).cancelWorkById(UUID.fromString(id))
        val record = record(id) ?: return
        record.jobId?.let { jobId ->
            withTimeoutOrNull(5_000) {
                runCatching { WololoApi(record.server, credentials.read(record.server)).cancel(jobId) }
            }
        }
    }

    private fun decode(value: String?): List<DownloadRecord> = value?.let { WololoApi.json.decodeFromString(it) } ?: emptyList()

    private fun trim(records: List<DownloadRecord>): List<DownloadRecord> {
        val active = records.filterNot { it.isTerminal }
        val completed = records.filter { it.isTerminal }.take(50)
        return (active + completed).sortedByDescending { it.createdAt }
    }
}
