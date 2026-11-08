package dev.edilson.wololo.links

import java.net.URI
import java.net.URLDecoder

data class MediaLink(val url: String, val platform: String)

object LinkParser {
    private val patterns = linkedMapOf(
        "youtube" to listOf(
            "(?:(?:www|m|music)\\.)?youtube\\.com/watch\\?(?:[^#]*&)?v=[\\w-]+.*",
            "(?:(?:www|m)\\.)?youtube\\.com/(?:shorts|live|embed)/[\\w-]+.*",
            "youtu\\.be/[\\w-]+.*",
        ),
        "instagram" to listOf("(?:www\\.)?instagram\\.com/(?:p|reels?|tv|share/(?:p|reel))/[\\w-]+.*"),
        "tiktok" to listOf(
            "(?:www\\.)?tiktok\\.com/@[\\w.]+/video/\\d+.*",
            "(?:vm|vt)\\.tiktok\\.com/[\\w]+.*",
            "(?:www\\.)?tiktok\\.com/t/[\\w]+.*",
        ),
        "twitter" to listOf("(?:www\\.)?(?:twitter|x)\\.com/\\w+/status/\\d+.*"),
        "threads" to listOf(
            "(?:www\\.)?threads\\.(?:net|com)/@[\\w.]+/post/[\\w]+.*",
            "(?:www\\.)?threads\\.(?:net|com)/share/[\\w-]+(?:/|[?#]|$).*",
        ),
        "facebook" to listOf(
            "(?:www\\.)?facebook\\.com/.+/videos/\\d+.*",
            "(?:www\\.)?facebook\\.com/watch/?\\?v=\\d+.*",
            "fb\\.watch/[\\w-]+.*",
        ),
        "music" to listOf("(?:www\\.)?artlist\\.io/royalty-free-music/(?:album|song)/[^/?#\\s]+/\\d+.*"),
    ).mapValues { (_, values) -> values.map { Regex("^(?:https?://)?$it$", RegexOption.IGNORE_CASE) } }

    fun first(text: String): MediaLink? = text.split(Regex("[\\s,]+"))
        .firstNotNullOfOrNull { parse(it.trim('(', ')', '[', ']', '<', '>', '"', '\'', '.', '!')) }

    fun parse(value: String): MediaLink? {
        val platform = patterns.entries.firstOrNull { (_, patterns) -> patterns.any { it.matches(value) } }?.key
            ?: return null
        val source = if (value.startsWith("http", true)) value else "https://$value"
        return runCatching {
            val uri = URI(source)
            if (uri.userInfo != null || uri.port != -1) return null
            val query = uri.rawQuery.orEmpty().split('&').mapNotNull {
                val pair = it.split('=', limit = 2)
                if (pair.size == 2) pair[0] to URLDecoder.decode(pair[1], "UTF-8") else null
            }.toMap()
            val videoId = query["v"]
            val normalized = when {
                platform == "youtube" && uri.path == "/watch" && videoId != null -> "https://youtu.be/$videoId"
                platform == "youtube" && uri.host.equals("youtu.be", true) -> "https://youtu.be/${uri.path.trim('/').substringBefore('/')}"
                platform == "facebook" && uri.path.trimEnd('/') == "/watch" -> "https://${uri.host}/watch/?v=$videoId"
                else -> URI("https", null, uri.host.lowercase(), -1, uri.path, null, null).toString()
            }
            MediaLink(normalized, platform)
        }.getOrNull()
    }
}
