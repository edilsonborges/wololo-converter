import Foundation
import os
import WololoKit

@MainActor
final class BackgroundTransfers: NSObject, @preconcurrency URLSessionDownloadDelegate {
    private let store: SharedStore
    private let isExtension: Bool
    private let logger = Logger(subsystem: "dev.edilson.wololo", category: "Transfers")
    let identifier: String
    var onChange: (() -> Void)?
    var completionHandler: (() -> Void)? {
        didSet { finishBackgroundEventsIfReady() }
    }
    private var pendingSaves = 0
    private var deliveredEvents = false
    private lazy var session: URLSession = {
        let config = URLSessionConfiguration.background(withIdentifier: identifier)
        config.sharedContainerIdentifier = AppConstants.appGroup
        config.sessionSendsLaunchEvents = true
        config.isDiscretionary = false
        config.waitsForConnectivity = true
        config.timeoutIntervalForResource = 3600
        return URLSession(configuration: config, delegate: self, delegateQueue: .main)
    }()

    init(store: SharedStore, identifier: String, isExtension: Bool) {
        self.store = store
        self.identifier = identifier
        self.isExtension = isExtension
        super.init()
    }

    func connect() { _ = session }

    func start(request: URLRequest, localID: UUID) {
        // Background sessions follow redirects without a delegate callback.
        // File delivery is public by job ID; keep the access key on API calls only.
        var fileRequest = request
        fileRequest.setValue(nil, forHTTPHeaderField: "X-Wololo-Key")
        let task = session.downloadTask(with: fileRequest)
        task.taskDescription = localID.uuidString
        task.resume()
    }

    func taskIDs() async -> Set<UUID> {
        Set(await session.allTasks.compactMap { $0.taskDescription.flatMap(UUID.init(uuidString:)) })
    }

    func cancel(id: UUID) async {
        let tasks = await session.allTasks
        for task in tasks where task.taskDescription == id.uuidString {
            task.cancel()
        }
    }

    func urlSession(
        _ session: URLSession, downloadTask: URLSessionDownloadTask,
        didWriteData bytesWritten: Int64, totalBytesWritten: Int64, totalBytesExpectedToWrite: Int64
    ) {
        guard let id = localID(downloadTask), totalBytesExpectedToWrite > 0 else { return }
        do {
            try store.update(id: id) {
                guard $0.status == .transferring else { return }
                $0.progress = 90 + 10 * Double(totalBytesWritten) / Double(totalBytesExpectedToWrite)
            }
            onChange?()
        } catch { logger.error("Could not store transfer progress: \(error.localizedDescription)") }
    }

    func urlSession(
        _ session: URLSession, downloadTask: URLSessionDownloadTask, didFinishDownloadingTo location: URL
    ) {
        guard let id = localID(downloadTask) else { return }
        do {
            guard let response = downloadTask.response as? HTTPURLResponse,
                  (200...299).contains(response.statusCode) else {
                throw TransferError.unavailable
            }
            guard let entry = try store.jobs().first(where: { $0.id == id }),
                  entry.status != .cancelled else { return }
            let fallback = "Wololo.\(entry.format.rawValue)"
            let filename = entry.filename ?? downloadTask.response?.suggestedFilename ?? fallback
            let destination = try store.stagedFileURL(id: id, filename: filename)
            if FileManager.default.fileExists(atPath: destination.path) {
                try FileManager.default.removeItem(at: destination)
            }
            // The URLSession temporary file exists only until this delegate returns.
            try FileManager.default.moveItem(at: location, to: destination)
            var accepted = false
            try store.update(id: id) {
                guard $0.status == .transferring else { return }
                accepted = true
                $0.localPath = destination.path
                $0.status = .readyToSave
                $0.progress = 100
                $0.filename = destination.lastPathComponent
            }
            guard accepted else {
                try? FileManager.default.removeItem(at: destination)
                return
            }
            pendingSaves += 1
            onChange?()
            Task {
                defer {
                    pendingSaves -= 1
                    onChange?()
                    finishBackgroundEventsIfReady()
                }
                do {
                    if let staged = try store.jobs().first(where: { $0.id == id }) {
                        try await MediaSaver.save(staged, store: store, isExtension: isExtension)
                    }
                } catch {
                    try? store.update(id: id) { $0.errorMessage = error.localizedDescription }
                    await MediaSaver.notify(title: L("Ready to save"), body: error.localizedDescription, id: id)
                }
            }
        } catch { fail(id: id, error: error) }
    }

    func urlSession(_ session: URLSession, task: URLSessionTask, didCompleteWithError error: Error?) {
        guard let error, let id = localID(task) else { return }
        if (error as NSError).code == NSURLErrorCancelled { return }
        fail(id: id, error: error)
    }

    func urlSessionDidFinishEvents(forBackgroundURLSession session: URLSession) {
        deliveredEvents = true
        finishBackgroundEventsIfReady()
    }

    private func finishBackgroundEventsIfReady() {
        guard deliveredEvents, pendingSaves == 0, let completionHandler else { return }
        self.completionHandler = nil
        deliveredEvents = false
        completionHandler()
    }

    private func localID(_ task: URLSessionTask) -> UUID? {
        task.taskDescription.flatMap(UUID.init(uuidString:))
    }

    private func fail(id: UUID, error: Error) {
        do {
            try store.update(id: id) {
                guard $0.status != .cancelled else { return }
                $0.status = .failed
                $0.errorMessage = error.localizedDescription
                $0.completedAt = Date()
            }
        } catch { logger.error("Could not store transfer failure: \(error.localizedDescription)") }
        onChange?()
        Task { await MediaSaver.notify(title: L("Download failed"), body: error.localizedDescription, id: id) }
    }

    enum TransferError: LocalizedError {
        case unavailable
        var errorDescription: String? { L("The server could not send this file. Please download it again.") }
    }
}
