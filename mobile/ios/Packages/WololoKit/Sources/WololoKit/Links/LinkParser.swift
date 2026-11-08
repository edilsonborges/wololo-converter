import Foundation

public struct ParsedLink: Equatable, Sendable {
    public let url: URL
    public let platform: String
    public var requiresResolution: Bool { platform == "music" }
}

public enum LinkParser {
    private static let patterns: [(String, [String])] = [
        ("youtube", [
            #"^https?://(?:(?:www|m|music)\.)?youtube\.com/watch\?(?:[^#]*&)?v=[\w-]+"#,
            #"^https?://(?:(?:www|m)\.)?youtube\.com/(?:shorts|live|embed)/[\w-]+"#,
            #"^https?://youtu\.be/[\w-]+"#
        ]),
        ("instagram", [
            #"^https?://(?:www\.)?instagram\.com/(?:p|reels?|tv)/[\w-]+"#,
            #"^https?://(?:www\.)?instagram\.com/share/(?:p|reel)/[\w-]+"#
        ]),
        ("tiktok", [
            #"^https?://(?:www\.)?tiktok\.com/@[\w.]+/video/\d+"#,
            #"^https?://(?:vm|vt)\.tiktok\.com/[\w]+"#,
            #"^https?://(?:www\.)?tiktok\.com/t/[\w]+"#
        ]),
        ("twitter", [#"^https?://(?:www\.)?(?:twitter|x)\.com/\w+/status/\d+"#]),
        ("threads", [
            #"^https?://(?:www\.)?threads\.(?:net|com)/@[\w.]+/post/[\w]+"#,
            #"^https?://(?:www\.)?threads\.(?:net|com)/share/[\w-]+(?:/|[?#]|$)"#
        ]),
        ("facebook", [
            #"^https?://(?:www\.)?facebook\.com/.+/videos/\d+"#,
            #"^https?://(?:www\.)?facebook\.com/watch/?\?v=\d+"#,
            #"^https?://fb\.watch/[\w-]+"#
        ]),
        ("music", [#"^https?://(?:www\.)?artlist\.io/royalty-free-music/(?:album|song)/[^/?#\s]+/\d+"#])
    ]

    public static func firstSupportedLink(in text: String) -> ParsedLink? {
        let range = NSRange(text.startIndex..<text.endIndex, in: text)
        let detector = try? NSDataDetector(types: NSTextCheckingResult.CheckingType.link.rawValue)
        var candidates = detector?.matches(in: text, range: range).compactMap { match -> (Int, String)? in
            guard let matchRange = Range(match.range, in: text) else { return nil }
            return (match.range.location, String(text[matchRange]))
        } ?? []
        // The detector can omit short share codes and links without a scheme.
        let tokens = try? NSRegularExpression(pattern: #"[^\s,<>]+"#)
        candidates += tokens?.matches(in: text, range: range).compactMap { match -> (Int, String)? in
            guard let matchRange = Range(match.range, in: text) else { return nil }
            return (match.range.location, String(text[matchRange]))
        } ?? []
        for (_, candidate) in candidates.sorted(by: { $0.0 < $1.0 }) {
            if let parsed = parse(candidate) { return parsed }
        }
        return nil
    }

    public static func parse(_ text: String) -> ParsedLink? {
        var candidate = text.trimmingCharacters(in: .whitespacesAndNewlines)
            .trimmingCharacters(in: CharacterSet(charactersIn: "()[]<>\"'.,!"))
        if !candidate.contains("://") { candidate = "https://" + candidate }
        guard var components = URLComponents(string: candidate) else { return nil }
        if components.host?.lowercased() == "wololo.edilson.dev" {
            guard let decoded = components.percentEncodedPath.dropFirst().removingPercentEncoding,
                  !decoded.isEmpty else { return nil }
            candidate = decoded.replacingOccurrences(of: #"^(https?):/(?!/)"#, with: "$1://", options: .regularExpression)
            if !candidate.contains("://") { candidate = "https://" + candidate }
            if let query = components.percentEncodedQuery { candidate += "?" + query }
            guard let source = URLComponents(string: candidate) else { return nil }
            components = source
        }
        guard let scheme = components.scheme?.lowercased(), ["https", "http"].contains(scheme),
              let host = components.host, !host.isEmpty,
              components.user == nil, components.password == nil,
              components.port == nil else { return nil }
        guard let platform = patterns.first(where: { entry in
            entry.1.contains { pattern in
                candidate.range(of: pattern, options: [.regularExpression, .caseInsensitive]) != nil
            }
        })?.0 else { return nil }

        if platform == "youtube", components.path == "/watch",
           let videoID = components.queryItems?.first(where: { $0.name == "v" })?.value,
           let canonical = URL(string: "https://youtu.be/" + videoID) {
            return ParsedLink(url: canonical, platform: platform)
        }
        if platform == "youtube", host.lowercased() == "youtu.be",
           let videoID = components.path.split(separator: "/").first,
           let canonical = URL(string: "https://youtu.be/" + videoID) {
            return ParsedLink(url: canonical, platform: platform)
        }
        components.scheme = "https"
        components.fragment = nil
        components.query = nil
        guard let url = components.url else { return nil }
        return ParsedLink(url: url, platform: platform)
    }
}
