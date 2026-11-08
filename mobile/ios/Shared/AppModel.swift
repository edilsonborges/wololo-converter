import Foundation
import Observation
import WololoKit

@MainActor
@Observable
final class AppModel {
    var settings = AppSettings.defaults
    var accessKey = ""
    var entries: [LocalDownload] = []
    var errorMessage: String?
    var connectionMessage: String?
    var isSubmitting = false
    let isExtension: Bool
    let sessionID: String
    private(set) var store: SharedStore?
    private let keychain = KeychainStore()
    private var polling: [UUID: Task<Void, Never>] = [:]
    private var transfers: [String: BackgroundTransfers] = [:]
    private var saving: Set<UUID> = []
    private var reconcilingTransfers = false

    init(isExtension: Bool = false) {
        self.isExtension = isExtension
        sessionID = isExtension
            ? "dev.edilson.wololo.download.share.\(UUID().uuidString)"
            : "dev.edilson.wololo.download.app"
        do {
            let sharedStore = try SharedStore()
            store = sharedStore
            settings = try sharedStore.loadSettings()
            accessKey = try keychain.readKey(serverURL: settings.serverURL)
            entries = try sharedStore.jobs()
            transferSession(identifier: sessionID)?.connect()
        } catch { errorMessage = error.localizedDescription }
    }

    func saveSettings() throws {
        _ = try APIClient(serverURL: settings.serverURL, accessKey: accessKey)
        try keychain.saveKey(accessKey, serverURL: settings.serverURL)
        try store?.saveSettings(settings)
    }

    func serverAddressChanged() {
        accessKey = ""
        connectionMessage = nil
        if let stored = try? keychain.readKey(serverURL: settings.serverURL) { accessKey = stored }
    }

    func checkConnection() async {
        do {
            try saveSettings()
            let client = try APIClient(serverURL: settings.serverURL, accessKey: accessKey)
            let health = try await client.health()
            guard !health.requiresUpdate() else { throw ModelError.updateRequired }
            connectionMessage = L("Connected to Wololo") + " " + health.version
        } catch { connectionMessage = error.localizedDescription }
    }

    @discardableResult
    func submit(text: String, format: DownloadFormat? = nil) async -> UUID? {
        guard !isSubmitting else { return nil }
        guard let link = LinkParser.firstSupportedLink(in: text) else {
            errorMessage = L("Share or paste a supported video link.")
            return nil
        }
        isSubmitting = true
        errorMessage = nil
        defer { isSubmitting = false }
        do {
            guard let store else { throw ModelError.storageUnavailable }
            settings.format = format ?? settings.format
            try saveSettings()
            let client = try APIClient(serverURL: settings.serverURL, accessKey: accessKey)
            let health = try await client.health()
            guard !health.requiresUpdate() else { throw ModelError.updateRequired }
            let selectedFormat = link.requiresResolution ? DownloadFormat.mp3 : settings.format
            if selectedFormat == .mp4 { try await MediaSaver.requestPhotoPermission() }
            if link.requiresResolution {
                let page = try await client.resolve(url: link.url)
                var firstID: UUID?
                var missing = 0
                for track in page.tracks {
                    guard let source = track.videoURL, let url = URL(string: source) else {
                        missing += 1
                        continue
                    }
                    let id = try await createDownload(url: url, format: .mp3, client: client, store: store)
                    if firstID == nil { firstID = id }
                }
                if missing > 0 { errorMessage = L("Some items could not be found. Available items were added.") }
                if firstID == nil { throw ModelError.noResults }
                return firstID
            }
            return try await createDownload(url: link.url, format: selectedFormat, client: client, store: store)
        } catch {
            errorMessage = error.localizedDescription
            return nil
        }
    }

    private func createDownload(url: URL, format: DownloadFormat, client: APIClient, store: SharedStore) async throws -> UUID {
        var entry = LocalDownload(sourceURL: url.absoluteString, serverURL: settings.serverURL,
                                  format: format, quality: settings.videoQuality)
        let started = try await client.startDownload(url: url, quality: entry.quality)
        entry.jobID = started.jobID
        do { try store.upsert(entry) }
        catch {
            try? await client.cancelJob(id: started.jobID)
            throw error
        }
        reload()
        resume(entry)
        return entry.id
    }

