package dev.edilson.wololo.worker

import android.content.Context
import androidx.work.CoroutineWorker
import androidx.work.WorkerParameters
import dev.edilson.wololo.BuildConfig
import dev.edilson.wololo.R
import dev.edilson.wololo.WololoApplication
import dev.edilson.wololo.api.ApiException
import dev.edilson.wololo.api.WololoApi
import dev.edilson.wololo.links.LinkParser
import dev.edilson.wololo.media.MediaSaver
import dev.edilson.wololo.model.isNewerVersion
import java.io.IOException
import kotlinx.coroutines.*

class DownloadWorker(context: Context, parameters: WorkerParameters) : CoroutineWorker(context, parameters) {
    private val repository = (context.applicationContext as WololoApplication).repository
    private val recordId = inputData.getString("record_id").orEmpty()
    private val notifications = DownloadNotifications(context, recordId)
    private val saver = MediaSaver(context)

    override suspend fun doWork(): Result {
        val record = repository.record(recordId) ?: return Result.failure()
        if (record.isTerminal) return Result.success()
        var api: WololoApi? = null
        var pendingFileUri: String? = record.pendingUri
        try {
            setForeground(notifications.foreground(record.title.ifBlank { applicationContext.getString(R.string.app_name) }, 0))
            api = WololoApi(record.server, repository.credentials.read(record.server))
            record.pendingUri?.let { saver.remove(it) }
            pendingFileUri = null
            repository.update(recordId) { it.copy(pendingUri = null) }
            val remaining = 15 * 60_000L - (System.currentTimeMillis() - record.createdAt)
            withTimeout(remaining.coerceAtLeast(1)) {
                val health = api.health()
                if (health.minAppVersion?.let { isNewerVersion(it, BuildConfig.VERSION_NAME) } == true) {
                    throw ApiException(426, applicationContext.getString(R.string.update_required))
                }
                if (LinkParser.parse(record.url)?.platform == "music") {
                    val page = api.resolve(record.url)
                    var count = 0
                    for (track in page.tracks) {
                        ensureActive()
                        track.videoUrl?.let { repository.enqueue(it, "mp3", record.server); count++ }
                    }
                    check(count > 0) { applicationContext.getString(R.string.no_matches) }
                    repository.updateActive(recordId) {
                        it.copy(status = "completed", title = page.album, progress = 100f,
                            error = applicationContext.getString(R.string.tracks_queued, count, page.tracks.size - count),
                            completedAt = System.currentTimeMillis())
                    }
                } else {
                    var jobId = record.jobId
                    if (jobId == null) {
                        jobId = api.start(record.url, record.quality).jobId
                        withContext(NonCancellable) {
                            repository.update(recordId) { it.copy(jobId = jobId) }
                        }
                    }
                    while (true) {
                        ensureActive()
                        if (repository.record(recordId)?.status == "cancelled") throw CancellationException()
                        val job = api.job(jobId)
                        when (job.status) {
                            "failed" -> throw ApiException(422, job.errorMessage ?: applicationContext.getString(R.string.download_failed))
                            "cancelled" -> {
                                repository.updateActive(recordId) { it.copy(status = "cancelled", completedAt = System.currentTimeMillis()) }
                                throw CancellationException()
                            }
                            "completed" -> {
                                val title = job.title ?: "Wololo"
                                val uri = saver.create(title, record.isAudio, recordId)
                                pendingFileUri = uri.toString()
                                repository.updateActive(recordId) { it.copy(status = "saving", title = title, pendingUri = uri.toString(), progress = 100f) }
                                api.file(jobId).use { response ->
                                    val body = response.body ?: throw IOException(applicationContext.getString(R.string.empty_file))
                                    saver.write(uri, body)
                                }
                                repository.updateActive(recordId) {
                                    it.copy(status = "completed", title = title, fileUri = uri.toString(), pendingUri = null,
                                        progress = 100f, error = null, completedAt = System.currentTimeMillis())
                                }
                                if (repository.record(recordId)?.status == "cancelled") throw CancellationException()
                                break
                            }
                            else -> {
                                repository.updateActive(recordId) {
                                    it.copy(status = job.status, title = job.title ?: it.title, progress = job.progress.toFloat(), error = null)
                                }
                                setForeground(notifications.foreground(job.title ?: applicationContext.getString(R.string.app_name), job.progress.toInt()))
                                delay(1_000)
                            }
                        }
                    }
                }
            }
            repository.record(recordId)?.let { notifications.finish(it) }
            return Result.success()
        } catch (error: TimeoutCancellationException) {
            fail(applicationContext.getString(R.string.timeout))
            cancelServer(api)
            return Result.failure()
        } catch (error: CancellationException) {
            withContext(NonCancellable) {
                if (repository.record(recordId)?.status == "cancelled") cancelServer(api)
            }
            throw error
        } catch (error: Exception) {
            val latest = repository.record(recordId)
            if (error is IOException && error !is ApiException && latest?.jobId != null && runAttemptCount < 3) {
                repository.updateActive(recordId) { it.copy(status = "queued", error = applicationContext.getString(R.string.reconnecting)) }
                return Result.retry()
            }
            fail(error.message ?: applicationContext.getString(R.string.download_failed))
            cancelServer(api)
            return Result.failure()
        } finally {
            withContext(NonCancellable) {
                val latest = repository.record(recordId)
                (pendingFileUri ?: latest?.pendingUri)?.let { uri ->
                    if (latest?.status != "completed" || latest.fileUri != uri) runCatching { saver.remove(uri) }
                    repository.update(recordId) { it.copy(pendingUri = null) }
                }
            }
        }
    }

    private suspend fun fail(message: String) {
        repository.updateActive(recordId) {
            it.copy(status = "failed", error = message, completedAt = System.currentTimeMillis())
        }
        repository.record(recordId)?.takeIf { it.status == "failed" }?.let { notifications.finish(it) }
    }

    private suspend fun cancelServer(api: WololoApi?) {
        val jobId = repository.record(recordId)?.jobId ?: return
        withTimeoutOrNull(5_000) { runCatching { api?.cancel(jobId) } }
    }
}
