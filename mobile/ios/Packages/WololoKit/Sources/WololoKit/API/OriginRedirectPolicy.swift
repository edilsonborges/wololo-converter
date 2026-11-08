import Foundation

/// Custom access headers are only forwarded within the original HTTPS origin.
final class OriginRedirectPolicy: NSObject, URLSessionTaskDelegate, Sendable {
    static func permits(original: URL?, redirected: URL?) -> Bool {
        guard let original, let redirected,
              original.scheme?.lowercased() == "https",
              redirected.scheme?.lowercased() == "https",
              original.host?.lowercased() == redirected.host?.lowercased(),
              (original.port ?? 443) == (redirected.port ?? 443),
              redirected.user == nil, redirected.password == nil else { return false }
        return true
    }

    func urlSession(
        _ session: URLSession,
        task: URLSessionTask,
        willPerformHTTPRedirection response: HTTPURLResponse,
        newRequest request: URLRequest,
        completionHandler: @escaping @Sendable (URLRequest?) -> Void
    ) {
        completionHandler(Self.permits(original: task.originalRequest?.url, redirected: request.url) ? request : nil)
    }
}
