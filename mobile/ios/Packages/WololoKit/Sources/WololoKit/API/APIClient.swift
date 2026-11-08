import Foundation

public enum APIError: LocalizedError, Sendable {
    case invalidServerURL, invalidJobID, invalidResponse, pollingTimedOut, jobCancelled
    case http(statusCode: Int, message: String)
    case jobFailed(String)

    public var errorDescription: String? {
        switch self {
        case .invalidServerURL: String(localized: "Enter a valid HTTPS server address.", bundle: .module)
        case .invalidJobID: String(localized: "The server returned an invalid download identifier.", bundle: .module)
        case .invalidResponse: String(localized: "The server returned an unexpected response.", bundle: .module)
        case .pollingTimedOut: String(localized: "This download is taking longer than expected. Open Wololo to resume checking it.", bundle: .module)
        case .jobCancelled: String(localized: "The download was cancelled.", bundle: .module)
        case .http(_, let message), .jobFailed(let message): message
        }
    }
}

public struct APIClient: Sendable {
    public let baseURL: URL
    private let accessKey: String
    private let session: URLSession

    public init(serverURL: String, accessKey: String = "", session: URLSession? = nil) throws {
        guard var components = URLComponents(string: serverURL.trimmingCharacters(in: .whitespacesAndNewlines)),
              components.scheme?.lowercased() == "https",
              let host = components.host, !host.isEmpty,
              components.user == nil, components.password == nil,
              components.query == nil, components.fragment == nil else { throw APIError.invalidServerURL }
        components.path = components.path.trimmingCharacters(in: CharacterSet(charactersIn: "/"))
        if !components.path.isEmpty { components.path = "/" + components.path }
        guard let url = components.url else { throw APIError.invalidServerURL }
        self.baseURL = url.lastPathComponent == "api" ? url : url.appendingPathComponent("api")
        self.accessKey = accessKey.trimmingCharacters(in: .whitespacesAndNewlines)
        self.session = session ?? Self.defaultSession
    }

    public func health() async throws -> ServerHealth {
        try await perform(request(path: "health"))
    }

    public func startDownload(url: URL, quality: VideoQuality) async throws -> DownloadStarted {
        struct Payload: Encodable { let url: String; let quality: VideoQuality }
        return try await perform(request(path: "download", method: "POST", body: JSONEncoder().encode(Payload(url: url.absoluteString, quality: quality))))
    }

    public func job(id: String) async throws -> ServerJob {
        try validateJobID(id)
        return try await perform(request(path: "jobs/" + id))
    }

    public func cancelJob(id: String) async throws {
        try validateJobID(id)
        let request = request(path: "jobs/" + id, method: "DELETE")
        let (data, response) = try await session.data(for: request)
        try Self.check(response: response, data: data)
    }

    public func resolve(url: URL) async throws -> ResolvedPage {
        struct Payload: Encodable { let url: String }
        var request = request(path: "resolve", method: "POST", body: try JSONEncoder().encode(Payload(url: url.absoluteString)))
        request.timeoutInterval = 190
        return try await perform(request)
    }

    public func downloadRequest(jobID: String) throws -> URLRequest {
        try validateJobID(jobID)
        var request = request(path: "jobs/" + jobID + "/download")
        request.timeoutInterval = 60
        return request
    }

    /// URLSession writes the response to disk. The caller must move this file
    /// into its durable container before returning control to its own flow.
    public func download(jobID: String) async throws -> URL {
        let (file, response) = try await session.download(for: downloadRequest(jobID: jobID))
        do {
            try Self.check(response: response)
            return file
        } catch {
            try? FileManager.default.removeItem(at: file)
            throw error
        }
    }

