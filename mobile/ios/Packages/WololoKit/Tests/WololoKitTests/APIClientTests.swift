import Foundation
import Testing
@testable import WololoKit

private struct StubReply: Sendable {
    let status: Int
    let json: String
}

private final class StubState: @unchecked Sendable {
    private let lock = NSLock()
    private var replies: [StubReply] = []
    private var requests: [URLRequest] = []

    func configure(_ replies: [StubReply]) {
        lock.withLock { self.replies = replies; requests = [] }
    }

    func respond(to request: URLRequest) -> StubReply {
        lock.withLock {
            requests.append(request)
            return replies.isEmpty ? StubReply(status: 500, json: "{}") : replies.removeFirst()
        }
    }

    var receivedRequests: [URLRequest] { lock.withLock { requests } }
}

private final class StubURLProtocol: URLProtocol, @unchecked Sendable {
    static let state = StubState()

    override class func canInit(with request: URLRequest) -> Bool { true }
    override class func canonicalRequest(for request: URLRequest) -> URLRequest { request }
    override func startLoading() {
        let reply = Self.state.respond(to: request)
        guard let url = request.url,
              let response = HTTPURLResponse(url: url, statusCode: reply.status, httpVersion: "HTTP/1.1", headerFields: ["Content-Type": "application/json"]) else { return }
        client?.urlProtocol(self, didReceive: response, cacheStoragePolicy: .notAllowed)
        client?.urlProtocol(self, didLoad: Data(reply.json.utf8))
        client?.urlProtocolDidFinishLoading(self)
    }
    override func stopLoading() {}
}

@Suite(.serialized)
struct APIClientTests {
    private func makeClient(_ replies: [StubReply]) throws -> (APIClient, URLSession) {
        StubURLProtocol.state.configure(replies)
        let configuration = URLSessionConfiguration.ephemeral
        configuration.protocolClasses = [StubURLProtocol.self]
        let session = URLSession(configuration: configuration)
        return (try APIClient(serverURL: "https://wololo.test/", accessKey: "private-test-key", session: session), session)
    }

    @Test func sendsAccessKeyAndDecodesLegacyHealth() async throws {
        let (client, session) = try makeClient([.init(status: 200, json: #"{"status":"healthy","version":"0.8.1","active_downloads":2}"#)])
        defer { session.invalidateAndCancel() }
        let health = try await client.health()
        #expect(health.minAppVersion == nil)
        #expect(!health.requiresUpdate())
        let request = try #require(StubURLProtocol.state.receivedRequests.first)
        #expect(request.url?.absoluteString == "https://wololo.test/api/health")
        #expect(request.value(forHTTPHeaderField: "X-Wololo-Key") == "private-test-key")
    }

    @Test func checksMinimumAppVersionNumerically() async throws {
        let (client, session) = try makeClient([.init(status: 200, json: #"{"status":"healthy","version":"0.9.0","active_downloads":0,"min_app_version":"1.10.0"}"#)])
        defer { session.invalidateAndCancel() }
        let health = try await client.health()
        #expect(health.requiresUpdate(currentVersion: "1.2.0"))
        #expect(!health.requiresUpdate(currentVersion: "1.10.0"))
    }

    @Test func startsDownloadAndCreatesAuthenticatedFileRequest() async throws {
        let (client, session) = try makeClient([.init(status: 200, json: #"{"job_id":"job-123","status":"queued","message":"Download started"}"#)])
        defer { session.invalidateAndCancel() }
        let started = try await client.startDownload(url: #require(URL(string: "https://youtu.be/test123")), quality: .mp3)
        #expect(started.jobID == "job-123")
        #expect(started.status == .queued)
        let post = try #require(StubURLProtocol.state.receivedRequests.first)
        #expect(post.httpMethod == "POST")
        #expect(post.url?.path == "/api/download")
        let download = try client.downloadRequest(jobID: started.jobID)
        #expect(download.url?.absoluteString == "https://wololo.test/api/jobs/job-123/download")
        #expect(download.value(forHTTPHeaderField: "X-Wololo-Key") == "private-test-key")
    }

    @Test func preservesServerErrorDetails() async throws {
        let (client, session) = try makeClient([.init(status: 429, json: #"{"detail":"Download queue is full. Please try again later."}"#)])
        defer { session.invalidateAndCancel() }
        do {
            _ = try await client.health()
            Issue.record("Expected an HTTP error")
        } catch APIError.http(let status, let message) {
            #expect(status == 429)
            #expect(message.contains("queue is full"))
        }
    }

    @Test func pollsUntilCompletionAndDecodesNaiveUTCDates() async throws {
        let (client, session) = try makeClient([
            .init(status: 200, json: jobJSON(status: "queued")),
            .init(status: 200, json: jobJSON(status: "completed"))
        ])
        defer { session.invalidateAndCancel() }
        let job = try await client.waitForCompletion(jobID: "job-123", timeoutSeconds: 1, pollingIntervalSeconds: 0.01)
        #expect(job.status == .completed)
        #expect(job.createdAt.timeIntervalSince1970 > 1_700_000_000)
        #expect(StubURLProtocol.state.receivedRequests.count == 2)
    }

    @Test func stopsPollingForFailedJob() async throws {
        let (client, session) = try makeClient([.init(status: 200, json: jobJSON(status: "failed"))])
        defer { session.invalidateAndCancel() }
        await #expect(throws: APIError.self) {
            try await client.waitForCompletion(jobID: "job-123", timeoutSeconds: 1)
        }
        #expect(StubURLProtocol.state.receivedRequests.count == 1)
    }

    @Test(arguments: ["http://wololo.test", "https://user:key@wololo.test", "https://wololo.test?secret=test", "not-a-url"])
    func rejectsUnsafeServerAddress(_ address: String) {
        #expect(throws: APIError.self) { try APIClient(serverURL: address) }
    }

    @Test func preservesServerPathAndRejectsJobTraversal() throws {
        let client = try APIClient(serverURL: "https://wololo.test/prefix/api")
        #expect(try client.downloadRequest(jobID: "job-123").url?.path == "/prefix/api/jobs/job-123/download")
        #expect(throws: APIError.self) { try client.downloadRequest(jobID: "../health") }
        #expect(throws: APIError.self) { try client.downloadRequest(jobID: "job?key=leak") }
    }

    private func jobJSON(status: String) -> String {
        """
        {"id":"job-123","url":"https://youtu.be/test123","platform":"youtube","output_format":"video","quality":"720p","status":"\(status)","progress":0,"created_at":"2026-11-08T15:00:00.123456","error_message":"Video unavailable"}
        """
    }
}
