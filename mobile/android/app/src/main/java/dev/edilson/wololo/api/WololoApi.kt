package dev.edilson.wololo.api

import dev.edilson.wololo.model.*
import java.io.IOException
import java.util.concurrent.TimeUnit
import kotlin.coroutines.resume
import kotlin.coroutines.resumeWithException
import kotlinx.coroutines.suspendCancellableCoroutine
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.ExperimentalCoroutinesApi
import kotlinx.coroutines.withContext
import kotlinx.serialization.encodeToString
import kotlinx.serialization.json.Json
import kotlinx.serialization.json.jsonArray
import kotlinx.serialization.json.jsonObject
import kotlinx.serialization.json.jsonPrimitive
import okhttp3.*
import okhttp3.HttpUrl.Companion.toHttpUrl
import okhttp3.MediaType.Companion.toMediaType
import okhttp3.RequestBody.Companion.toRequestBody

class ApiException(val code: Int, message: String) : IOException(message)

class WololoApi(server: String, private val key: String, private val client: OkHttpClient = http) {
    private val base = server.trimEnd('/').toHttpUrl()
    init {
        require(base.isHttps) { "Use an HTTPS server address." }
        require(base.username.isEmpty() && base.password.isEmpty()) { "Enter the access key separately." }
    }

    suspend fun health(): ServerHealth = json.decodeFromString(read(request("health")))
    suspend fun start(url: String, quality: String): StartedJob = json.decodeFromString(
        read(request("download").post(json.encodeToString(StartRequest(url, quality)).body())),
    )
    suspend fun job(jobId: String): RemoteJob = json.decodeFromString(read(request("jobs/$jobId")))
    suspend fun cancel(jobId: String) { read(request("jobs/$jobId").delete()) }
    suspend fun resolve(url: String): ResolvedPage = json.decodeFromString(
        read(request("resolve").post(json.encodeToString(ResolveRequest(url)).body())),
    )
    suspend fun file(jobId: String): Response = execute(request("jobs/$jobId/download"))

    private fun request(path: String): Request.Builder {
        val url = base.newBuilder().addPathSegments("api/$path").build()
        return Request.Builder().url(url).apply {
            if (key.isNotBlank()) header("X-Wololo-Key", key)
        }
    }

    private suspend fun read(builder: Request.Builder): String = withContext(Dispatchers.IO) {
        execute(builder).use { response ->
            response.body?.string() ?: throw IOException("The server returned an empty response.")
        }
    }

    private suspend fun execute(builder: Request.Builder): Response {
        val response = client.newCall(builder.build()).await()
        if (!response.isSuccessful) {
            val status = response.code
            val detail = response.use { it.body?.string().orEmpty() }
            throw ApiException(status, errorMessage(status, detail))
        }
        return response
    }

    companion object {
        val json = Json { ignoreUnknownKeys = true }
        val http = OkHttpClient.Builder()
            .connectTimeout(15, TimeUnit.SECONDS)
            .readTimeout(180, TimeUnit.SECONDS)
            .followRedirects(false)
            .followSslRedirects(false)
            .build()

        fun errorMessage(code: Int, body: String): String {
            val fallback = when (code) {
                401 -> "The access key is invalid. Check Settings."
                404 -> "This download has expired or is unavailable. Try again."
                429 -> "The server is busy. Please try again shortly."
                else -> "The server could not complete this request ($code)."
            }
            return runCatching {
                val detail = json.parseToJsonElement(body).jsonObject["detail"] ?: return fallback
                runCatching { detail.jsonPrimitive.content }.getOrElse {
                    detail.jsonArray.joinToString(" ") { it.jsonObject["msg"]?.jsonPrimitive?.content.orEmpty() }
                }.take(500).ifBlank { fallback }
            }.getOrDefault(fallback)
        }
    }
}

private fun String.body() = toRequestBody("application/json".toMediaType())

@OptIn(ExperimentalCoroutinesApi::class)
private suspend fun Call.await(): Response = suspendCancellableCoroutine { continuation ->
    continuation.invokeOnCancellation { cancel() }
    enqueue(object : Callback {
        override fun onFailure(call: Call, error: IOException) {
            if (!continuation.isCancelled) continuation.resumeWithException(error)
        }
        override fun onResponse(call: Call, response: Response) {
            continuation.resume(response) { response.close() }
        }
    })
}
