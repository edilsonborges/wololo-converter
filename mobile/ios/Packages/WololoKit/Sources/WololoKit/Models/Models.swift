import Foundation

public enum AppConstants {
    public static let appGroup = "group.dev.edilson.wololo"
    public static let appVersion = "1.0.0"
    public static let defaultServer = "https://wololo.edilson.dev"
}

public enum DownloadFormat: String, Codable, CaseIterable, Sendable, Identifiable {
    case mp4, mp3
    public var id: String { rawValue }
    public var title: String { rawValue.uppercased() }
}

public enum VideoQuality: String, Codable, CaseIterable, Sendable, Identifiable {
    case p360 = "360p"
    case p480 = "480p"
    case p720 = "720p"
    case p1080 = "1080p"
    case mp3

    public var id: String { rawValue }
    public static let videoOptions: [VideoQuality] = [.p360, .p480, .p720, .p1080]
}

public struct AppSettings: Codable, Equatable, Sendable {
    public var serverURL = AppConstants.defaultServer
    public var videoQuality: VideoQuality = .p720
    public var format: DownloadFormat = .mp4
    public static let defaults = AppSettings()
    public init() {}
}

public enum JobStatus: String, Codable, Sendable {
    case queued, validating, downloading, converting, finalizing, completed, failed, cancelled
    public var isTerminal: Bool { self == .completed || self == .failed || self == .cancelled }
}

public struct ServerHealth: Decodable, Sendable {
    public let status: String
    public let version: String
    public let minAppVersion: String?
    public let activeDownloads: Int

    enum CodingKeys: String, CodingKey {
        case status, version
        case minAppVersion = "min_app_version"
        case activeDownloads = "active_downloads"
    }

    public func requiresUpdate(currentVersion: String = AppConstants.appVersion) -> Bool {
        guard let minimum = minAppVersion else { return false }
        return currentVersion.compare(minimum, options: .numeric) == .orderedAscending
    }
}

public struct DownloadStarted: Decodable, Sendable {
    public let jobID: String
    public let status: JobStatus
    public let message: String

    enum CodingKeys: String, CodingKey {
        case jobID = "job_id"
        case status, message
    }
}

public struct ServerJob: Decodable, Sendable, Identifiable {
    public let id: String
    public let url: String
    public let platform: String
    public let outputFormat: String
    public let quality: VideoQuality?
    public let status: JobStatus
    public let progress: Double
    public let speed: String?
    public let eta: String?
    public let currentStage: String?
    public let title: String?
    public let filename: String?
    public let fileSize: Int64?
    public let duration: Double?
    public let thumbnailURL: String?
    public let errorMessage: String?
    public let createdAt: Date
    public let startedAt: Date?
    public let completedAt: Date?

    enum CodingKeys: String, CodingKey {
        case id, url, platform, quality, status, progress, speed, eta, title, filename, duration
        case outputFormat = "output_format"
        case currentStage = "current_stage"
        case fileSize = "file_size"
        case thumbnailURL = "thumbnail_url"
        case errorMessage = "error_message"
        case createdAt = "created_at"
        case startedAt = "started_at"
        case completedAt = "completed_at"
    }
}

public struct ResolvedTrack: Decodable, Sendable {
    public let title: String
    public let artist: String
    public let duration: Double?
    public let sourceURL: String?
    public let videoURL: String?
    public let videoTitle: String?

    enum CodingKeys: String, CodingKey {
        case title, artist, duration
        case sourceURL = "source_url"
        case videoURL = "video_url"
        case videoTitle = "video_title"
    }
}

public struct ResolvedPage: Decodable, Sendable {
    public let album: String
    public let tracks: [ResolvedTrack]
}

public enum LocalDownloadStatus: String, Codable, Sendable {
    case queued, processing, transferring, readyToSave, saved, failed, cancelled
    public var isTerminal: Bool { self == .saved || self == .failed || self == .cancelled }
}

public struct LocalDownload: Identifiable, Codable, Equatable, Sendable {
    public var id = UUID()
    public var jobID: String?
    public var sourceURL: String
    public var serverURL: String
    public var format: DownloadFormat
    public var quality: VideoQuality
    public var title: String?
    public var status: LocalDownloadStatus = .queued
    public var progress: Double = 0
    public var filename: String?
    public var localPath: String?
    public var transferSessionID: String?
    public var transferStartedAt: Date?
    public var transferOwnerPID: Int32?
    public var saveOwnerPID: Int32?
    public var errorMessage: String?
    public var createdAt = Date()
    public var completedAt: Date?

    public init(sourceURL: String, serverURL: String, format: DownloadFormat, quality: VideoQuality) {
        self.sourceURL = sourceURL
        self.serverURL = serverURL
        self.format = format
        self.quality = format == .mp3 ? .mp3 : quality
    }
}
