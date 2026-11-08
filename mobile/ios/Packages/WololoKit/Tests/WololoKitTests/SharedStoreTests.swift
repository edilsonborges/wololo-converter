import Foundation
import Testing
@testable import WololoKit

struct SharedStoreTests {
    @Test func retainsActiveQueueAndOnlyFiftyHistoryEntries() throws {
        let directory = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString)
        defer { try? FileManager.default.removeItem(at: directory) }
        let store = try SharedStore(directory: directory)
        let active = LocalDownload(sourceURL: "https://youtu.be/active", serverURL: AppConstants.defaultServer, format: .mp4, quality: .p720)
        try store.upsert(active)
        for index in 0..<60 {
            var item = LocalDownload(sourceURL: "https://youtu.be/\(index)", serverURL: AppConstants.defaultServer, format: .mp4, quality: .p720)
            item.status = .saved
            item.createdAt = Date(timeIntervalSince1970: Double(index))
            try store.upsert(item)
        }
        let stored = try store.jobs()
        #expect(stored.count == 51)
        #expect(stored.contains { $0.id == active.id })
        #expect(stored.filter { $0.status == .saved }.count == 50)
    }

    @Test func concurrentClientsPreserveIndependentQueueUpdates() async throws {
        let directory = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString)
        defer { try? FileManager.default.removeItem(at: directory) }
        let store = try SharedStore(directory: directory)
        try await withThrowingTaskGroup(of: Void.self) { group in
            for index in 0..<30 {
                group.addTask {
                    let secondProcessStore = try SharedStore(directory: directory)
                    let item = LocalDownload(sourceURL: "https://youtu.be/\(index)", serverURL: AppConstants.defaultServer, format: .mp4, quality: .p720)
                    try secondProcessStore.upsert(item)
                    try secondProcessStore.update(id: item.id) { $0.status = .processing }
                }
            }
            try await group.waitForAll()
        }
        let jobs = try store.jobs()
        #expect(jobs.count == 30)
        #expect(jobs.allSatisfy { $0.status == .processing })
    }

    @Test func storageDefaultsSettingsAndStagingAreSafe() throws {
        let directory = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString)
        defer { try? FileManager.default.removeItem(at: directory) }
        let store = try SharedStore(directory: directory)
        #expect(try store.loadSettings() == .defaults)
        var settings = AppSettings()
        settings.format = .mp3
        settings.videoQuality = .p1080
        try store.saveSettings(settings)
        #expect(try store.loadSettings() == settings)
        let id = UUID()
        let staged = try store.stagedFileURL(id: id, filename: "../../private.mp3")
        #expect(staged.deletingLastPathComponent().lastPathComponent == id.uuidString)
        #expect(staged.path.hasPrefix(directory.path))
        #expect(!staged.lastPathComponent.contains("/"))
    }

    @Test func transferClaimIsAtomicAcrossStores() async throws {
        let directory = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString)
        defer { try? FileManager.default.removeItem(at: directory) }
        let store = try SharedStore(directory: directory)
        let item = LocalDownload(sourceURL: "https://youtu.be/test", serverURL: AppConstants.defaultServer, format: .mp4, quality: .p720)
        try store.upsert(item)
        let winners = try await withThrowingTaskGroup(of: Bool.self) { group in
            for index in 0..<20 {
                group.addTask {
                    var claimed = false
                    try store.update(id: item.id) { current in
                        if current.status == .queued {
                            current.status = .transferring
                            current.transferSessionID = "session-\(index)"
                            claimed = true
                        }
                    }
                    return claimed
                }
            }
            var winners = 0
            for try await claimed in group { if claimed { winners += 1 } }
            return winners
        }
        #expect(winners == 1)
        #expect(try store.jobs().first?.transferSessionID != nil)
    }
}
