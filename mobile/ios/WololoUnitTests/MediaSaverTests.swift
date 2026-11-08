import XCTest
import Photos
import WololoKit
@testable import Wololo

final class MediaSaverTests: XCTestCase {
    @MainActor
    func testSavesStagedVideoToPhotos() async throws {
        // Pregrant photos-add to the app in the simulator before running this suite.
        guard PHPhotoLibrary.authorizationStatus(for: .addOnly) == .authorized else {
            XCTFail("Grant photos-add to dev.edilson.wololo before running this test.")
            return
        }
        let directory = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString)
        defer { try? FileManager.default.removeItem(at: directory) }
        let store = try SharedStore(directory: directory)
        var entry = LocalDownload(
            sourceURL: "https://www.youtube.com/watch?v=fixture",
            serverURL: AppConstants.defaultServer, format: .mp4, quality: .p720
        )
        let fixture = try XCTUnwrap(Bundle(for: Self.self).url(forResource: "video", withExtension: "mp4"))
        let staged = try store.stagedFileURL(id: entry.id, filename: "video.mp4")
        try FileManager.default.copyItem(at: fixture, to: staged)
        entry.localPath = staged.path
        entry.status = .readyToSave
        try store.upsert(entry)

        try await MediaSaver.save(entry, store: store, isExtension: false)

        let saved = try XCTUnwrap(store.jobs().first)
        XCTAssertEqual(saved.status, .saved)
        XCTAssertEqual(saved.progress, 100)
        XCTAssertNotNil(saved.completedAt)
        XCTAssertNil(saved.localPath)
        XCTAssertFalse(FileManager.default.fileExists(atPath: staged.path))
    }
}
