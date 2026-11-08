package dev.edilson.wololo

import dev.edilson.wololo.links.LinkParser
import dev.edilson.wololo.model.isNewerVersion
import org.junit.Assert.*
import org.junit.Test

class LinkParserTest {
    @Test fun sharedTextReturnsFirstSupportedLink() {
        val link = LinkParser.first("Watch this https://example.com/other https://x.com/pardald3sign/status/2092425556650242194?s=48")
        assertEquals("https://x.com/pardald3sign/status/2092425556650242194", link?.url)
        assertEquals("twitter", link?.platform)
    }

    @Test fun threadsShareLinksPreserveTheirCode() {
        for (host in listOf("www.threads.com", "threads.com", "www.threads.net")) {
            val url = "https://$host/share/BAR2SGFo1r/"
            assertEquals(url, LinkParser.parse("$url?tracking=1")?.url)
        }
    }

    @Test fun sharedVariantsMatchWebsite() {
        val cases = listOf(
            "https://m.youtube.com/watch?v=dQw4w9WgXcQ" to "https://youtu.be/dQw4w9WgXcQ",
            "www.instagram.com/share/reel/ABC123/" to "https://www.instagram.com/share/reel/ABC123/",
            "vt.tiktok.com/ZMkABC123/" to "https://vt.tiktok.com/ZMkABC123/",
            "https://www.youtube.com/watch?v=dQw4w9WgXcQ&t=95&list=playlist" to "https://youtu.be/dQw4w9WgXcQ",
            "https://www.instagram.com/reel/ABC123/?igsh=tracking#fragment" to "https://www.instagram.com/reel/ABC123/",
            "https://youtu.be/abc123?si=tracking" to "https://youtu.be/abc123",
        )
        for ((source, expected) in cases) assertEquals(source, expected, LinkParser.parse(source)?.url)
    }

    @Test fun punctuationAndMissingProtocolAreAccepted() {
        assertEquals("https://x.com/user/status/123456", LinkParser.first("Look (x.com/user/status/123456).")?.url)
        assertNotNull(LinkParser.first("https://www.youtube.com/shorts/xyz_123"))
    }

    @Test fun unsupportedAndSpoofedDomainsAreRejected() {
        for (url in listOf(
            "https://example.com/video", "https://evil.com/x.com/user/status/123", "https://x.com.evil.test/user/status/123",
            "https://x.com@evil.test/user/status/123", "file://x.com/user/status/123", "https://x.com/user",
            "https://x.com:443/user/status/123", "https://www.threads.com/share/", "https://artlist.io/royalty-free-music/artist/djnoone/2901",
        )) assertNull(url, LinkParser.parse(url))
    }

    @Test fun privatePagePatternsAreRecognizedWithoutDisplayPlatformList() {
        val link = LinkParser.parse("https://artlist.io/royalty-free-music/song/earthquake/6002056?ref=x")
        assertEquals("music", link?.platform)
        assertEquals("https://artlist.io/royalty-free-music/song/earthquake/6002056", link?.url)
    }

    @Test fun appVersionsAreComparedNumerically() {
        assertTrue(isNewerVersion("1.10.0", "1.9.0"))
        assertTrue(isNewerVersion("2.0.0", "1.9.0"))
        assertFalse(isNewerVersion("1.0.0", "1.0"))
        assertFalse(isNewerVersion("invalid", "1.0.0"))
        assertFalse(isNewerVersion("0.9.0", "1.0.0"))
    }
}
