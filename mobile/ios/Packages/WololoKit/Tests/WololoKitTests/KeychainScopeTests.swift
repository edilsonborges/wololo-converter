import Testing
@testable import WololoKit

struct KeychainScopeTests {
    @Test func equivalentServerAddressesShareOneCredential() throws {
        let store = KeychainStore()
        let original = try store.account(serverURL: "https://wololo.edilson.dev")
        #expect(try store.account(serverURL: "https://WOLOLO.EDILSON.DEV:443/api/") == original)
        #expect(try store.account(serverURL: "https://wololo.edilson.dev/") == original)
    }

    @Test(arguments: [
        "https://other.example",
        "https://wololo.edilson.dev:8443",
        "https://wololo.edilson.dev/another-server"
    ])
    func differentEndpointsHaveIndependentCredentials(_ other: String) throws {
        let store = KeychainStore()
        #expect(try store.account(serverURL: other) != store.account(serverURL: AppConstants.defaultServer))
    }

    @Test func insecureAddressesCannotReadOrOverwriteAStoredKey() {
        let store = KeychainStore()
        #expect(throws: APIError.self) { try store.readKey(serverURL: "http://wololo.edilson.dev") }
        #expect(throws: APIError.self) { try store.saveKey("test-key", serverURL: "http://wololo.edilson.dev") }
    }
}
