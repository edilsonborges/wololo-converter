import Foundation
import Photos
import UserNotifications
import WololoKit

@MainActor
struct MediaSaver {
    private static var savingIDs: Set<UUID> = []
    static func requestPhotoPermission() async throws {
        let status = await PHPhotoLibrary.requestAuthorization(for: .addOnly)
        guard status == .authorized || status == .limited else {
            throw SaveError.photoPermission
        }
    }

    static func save(_ entry: LocalDownload, store: SharedStore, isExtension: Bool) async throws {
        if entry.format == .mp3 && isExtension { return }
        guard savingIDs.insert(entry.id).inserted else { return }
        defer { savingIDs.remove(entry.id) }
        let processID = ProcessInfo.processInfo.processIdentifier
        var claimed = false
        try store.update(id: entry.id) {
            guard $0.status == .readyToSave else { return }
            if let owner = $0.saveOwnerPID, owner != processID, processIsRunning(owner) { return }
            $0.saveOwnerPID = processID
            claimed = true
        }
        guard claimed else { return }
        defer {
            try? store.update(id: entry.id) {
                if $0.saveOwnerPID == processID { $0.saveOwnerPID = nil }
            }
        }
        guard let path = entry.localPath else { throw SaveError.missingFile }
        let file = URL(fileURLWithPath: path)
        guard FileManager.default.fileExists(atPath: file.path) else { throw SaveError.missingFile }
        var savedPath: String?
        if entry.format == .mp4 {
            try await requestPhotoPermission()
            try await PHPhotoLibrary.shared().performChanges {
                PHAssetChangeRequest.creationRequestForAssetFromVideo(atFileURL: file)
            }
            try? FileManager.default.removeItem(at: file)
        } else {
            let documents = try FileManager.default.url(
                for: .documentDirectory, in: .userDomainMask, appropriateFor: nil, create: true
            )
            let name = file.deletingPathExtension().lastPathComponent
            var destination = documents.appendingPathComponent(file.lastPathComponent)
            if FileManager.default.fileExists(atPath: destination.path) {
                destination = documents.appendingPathComponent("\(name)-\(entry.id.uuidString.prefix(8)).mp3")
            }
            try FileManager.default.moveItem(at: file, to: destination)
            savedPath = destination.path
        }
        try store.update(id: entry.id) {
            $0.status = .saved
            $0.localPath = savedPath
            $0.progress = 100
            $0.completedAt = Date()
            $0.errorMessage = nil
        }
        await notify(title: L("Download saved"), body: entry.title ?? L("Your download is ready."), id: entry.id)
    }

    static func notify(title: String, body: String, id: UUID) async {
        let content = UNMutableNotificationContent()
        content.title = title
        content.body = body
        content.sound = .default
        let request = UNNotificationRequest(identifier: id.uuidString, content: content, trigger: nil)
        try? await UNUserNotificationCenter.current().add(request)
    }

    enum SaveError: LocalizedError {
        case photoPermission, missingFile
        var errorDescription: String? {
            switch self {
            case .photoPermission: L("Allow Wololo to add videos in Settings, then tap Save again.")
            case .missingFile: L("This file is no longer available. Download it again.")
            }
        }
    }
}
