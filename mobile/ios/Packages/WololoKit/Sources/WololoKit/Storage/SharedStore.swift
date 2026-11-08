import Darwin
import Foundation

public enum StorageError: LocalizedError {
    case unavailableGroup, missingJob, invalidFilename
    case lockFailed(Int32)

    public var errorDescription: String? {
        switch self {
        case .unavailableGroup: String(localized: "Shared storage is unavailable. Open Wololo and check the app installation.", bundle: .module)
        case .missingJob: String(localized: "This download is no longer in the queue.", bundle: .module)
        case .invalidFilename: String(localized: "The download filename is invalid.", bundle: .module)
        case .lockFailed: String(localized: "The download queue could not be opened. Please try again.", bundle: .module)
        }
    }
}

/// Every read-modify-write holds the same file lock in the app and extension.
/// The lock belongs to a separate file so atomic JSON replacement preserves it.
public struct SharedStore: Sendable {
    public let directory: URL

    public init(appGroup: String = AppConstants.appGroup) throws {
        guard let container = FileManager.default.containerURL(forSecurityApplicationGroupIdentifier: appGroup) else {
            throw StorageError.unavailableGroup
        }
        try self.init(directory: container.appendingPathComponent("Wololo", isDirectory: true))
    }

    public init(directory: URL) throws {
        self.directory = directory
        try FileManager.default.createDirectory(at: directory, withIntermediateDirectories: true)
    }

    public func loadSettings() throws -> AppSettings {
        try locked { try read("settings.json", default: AppSettings.defaults) }
    }

    public func saveSettings(_ settings: AppSettings) throws {
        try locked { try write(settings, to: "settings.json") }
    }

    public func jobs() throws -> [LocalDownload] {
        try locked { try readJobs().sorted { $0.createdAt > $1.createdAt } }
    }

    public func upsert(_ job: LocalDownload) throws {
        try locked {
            var jobs = try readJobs()
            jobs.removeAll { $0.id == job.id }
            jobs.append(job)
            try writeJobs(jobs)
        }
    }

    public func update(id: UUID, mutation: (inout LocalDownload) -> Void) throws {
        try locked {
            var jobs = try readJobs()
            guard let index = jobs.firstIndex(where: { $0.id == id }) else { throw StorageError.missingJob }
            mutation(&jobs[index])
            try writeJobs(jobs)
        }
    }

    public func remove(id: UUID) throws {
        try locked {
            var jobs = try readJobs()
            jobs.removeAll { $0.id == id }
            try writeJobs(jobs)
        }
    }

    public func stagedFileURL(id: UUID, filename: String) throws -> URL {
        let safeName = Self.safeFilename(filename)
        guard !safeName.isEmpty else { throw StorageError.invalidFilename }
        let folder = directory.appendingPathComponent("Transfers", isDirectory: true)
            .appendingPathComponent(id.uuidString, isDirectory: true)
        try FileManager.default.createDirectory(at: folder, withIntermediateDirectories: true)
        return folder.appendingPathComponent(safeName)
    }

    public static func safeFilename(_ filename: String) -> String {
        let forbidden = CharacterSet(charactersIn: "/\\\0:\n\r")
        let cleaned = filename.components(separatedBy: forbidden).joined(separator: "_")
            .trimmingCharacters(in: CharacterSet(charactersIn: ". "))
        let extensionPart = (cleaned as NSString).pathExtension
        let suffix = extensionPart.isEmpty ? "" : "." + extensionPart
        var stem = extensionPart.isEmpty ? cleaned : (cleaned as NSString).deletingPathExtension
        while (stem + suffix).utf8.count > 220, !stem.isEmpty { stem.removeLast() }
        return stem + suffix
    }

    private func readJobs() throws -> [LocalDownload] {
        try read("jobs.json", default: [])
    }

    private func writeJobs(_ jobs: [LocalDownload]) throws {
        let active = jobs.filter { !$0.status.isTerminal }
        let history = jobs.filter { $0.status.isTerminal }.sorted { $0.createdAt > $1.createdAt }.prefix(50)
        try write(active + history, to: "jobs.json")
    }

    private func read<Value: Decodable>(_ filename: String, default fallback: Value) throws -> Value {
        let url = directory.appendingPathComponent(filename)
        guard FileManager.default.fileExists(atPath: url.path) else { return fallback }
        return try JSONDecoder().decode(Value.self, from: Data(contentsOf: url))
    }

    private func write<Value: Encodable>(_ value: Value, to filename: String) throws {
        let url = directory.appendingPathComponent(filename)
        try JSONEncoder().encode(value).write(to: url, options: .atomic)
        #if os(iOS)
        try FileManager.default.setAttributes([.protectionKey: FileProtectionType.completeUntilFirstUserAuthentication], ofItemAtPath: url.path)
        #endif
    }

    private func locked<Value>(_ operation: () throws -> Value) throws -> Value {
        let descriptor = open(directory.appendingPathComponent("store.lock").path, O_CREAT | O_RDWR, S_IRUSR | S_IWUSR)
        guard descriptor >= 0 else { throw StorageError.lockFailed(errno) }
        defer { close(descriptor) }
        guard flock(descriptor, LOCK_EX) == 0 else { throw StorageError.lockFailed(errno) }
        defer { flock(descriptor, LOCK_UN) }
        return try operation()
    }
}
