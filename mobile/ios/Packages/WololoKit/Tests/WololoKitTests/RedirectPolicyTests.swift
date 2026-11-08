import Foundation
import Testing
@testable import WololoKit

struct RedirectPolicyTests {
    @Test(arguments: [
        ("https://wololo.test/api/file", true),
        ("https://WOLOLO.TEST:443/api/file", true),
        ("https://other.test/file", false),
        ("http://wololo.test/api/file", false),
        ("https://wololo.test:8443/api/file", false),
        ("https://name:secret@wololo.test/file", false)
    ])
    func onlyFollowsRedirectsWithinTheOriginalHTTPSOrigin(address: String, permitted: Bool) {
        let original = URL(string: "https://wololo.test/api/health")
        #expect(OriginRedirectPolicy.permits(original: original, redirected: URL(string: address)) == permitted)
    }
}
