import CoreLocation
import XCTest
@testable import AICaddieWatch

@MainActor
final class WatchManualShotTests: XCTestCase {
    private let now = Date(timeIntervalSince1970: 1_800_000_000)

    private func fix(age: TimeInterval = 0, speed: Double = 0) -> WatchLocationFix {
        WatchLocationFix(
            coordinate: CLLocationCoordinate2D(latitude: 40, longitude: 116),
            horizontalAccuracyM: 5,
            capturedAt: ISO8601DateFormatter().string(from: now.addingTimeInterval(-age)),
            speedMps: speed
        )
    }

    private func makeModel() -> (WatchRoundModel, URL) {
        let directory = FileManager.default.temporaryDirectory
            .appendingPathComponent("watch-manual-shot-\(UUID().uuidString)", isDirectory: true)
        let model = WatchRoundModel(
            store: WatchRoundStore(directoryURL: directory),
            autoShotEnabled: false,
            persistAutoShotEnabled: { _ in },
            now: { "2027-01-15T08:00:00Z" }
        )
        model.seedRound([
            WatchRoundState(
                roundId: "manual-shot-round", hole: 1, par: 4, distanceM: nil,
                selectedClub: nil, score: 0, putts: 0, penaltyCount: 0,
                caddieConfidence: "offline"
            ),
        ], activeHole: 1, courseName: "Fixture course")
        return (model, directory)
    }

    // Card 455 G5/G6: both pages share this action; no location must never reach the model.
    func testMissingAndUnusableFixesNeverBeginAShotAndRequestFailureFeedback() {
        var haptics: [WatchManualShotFeedback.Haptic] = []
        let feedback = WatchManualShotFeedback(now: { self.now }, playHaptic: { haptics.append($0) })
        var beginCount = 0
        for unavailable in [nil, fix(age: 31), fix(age: 20, speed: 6)] as [WatchLocationFix?] {
            feedback.record(at: unavailable) { _ in
                beginCount += 1
                return true
            }
            XCTAssertTrue(feedback.needsGPS)
        }
        XCTAssertEqual(beginCount, 0)
        XCTAssertEqual(haptics, [.failure, .failure, .failure])
    }

    // Card 455 G5: exercise the action used by the map's +, with its production model.
    func testMapPlusWithoutGPSRequestsPromptAndFailureHaptic() {
        let (model, directory) = makeModel()
        defer { try? FileManager.default.removeItem(at: directory) }
        var haptics: [WatchManualShotFeedback.Haptic] = []
        let feedback = WatchManualShotFeedback(now: { self.now }, playHaptic: { haptics.append($0) })
        let view = WatchRoundContainerView(model: model, holeGeometry: WatchHoleMapSample.geometry)

        view.recordManualShot(feedback: feedback)

        XCTAssertNil(model.pendingManualShot)
        XCTAssertTrue(feedback.needsGPS)
        XCTAssertEqual(haptics, [.failure])
    }

    // Card 455 G6: invoke the real score-only button callback, including its prompt projection.
    func testScoreOnlyPlusWithoutGPSRemainsActionableAndShowsFailurePrompt() throws {
        let (model, directory) = makeModel()
        defer { try? FileManager.default.removeItem(at: directory) }
        var haptics: [WatchManualShotFeedback.Haptic] = []
        let feedback = WatchManualShotFeedback(now: { self.now }, playHaptic: { haptics.append($0) })
        let container = WatchRoundContainerView(model: model)
        let state = try XCTUnwrap(model.activeHoleState)
        let home = container.scoreOnlyRoot(state, feedback: feedback)
        XCTAssertFalse(home.canRecordShot, "unavailable GPS dims the button")
        XCTAssertFalse(home.manualShotNeedsGPS)

        home.onRecordShot()

        XCTAssertNil(model.pendingManualShot)
        XCTAssertTrue(container.scoreOnlyRoot(state, feedback: feedback).manualShotNeedsGPS)
        XCTAssertEqual(haptics, [.failure])
    }

    // Card 455 G7: an accepted tap invokes beginManualShot exactly once before playing click.
    func testUsableFixBeginsExactlyOneShotAndHapticFollowsTheResult() {
        let acceptedFix = fix(age: 30)
        var began: [WatchLocationFix] = []
        var haptics: [WatchManualShotFeedback.Haptic] = []
        let feedback = WatchManualShotFeedback(now: { self.now }, playHaptic: {
            XCTAssertEqual(began.count, 1, "feedback follows the model's result")
            haptics.append($0)
        })

        feedback.record(at: acceptedFix) { fix in
            began.append(fix)
            return true
        }

        XCTAssertEqual(began, [acceptedFix])
        XCTAssertEqual(haptics, [.click])
        XCTAssertFalse(feedback.needsGPS)
    }

