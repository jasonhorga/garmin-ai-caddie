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
            "Apple 登录已失效，请重新登录。"
        )
        XCTAssertEqual(
            MobileCourseSearchView.searchErrorMessage(error, nearby: true),
            "Apple 登录已失效，请重新登录。"
        )
        XCTAssertEqual(
            MobileCourseSearchView.searchErrorMessage(SyncClientError.http(status: 403, body: nil), nearby: false),
            "当前 Apple 账号无权访问球场目录。"
        )
    }

    func testGarminImportErrorsKeepAuthorizationFailureActionable() {
        XCTAssertEqual(
            GarminSessionView.importErrorMessage(SyncClientError.http(status: 401, body: nil)),
            "Apple 登录已失效，请重新登录"
        )
        XCTAssertEqual(
            GarminSessionView.importErrorMessage(SyncClientError.http(status: 422, body: nil)),
            "Garmin 登录信息无效，请重新登录"
        )
        XCTAssertEqual(
            GarminSessionView.importErrorMessage(SyncClientError.http(status: 403, body: nil)),
            "当前 Apple 账号无权连接此 Garmin"
        )
        XCTAssertEqual(
            GarminSessionView.importErrorMessage(URLError(.timedOut)),
            "连接失败，请重试"
        )
    }

    func testGarminImport401InvalidatesAppleSessionExceptExplicitUITestBypass() {
        let error = SyncClientError.http(status: 401, body: nil)
        #if DEBUG
        XCTAssertTrue(GarminSessionView.shouldInvalidateAppleSession(error, environment: [:]))
        XCTAssertFalse(GarminSessionView.shouldInvalidateAppleSession(error, environment: ["UITEST_MODE": "1"]))
        #else
        XCTAssertTrue(GarminSessionView.shouldInvalidateAppleSession(error, environment: ["UITEST_MODE": "1"]))
        #endif
        XCTAssertFalse(GarminSessionView.shouldInvalidateAppleSession(
            SyncClientError.http(status: 422, body: nil),
            environment: [:]
        ))
    }

    func testGarminCaptureRetryIsBounded() {
        XCTAssertTrue(GarminWebSessionCaptureView.Coordinator.shouldRetryCapture(attempt: 0))
        XCTAssertTrue(GarminWebSessionCaptureView.Coordinator.shouldRetryCapture(attempt: 2))
        XCTAssertFalse(GarminWebSessionCaptureView.Coordinator.shouldRetryCapture(attempt: 3))
        XCTAssertFalse(GarminWebSessionCaptureView.Coordinator.shouldRetryCapture(attempt: -1))
    }
}