    public func waitForCompletion(
        jobID: String,
        timeoutSeconds: Double = 900,
        pollingIntervalSeconds: Double = 1,
        onProgress: @Sendable (ServerJob) async -> Void = { _ in }
    ) async throws -> ServerJob {
        let clock = ContinuousClock()
        let deadline = clock.now.advanced(by: .seconds(min(max(timeoutSeconds, 0), 900)))
        while clock.now < deadline {
            try Task.checkCancellation()
            let current = try await job(id: jobID)
            await onProgress(current)
            switch current.status {
            case .completed: return current
            case .failed: throw APIError.jobFailed(current.errorMessage ?? "This video could not be downloaded.")
            case .cancelled: throw APIError.jobCancelled
            default: break
            }
            try await clock.sleep(until: min(clock.now.advanced(by: .seconds(max(pollingIntervalSeconds, 0.01))), deadline))
        }
        throw APIError.pollingTimedOut
    }

    public static func check(response: URLResponse, data: Data? = nil) throws {
        guard let response = response as? HTTPURLResponse else { throw APIError.invalidResponse }
        guard (200..<300).contains(response.statusCode) else {
            let details = data.flatMap { try? JSONDecoder().decode(ErrorDetail.self, from: $0) }
            let fallback: String
            switch response.statusCode {
            case 401, 403: fallback = String(localized: "Your access key was rejected. Check it in Settings.", bundle: .module)
            case 404: fallback = String(localized: "This download is no longer available. Please try again.", bundle: .module)
            case 429: fallback = String(localized: "The server is busy. Please wait a moment and try again.", bundle: .module)
            case 500...599: fallback = String(localized: "The server could not complete this request. Please try again later.", bundle: .module)
            default: fallback = String(localized: "The server rejected this request. Please check the link and try again.", bundle: .module)
            }
            throw APIError.http(statusCode: response.statusCode, message: details?.detail ?? fallback)
        }
    }

    public static func decoder() -> JSONDecoder {
        let decoder = JSONDecoder()
        decoder.dateDecodingStrategy = .custom { decoder in
            let container = try decoder.singleValueContainer()
            var value = try container.decode(String.self)
            if !value.hasSuffix("Z"), value.range(of: #"[+-]\d{2}:?\d{2}$"#, options: .regularExpression) == nil {
                value += "Z"
            }
            let formatter = ISO8601DateFormatter()
            formatter.formatOptions = [.withInternetDateTime, .withFractionalSeconds]
            if let date = formatter.date(from: value) { return date }
            formatter.formatOptions = [.withInternetDateTime]
            guard let date = formatter.date(from: value) else {
                throw DecodingError.dataCorruptedError(in: container, debugDescription: "Invalid server date")
            }
            return date
        }
        return decoder
    }

    private func request(path: String, method: String = "GET", body: Data? = nil) -> URLRequest {
        var request = URLRequest(url: baseURL.appendingPathComponent(path))
        request.httpMethod = method
        request.timeoutInterval = 30
        request.setValue("application/json", forHTTPHeaderField: "Accept")
        if !accessKey.isEmpty { request.setValue(accessKey, forHTTPHeaderField: "X-Wololo-Key") }
        if body != nil { request.setValue("application/json", forHTTPHeaderField: "Content-Type") }
        request.httpBody = body
        return request
    }

    private func perform<Value: Decodable>(_ request: URLRequest) async throws -> Value {
        let (data, response) = try await session.data(for: request)
        try Self.check(response: response, data: data)
        do {
            return try Self.decoder().decode(Value.self, from: data)
        } catch {
            throw APIError.invalidResponse
        }
    }

    private func validateJobID(_ id: String) throws {
        let characters = CharacterSet.alphanumerics.union(CharacterSet(charactersIn: "-"))
        guard !id.isEmpty, id.unicodeScalars.allSatisfy(characters.contains) else { throw APIError.invalidJobID }
    }

    private static let defaultSession: URLSession = {
        let configuration = URLSessionConfiguration.ephemeral
        configuration.httpShouldSetCookies = false
        return URLSession(configuration: configuration, delegate: OriginRedirectPolicy(), delegateQueue: nil)
    }()

    private struct ErrorDetail: Decodable { let detail: String? }
}
