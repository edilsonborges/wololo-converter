import CryptoKit
import Foundation
import Security

public struct KeychainStore: Sendable {
    private let accessGroup: String

    public init(accessGroup: String = AppConstants.appGroup) {
        self.accessGroup = accessGroup
    }

    public func readKey(serverURL: String = AppConstants.defaultServer) throws -> String {
        var query = try baseQuery(serverURL: serverURL)
        query[kSecReturnData] = true
        query[kSecMatchLimit] = kSecMatchLimitOne
        var result: CFTypeRef?
        let status = SecItemCopyMatching(query as CFDictionary, &result)
        if status == errSecItemNotFound { return "" }
        guard status == errSecSuccess, let data = result as? Data,
              let key = String(data: data, encoding: .utf8) else { throw KeychainError(status: status) }
        return key
    }

    public func saveKey(_ key: String, serverURL: String = AppConstants.defaultServer) throws {
        let query = try baseQuery(serverURL: serverURL)
        let value = key.trimmingCharacters(in: .whitespacesAndNewlines)
        if value.isEmpty {
            let status = SecItemDelete(query as CFDictionary)
            guard status == errSecSuccess || status == errSecItemNotFound else { throw KeychainError(status: status) }
            return
        }
        let attributes: [CFString: Any] = [
            kSecValueData: Data(value.utf8),
            kSecAttrAccessible: kSecAttrAccessibleAfterFirstUnlockThisDeviceOnly
        ]
        var status = SecItemUpdate(query as CFDictionary, attributes as CFDictionary)
        if status == errSecItemNotFound {
            status = SecItemAdd(query.merging(attributes, uniquingKeysWith: { _, updated in updated }) as CFDictionary, nil)
        }
        guard status == errSecSuccess else { throw KeychainError(status: status) }
    }

    // Keys belong to a server endpoint, including its optional path prefix.
    // Pending jobs can read their original key after the selected server changes.
    func account(serverURL: String) throws -> String {
        let baseURL = try APIClient(serverURL: serverURL).baseURL
        guard var components = URLComponents(url: baseURL, resolvingAgainstBaseURL: false) else {
            throw APIError.invalidServerURL
        }
        components.scheme = "https"
        components.host = components.host?.lowercased()
        if components.port == 443 { components.port = nil }
        guard let identity = components.string else { throw APIError.invalidServerURL }
        let digest = SHA256.hash(data: Data(identity.utf8))
        return "access-key." + digest.map { String(format: "%02x", $0) }.joined()
    }

    private func baseQuery(serverURL: String) throws -> [CFString: Any] {
        [kSecClass: kSecClassGenericPassword,
         kSecAttrService: "dev.edilson.wololo.server",
         kSecAttrAccount: try account(serverURL: serverURL),
         kSecAttrAccessGroup: accessGroup]
    }
}

public struct KeychainError: LocalizedError {
    public let status: OSStatus
    public var errorDescription: String? {
        String(localized: "The access key could not be read or saved. Please check the app signing and try again.", bundle: .module)
    }
}