    // Card 455 G7: raw wrist fixes bypass the rangefinder gate on both production button paths.
    func testBothPagesRecordOneShotFromTheRawThirtySecondFix() throws {
        for hasMap in [true, false] {
            let (model, directory) = makeModel()
            defer { try? FileManager.default.removeItem(at: directory) }
            var haptics: [WatchManualShotFeedback.Haptic] = []
            let feedback = WatchManualShotFeedback(now: { self.now }, playHaptic: { haptics.append($0) })
            let rawFix = fix(age: 30)
            let container = WatchRoundContainerView(
                model: model,
                holeGeometry: hasMap ? WatchHoleMapSample.geometry : nil,
                shotLocation: nil,
                latestWatchFix: rawFix
            )
            if hasMap {
                container.recordManualShot(feedback: feedback)
            } else {
                let home = container.scoreOnlyRoot(try XCTUnwrap(model.activeHoleState), feedback: feedback)
                XCTAssertTrue(home.canRecordShot)
                home.onRecordShot()
            }

            let pending = try XCTUnwrap(model.pendingManualShot)
            XCTAssertEqual(pending.shotNumber, 1)
            XCTAssertEqual(pending.location.latitude, rawFix.coordinate.latitude)
            XCTAssertEqual(pending.location.longitude, rawFix.coordinate.longitude)
            XCTAssertEqual(pending.location.horizontalAccuracyM, rawFix.horizontalAccuracyM)
            XCTAssertEqual(pending.capturedAt, rawFix.capturedAt)
            XCTAssertEqual(model.pendingUploads, 0, "one tap leaves only its undoable pending shot")
            XCTAssertEqual(haptics, [.click])
            XCTAssertFalse(feedback.needsGPS)
        }
    }

    func testADeclinedModelActionPlaysFailureInsteadOfClick() {
        var haptics: [WatchManualShotFeedback.Haptic] = []
        let feedback = WatchManualShotFeedback(now: { self.now }, playHaptic: { haptics.append($0) })
        var beginCount = 0
        feedback.record(at: fix()) { _ in
            beginCount += 1
            return false
        }
        XCTAssertEqual(beginCount, 1)
        XCTAssertEqual(haptics, [.failure])
        XCTAssertFalse(feedback.needsGPS)
    }

    func testProductionActionPlaysFailureWhenTheModelHasNoActiveHole() {
        let (model, directory) = makeModel()
        defer { try? FileManager.default.removeItem(at: directory) }
        model.requestAbandon()
        model.confirmAbandon()
        var haptics: [WatchManualShotFeedback.Haptic] = []
        let feedback = WatchManualShotFeedback(now: { self.now }, playHaptic: { haptics.append($0) })

        WatchRoundContainerView(model: model, latestWatchFix: fix()).recordManualShot(feedback: feedback)

        XCTAssertNil(model.pendingManualShot)
        XCTAssertEqual(haptics, [.failure])
    }

    func testFixExpiringBetweenRenderAndTapStillShowsFailureFeedback() {
        var tapTime = now
        var haptics: [WatchManualShotFeedback.Haptic] = []
        let feedback = WatchManualShotFeedback(now: { tapTime }, playHaptic: { haptics.append($0) })
        let renderedFix = fix(age: 30)
        XCTAssertTrue(feedback.canRecord(at: renderedFix))
        tapTime = now.addingTimeInterval(1)

        feedback.record(at: renderedFix) { _ in
            XCTFail("expired fix must never begin a shot")
            return true
        }

        XCTAssertTrue(feedback.needsGPS)
        XCTAssertEqual(haptics, [.failure])
    }

    func testRepeatedFailureRestartsPromptAndSuccessClearsIt() throws {
        let feedback = WatchManualShotFeedback(now: { self.now }, playHaptic: { _ in })
        feedback.record(at: nil) { _ in XCTFail("no GPS"); return true }
        let firstPrompt = try XCTUnwrap(feedback.gpsPromptID)
        feedback.record(at: nil) { _ in XCTFail("no GPS"); return true }
        let secondPrompt = try XCTUnwrap(feedback.gpsPromptID)
        XCTAssertNotEqual(firstPrompt, secondPrompt)

        feedback.dismissGPSPrompt(firstPrompt)
        XCTAssertTrue(feedback.needsGPS, "an earlier timeout cannot clear the latest tap's prompt")
        feedback.dismissGPSPrompt(secondPrompt)
        XCTAssertFalse(feedback.needsGPS)

        feedback.record(at: nil) { _ in XCTFail("no GPS"); return true }
        feedback.record(at: fix()) { _ in true }
        XCTAssertFalse(feedback.needsGPS)
    }
}
