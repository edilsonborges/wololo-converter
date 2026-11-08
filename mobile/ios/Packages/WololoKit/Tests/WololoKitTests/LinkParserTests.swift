import Foundation
import Testing
@testable import WololoKit

struct LinkParserTests {
    @Test(arguments: [
        ("https://www.threads.com/share/BAR2SGFo1r/?tracking=1", "https://www.threads.com/share/BAR2SGFo1r/", "threads"),
        ("https://threads.com/share/BAR2SGFo1r/", "https://threads.com/share/BAR2SGFo1r/", "threads"),
        ("https://www.threads.net/share/BAR2SGFo1r/", "https://www.threads.net/share/BAR2SGFo1r/", "threads"),
        ("https://m.youtube.com/watch?v=dQw4w9WgXcQ&t=95&list=playlist", "https://youtu.be/dQw4w9WgXcQ", "youtube"),
        ("https://music.youtube.com/watch?si=abc&v=dQw4w9WgXcQ", "https://youtu.be/dQw4w9WgXcQ", "youtube"),
        ("https://www.instagram.com/reel/ABC123/?igsh=tracking#fragment", "https://www.instagram.com/reel/ABC123/", "instagram"),
        ("www.instagram.com/share/reel/ABC123/", "https://www.instagram.com/share/reel/ABC123/", "instagram"),
        ("vt.tiktok.com/ZMkABC123/", "https://vt.tiktok.com/ZMkABC123/", "tiktok"),
        ("x.com/pardald3sign/status/2092425556650242194?s=48", "https://x.com/pardald3sign/status/2092425556650242194", "twitter"),
        ("https://wololo.edilson.dev/https:/x.com/user/status/123456", "https://x.com/user/status/123456", "twitter"),
        ("https://wololo.edilson.dev/https%3A%2F%2Fwww.instagram.com%2Freel%2FABC123%2F", "https://www.instagram.com/reel/ABC123/", "instagram"),
        ("https://artlist.io/royalty-free-music/song/earthquake/6002056?ref=x", "https://artlist.io/royalty-free-music/song/earthquake/6002056", "music")
    ])
    func normalizesSupportedLinks(input: String, expected: String, platform: String) throws {
        let parsed = try #require(LinkParser.firstSupportedLink(in: input))
        #expect(parsed.url.absoluteString == expected)
        #expect(parsed.platform == platform)
        #expect(parsed.requiresResolution == (platform == "music"))
    }

    @Test func extractsFirstSupportedLinkFromShareText() throws {
        let parsed = try #require(LinkParser.firstSupportedLink(in: "Watch this! https://example.com/test (https://x.com/user/status/123?s=48). Also https://youtu.be/other"))
        #expect(parsed.url.absoluteString == "https://x.com/user/status/123")
    }

    @Test(arguments: [
        "https://example.com/?url=https://x.com/user/status/123",
        "https://x.com.evil.example/user/status/123",
        "https://user:secret@x.com/user/status/123",
        "https://artlist.io/royalty-free-music/artist/djnoone/2901",
        "https://wololo.edilson.dev/assets/app.js",
        "https://wololo.edilson.dev/",
        "file:///tmp/video.mp4",
        "javascript:alert(1)"
    ])
    func rejectsUnsupportedLinks(_ input: String) {
        #expect(LinkParser.firstSupportedLink(in: input) == nil)
    }
}
