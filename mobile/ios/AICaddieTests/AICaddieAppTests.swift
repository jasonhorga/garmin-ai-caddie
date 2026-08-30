import Foundation
import XCTest
@testable import AICaddie

final class AICaddieAppTests: XCTestCase {
    func testSignInRequiredWithoutSessionUnlessExplicitUITestBypass() {
        XCTAssertTrue(AICaddieApp.requiresAppleSignIn(environment: [:], session: nil))
        XCTAssertTrue(AICaddieApp.requiresAppleSignIn(environment: ["UITEST_MODE": "0"], session: nil))
        XCTAssertTrue(AICaddieApp.requiresAppleSignIn(environment: ["UITEST_MODE": "true"], session: nil))

        #if DEBUG
        XCTAssertTrue(AICaddieApp.debugUITestBypassAllowed(environment: ["UITEST_MODE": "1"]))
        XCTAssertFalse(AICaddieApp.requiresAppleSignIn(environment: ["UITEST_MODE": "1"], session: nil))
        #else
        XCTAssertFalse(AICaddieApp.debugUITestBypassAllowed(environment: ["UITEST_MODE": "1"]))
        XCTAssertTrue(AICaddieApp.requiresAppleSignIn(environment: ["UITEST_MODE": "1"], session: nil))
        #endif
    }

    func testValidSessionSatisfiesSignInGate() {
        let session = AppSession(token: "token", playerId: "player", expiresAt: Date().addingTimeInterval(60))
        XCTAssertFalse(AICaddieApp.requiresAppleSignIn(environment: [:], session: session))
    }

    func testExpiredSessionRequiresSignIn() {
        let session = AppSession(token: "token", playerId: "player", expiresAt: Date().addingTimeInterval(-60))
        XCTAssertTrue(AICaddieApp.requiresAppleSignIn(environment: [:], session: session))
    }

    func testGarminHostPolicyAllowsOfficialSSOAndRejectsLookalikes() {
        XCTAssertTrue(GarminWebSessionCaptureView.isOfficialGarminHost("connect.garmin.cn"))
        XCTAssertTrue(GarminWebSessionCaptureView.isOfficialGarminHost("sso.garmin.com"))
        XCTAssertTrue(GarminWebSessionCaptureView.isOfficialGarminHost("GARMIN.COM."))
        XCTAssertFalse(GarminWebSessionCaptureView.isOfficialGarminHost("evilgarmin.com"))
        XCTAssertFalse(GarminWebSessionCaptureView.isOfficialGarminHost("garmin.com.evil.test"))
        XCTAssertFalse(GarminWebSessionCaptureView.isOfficialGarminHost("accounts.google.com"))
        XCTAssertFalse(GarminWebSessionCaptureView.isOfficialGarminHost(nil))
    }

    func testGarminGolfProbeStaysOnConnectAndUsesOfficialPath() {
        let modern = URL(string: "https://connect.garmin.cn/modern/")!
        XCTAssertEqual(
            GarminWebSessionCaptureView.officialGolfURL(from: modern)?.absoluteString,
            "https://connect.garmin.cn/app/golf"
        )
        XCTAssertNil(GarminWebSessionCaptureView.officialGolfURL(from: URL(string: "https://sso.garmin.com/login")!))
        XCTAssertNil(GarminWebSessionCaptureView.officialGolfURL(from: URL(string: "https://connect.garmin.cn/app/golf")!))
        XCTAssertNil(GarminWebSessionCaptureView.officialGolfURL(from: URL(string: "https://evilgarmin.com/modern")!))
    }

    func testCourseSearchExplainsExpiredGarminLogin() {
        let error = SyncClientError.http(status: 401, body: nil)
        XCTAssertEqual(
            MobileCourseSearchView.searchErrorMessage(error, nearby: false),
            "Garmin 登录已失效，请先连接 Garmin 再搜索。"
        )
        XCTAssertEqual(
            MobileCourseSearchView.searchErrorMessage(error, nearby: true),
            "Garmin 登录已失效，请先连接 Garmin 再搜索。"
        )
    }
}
