package dev.edilson.wololo

import dev.edilson.wololo.api.ApiException
import dev.edilson.wololo.api.WololoApi
import kotlinx.coroutines.test.runTest
import okhttp3.*
import okhttp3.MediaType.Companion.toMediaType
import okhttp3.ResponseBody.Companion.toResponseBody
import okio.Buffer
import org.junit.Assert.*
import org.junit.Test

class WololoApiTest {
    private fun client(body: String, code: Int = 200, inspect: (Request) -> Unit = {}) = OkHttpClient.Builder().addInterceptor {
        val request = it.request()
        inspect(request)
        Response.Builder().request(request).protocol(Protocol.HTTP_1_1).code(code).message("Test")
            .body(body.toResponseBody("application/json".toMediaType())).build()
    }.build()

    @Test fun startUsesAccessKeyAndQualityContract() = runTest {
        val client = client("""{"job_id":"job-123","status":"queued","message":"Download started"}""") { request ->
            assertEquals("POST", request.method)
            assertEquals("/api/download", request.url.encodedPath)
            assertEquals("my-key", request.header("X-Wololo-Key"))
            val buffer = Buffer()
            request.body!!.writeTo(buffer)
            assertEquals("""{"url":"https://youtu.be/abc","quality":"mp3"}""", buffer.readUtf8())
        }
        val job = WololoApi("https://example.test", "my-key", client).start("https://youtu.be/abc", "mp3")
        assertEquals("job-123", job.jobId)
    }

    @Test fun healthToleratesOlderServerAndUnknownFields() = runTest {
        val response = """{"status":"healthy","version":"0.8.1","active_downloads":2}"""
        val api = WololoApi("https://example.test", "", client(response) { assertNull(it.header("X-Wololo-Key")) })
        assertNull(api.health().minAppVersion)
    }

    @Test fun healthReadsMinimumMobileVersion() = runTest {
        val api = WololoApi("https://example.test", "", client("""{"status":"healthy","version":"0.9.0","min_app_version":"1.0.0"}"""))
        assertEquals("1.0.0", api.health().minAppVersion)
    }

    @Test fun serverErrorsPreserveStatusAndDetail() = runTest {
        val api = WololoApi("https://example.test", "", client("""{"detail":"Download queue is full"}""", 429))
        try {
            api.health()
            fail("Expected server error")
        } catch (error: ApiException) {
            assertEquals(429, error.code)
            assertEquals("Download queue is full", error.message)
        }
    }

    @Test fun cancelUsesDeleteAndJobID() = runTest {
        val api = WololoApi("https://example.test", "", client("""{"message":"Job cancelled"}""") {
            assertEquals("DELETE", it.method)
            assertEquals("/api/jobs/abc-123", it.url.encodedPath)
        })
        api.cancel("abc-123")
    }

    @Test fun cleartextAndEmbeddedCredentialsAreRejected() {
        for (server in listOf("http://example.test", "https://user:pass@example.test")) {
            try { WololoApi(server, ""); fail("Expected invalid server rejection") }
            catch (_: IllegalArgumentException) { }
        }
    }

    @Test fun structuredValidationErrorsAreReadable() {
        assertEquals("Invalid URL", WololoApi.errorMessage(422, """{"detail":[{"msg":"Invalid URL"}]}"""))
        assertTrue(WololoApi.errorMessage(401, "not json").contains("key"))
    }
}