    func reload() {
        do { entries = try store?.jobs() ?? [] }
        catch { errorMessage = error.localizedDescription }
    }

    func refreshAndResume() {
        reload()
        reconcileTransfers()
        for entry in entries {
            if entry.status == .queued || entry.status == .processing { resume(entry) }
            if !isExtension, entry.status == .readyToSave, entry.errorMessage == nil {
                save(entry)
            }
        }
    }

    func reconcileTransfers() {
        guard !reconcilingTransfers, let store else { return }
        reconcilingTransfers = true
        Task {
            defer { reconcilingTransfers = false; reload() }
            do {
                let records = try store.jobs()
                let groups = Dictionary(grouping: records.filter {
                    $0.transferSessionID != nil && ($0.status == .transferring || $0.status == .cancelled)
                }, by: { $0.transferSessionID! })
                for (identifier, records) in groups {
                    guard records.allSatisfy(canOwnTransfer), let transfer = transferSession(identifier: identifier) else { continue }
                    for entry in records where entry.status == .transferring {
                        try store.update(id: entry.id) {
                            if canOwnTransfer($0) { $0.transferOwnerPID = ProcessInfo.processInfo.processIdentifier }
                        }
                    }
                    let taskIDs = await transfer.taskIDs()
                    for entry in records {
                        if entry.status == .cancelled {
                            if taskIDs.contains(entry.id) { await transfer.cancel(id: entry.id) }
                            continue
                        }
                        if taskIDs.contains(entry.id) { continue }
                        // Give a freshly submitted task time to register with the daemon.
                        if let started = entry.transferStartedAt, Date().timeIntervalSince(started) < 5 { continue }
                        let filename = entry.filename ?? "Wololo.\(entry.format.rawValue)"
                        let staged = try store.stagedFileURL(id: entry.id, filename: filename)
                        let hasFile = FileManager.default.fileExists(atPath: staged.path)
                        try store.update(id: entry.id) {
                            guard $0.status == .transferring else { return }
                            $0.transferSessionID = nil
                            $0.transferOwnerPID = nil
                            $0.transferStartedAt = nil
                            $0.status = hasFile ? .readyToSave : .queued
                            $0.localPath = hasFile ? staged.path : nil
                        }
                    }
                }
            } catch { errorMessage = error.localizedDescription }
        }
    }

    private func canOwnTransfer(_ entry: LocalDownload) -> Bool {
        if isExtension && entry.transferSessionID != sessionID { return false }
        guard let owner = entry.transferOwnerPID else { return true }
        return owner == ProcessInfo.processInfo.processIdentifier || !processIsRunning(owner)
    }

    func pausePolling() {
        for task in polling.values { task.cancel() }
    }

    private func resume(_ entry: LocalDownload) {
        guard polling[entry.id] == nil, entry.jobID != nil else { return }
        polling[entry.id] = Task {
            defer { polling.removeValue(forKey: entry.id) }
            await follow(entry)
        }
    }

    private func follow(_ entry: LocalDownload) async {
        do {
            guard let store, let jobID = entry.jobID else { return }
            let client = try APIClient(serverURL: entry.serverURL, accessKey: keychain.readKey(serverURL: entry.serverURL))
            let deadline = Date().addingTimeInterval(15 * 60)
            while Date() < deadline {
                try Task.checkCancellation()
                guard let current = try store.jobs().first(where: { $0.id == entry.id }),
                      current.status == .queued || current.status == .processing else { return }
                let job = try await client.job(id: jobID)
                try Task.checkCancellation()
                if job.status == .failed { throw ModelError.server(job.errorMessage ?? L("Download failed")) }
                if job.status == .cancelled {
                    try store.update(id: entry.id) { $0.status = .cancelled; $0.completedAt = Date() }
                    reload()
                    return
                }
                if job.status == .completed {
                    let request = try client.downloadRequest(jobID: jobID)
                    var claimed = false
                    try store.update(id: entry.id) {
                        guard $0.status == .queued || $0.status == .processing else { return }
                        $0.status = .transferring
                        $0.progress = 90
                        $0.title = job.title
                        $0.filename = job.filename
                        $0.transferSessionID = sessionID
                        $0.transferOwnerPID = ProcessInfo.processInfo.processIdentifier
                        $0.transferStartedAt = Date()
                        claimed = true
                    }
                    if claimed { transferSession(identifier: sessionID)?.start(request: request, localID: entry.id) }
                    reload()
                    return
                }
                try store.update(id: entry.id) {
                    guard $0.status == .queued || $0.status == .processing else { return }
                    $0.status = job.status == .queued ? .queued : .processing
                    $0.progress = job.progress * 0.9
                    $0.title = job.title
                }
                reload()
                try await Task.sleep(for: .seconds(1))
            }
            throw ModelError.pollingTimeout
        } catch is CancellationError {
            // The app resumes this persisted server job when it becomes active.
        } catch {
            do {
                try store?.update(id: entry.id) {
                    guard $0.status == .queued || $0.status == .processing else { return }
                    $0.status = .failed
                    $0.errorMessage = error.localizedDescription
                    $0.completedAt = Date()
                }
            } catch { errorMessage = error.localizedDescription }
            reload()
            await MediaSaver.notify(title: L("Download failed"), body: error.localizedDescription, id: entry.id)
        }
    }

