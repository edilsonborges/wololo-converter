package dev.edilson.wololo.model

import kotlinx.serialization.SerialName
import kotlinx.serialization.Serializable

@Serializable
data class ServerHealth(
    val status: String,
    val version: String,
    @SerialName("min_app_version") val minAppVersion: String? = null,
)

@Serializable
data class StartRequest(val url: String, val quality: String)

@Serializable
data class StartedJob(@SerialName("job_id") val jobId: String, val status: String)

@Serializable
data class RemoteJob(
    val id: String,
    val status: String,
    val progress: Double = 0.0,
    val title: String? = null,
    val filename: String? = null,
    @SerialName("file_size") val fileSize: Long? = null,
    @SerialName("error_message") val errorMessage: String? = null,
    @SerialName("current_stage") val currentStage: String? = null,
)

@Serializable
data class ResolveRequest(val url: String)

@Serializable
data class ResolvedPage(val album: String, val tracks: List<ResolvedTrack>)

@Serializable
data class ResolvedTrack(val title: String, @SerialName("video_url") val videoUrl: String? = null)

@Serializable
data class DownloadRecord(
    val id: String,
    val url: String,
    val quality: String,
    val server: String,
    val title: String = "",
    val status: String = "queued",
    val progress: Float = 0f,
    val jobId: String? = null,
    val fileUri: String? = null,
    val pendingUri: String? = null,
    val error: String? = null,
    val createdAt: Long = System.currentTimeMillis(),
    val completedAt: Long? = null,
) {
    val isTerminal: Boolean get() = status in setOf("completed", "failed", "cancelled")
    val isAudio: Boolean get() = quality == "mp3"
}

data class AppSettings(
    val server: String = "https://wololo.edilson.dev",
    val quality: String = "720p",
    val videoQuality: String = "720p",
)

fun isNewerVersion(required: String, current: String): Boolean {
    val requiredParts = required.split('.').map { it.toIntOrNull() ?: return false }
    val currentParts = current.split('.').map { it.toIntOrNull() ?: return false }
    for (index in 0 until maxOf(requiredParts.size, currentParts.size)) {
        val difference = requiredParts.getOrElse(index) { 0 }.compareTo(currentParts.getOrElse(index) { 0 })
        if (difference != 0) return difference > 0
    }
    return false
}
