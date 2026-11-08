import XCTest

final class LaunchTests: XCTestCase {
    @MainActor
    func testRejectsUnsupportedLinkAndOpensSettings() throws {
        let app = XCUIApplication()
        app.launch()
        let system = XCUIApplication(bundleIdentifier: "com.apple.springboard")
        let allow = system.buttons["Allow"]
        if allow.waitForExistence(timeout: 3) { allow.tap() }
        let input = app.descendants(matching: .any)["download.url"].firstMatch
        XCTAssertTrue(input.waitForExistence(timeout: 10))
        let download = app.buttons["download.start"]
        XCTAssertFalse(download.isEnabled)
        input.tap()
        input.typeText("https://example.org/video")
        XCTAssertTrue(download.isEnabled)
        download.tap()
        XCTAssertTrue(app.staticTexts["Share or paste a supported video link."].waitForExistence(timeout: 5))
        app.tabBars.buttons["Settings"].tap()
        XCTAssertTrue(app.textFields["settings.server"].waitForExistence(timeout: 5))
        XCTAssertTrue(app.secureTextFields["Access key"].exists)
        let attachment = XCTAttachment(screenshot: app.screenshot())
        attachment.name = "Wololo settings"
        attachment.lifetime = .keepAlways
        add(attachment)
    }
}