    func cancel(_ entry: LocalDownload) async {
        polling.removeValue(forKey: entry.id)?.cancel()
        do {
            try store?.update(id: entry.id) { $0.status = .cancelled; $0.completedAt = Date() }
            if let identifier = entry.transferSessionID,
               canOwnTransfer(entry), let transfer = transferSession(identifier: identifier) {
                await transfer.cancel(id: entry.id)
            }
            reload()
            if let jobID = entry.jobID {
                let client = try APIClient(serverURL: entry.serverURL, accessKey: keychain.readKey(serverURL: entry.serverURL))
                try await client.cancelJob(id: jobID)
            }
        } catch { errorMessage = error.localizedDescription }
    }

    func retry(_ entry: LocalDownload) async {
        _ = await submit(text: entry.sourceURL, format: entry.format)
    }

    func save(_ entry: LocalDownload) {
        guard let store, saving.insert(entry.id).inserted else { return }
        Task {
            defer { saving.remove(entry.id); reload() }
            do { try await MediaSaver.save(entry, store: store, isExtension: isExtension) }
            catch {
                errorMessage = error.localizedDescription
                try? store.update(id: entry.id) { $0.errorMessage = error.localizedDescription }
            }
        }
    }

    func markExported(_ entry: LocalDownload) {
        do {
            try store?.update(id: entry.id) {
                $0.status = .saved
                $0.completedAt = Date()
                $0.errorMessage = nil
            }
            reload()
            Task {
                await MediaSaver.notify(title: L("Download saved"), body: entry.title ?? L("Your download is ready."), id: entry.id)
            }
        } catch { errorMessage = error.localizedDescription }
    }

    func handleBackgroundEvents(identifier: String, completion: @escaping () -> Void) {
        // iOS hands ownership of this session to the containing app.
        if let store, let entries = try? store.jobs() {
            for entry in entries where entry.transferSessionID == identifier && entry.status == .transferring {
                try? store.update(id: entry.id) { $0.transferOwnerPID = ProcessInfo.processInfo.processIdentifier }
            }
        }
        guard let transfer = transferSession(identifier: identifier) else { completion(); return }
        transfer.completionHandler = completion
        transfer.connect()
    }

    private func transferSession(identifier: String) -> BackgroundTransfers? {
        if let existing = transfers[identifier] { return existing }
        guard let store else { return nil }
        let transfer = BackgroundTransfers(store: store, identifier: identifier, isExtension: isExtension)
        transfer.onChange = { [weak self] in self?.reload() }
        transfers[identifier] = transfer
        return transfer
    }

    enum ModelError: LocalizedError {
        case storageUnavailable, updateRequired, noResults, pollingTimeout, server(String)
        var errorDescription: String? {
            switch self {
            case .storageUnavailable: L("Shared storage is unavailable. Reinstall Wololo and try again.")
            case .updateRequired: L("Update Wololo to continue using this server.")
            case .noResults: L("No downloadable items were found.")
            case .pollingTimeout: L("The server is taking too long. Please try again later.")
            case .server(let message): message
            }
        }
    }
}
