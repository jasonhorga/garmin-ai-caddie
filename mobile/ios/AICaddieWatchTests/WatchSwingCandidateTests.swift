import XCTest
@testable import AICaddieWatch

/// B7 step 1 fixtures (IMPLEMENTATION_PLAN B7 验收): a real shot, a practice swing hitting the ground,
/// an air swing, a post-shot gesture, a putt and a cart ride each get their own kind.
final class WatchSwingCandidateTests: XCTestCase {
    /// 100 Hz rotation: `still` seconds quiet, then a triangle up to `peak` and back over `swing` s.
    private func rotation(start: Double = 0, still: Double, swing: Double, peak: Double) -> [WatchAutoShotRotationSample] {
        var samples: [WatchAutoShotRotationSample] = []
        let dt = 0.01
        var t = start
        while t < start + still { samples.append(.init(timestamp: t, rotationAlongGravity: 0.05)); t += dt }
        let swingStart = t
        while t < swingStart + swing {
            let phase = (t - swingStart) / swing
            samples.append(.init(timestamp: t, rotationAlongGravity: peak * (1 - abs(2 * phase - 1)) + 0.31))
            t += dt
        }
        let settle = t
        while t < settle + 0.6 { samples.append(.init(timestamp: t, rotationAlongGravity: 0.05)); t += dt }
        return samples
    }

    /// 1 kHz acceleration around `at`: 1 g, with `peakG` deviation lasting `durationMs`.
    private func impact(at: Double, peakG: Double, durationMs: Double) -> [WatchAutoShotAccelerationSample] {
        stride(from: at - 0.05, to: at + 0.05, by: 0.001).map { t in
            let inside = abs(t - at) * 1000 <= durationMs / 2
            return .init(timestamp: t, x: 0, y: 0, z: inside ? 1 + peakG : 1)
        }
    }

    func testARealShotIsAFullSwingWithASharpImpact() throws {
        let rot = rotation(still: 1.5, swing: 1.0, peak: 9)
        let f = try XCTUnwrap(WatchSwingFeatureExtractor.features(rotation: rot, acceleration: impact(at: 2.0, peakG: 4, durationMs: 6)))
        XCTAssertEqual(f.kind, .fullSwing)
        XCTAssertEqual(f.stillnessBeforeS, 1.5, accuracy: 0.05)
        XCTAssertEqual(f.swingDurationS, 1.0, accuracy: 0.05)
        XCTAssertGreaterThan(f.cumulativeRotationRad, 4)
        XCTAssertEqual(try XCTUnwrap(f.impactPeakG), 4, accuracy: 0.01)
        XCTAssertLessThan(try XCTUnwrap(f.impactDurationMs), 15)
    }

    func testAPracticeSwingHittingTheGroundHasADullImpact() throws {
        let rot = rotation(still: 0.4, swing: 1.0, peak: 8)
        let f = try XCTUnwrap(WatchSwingFeatureExtractor.features(rotation: rot, acceleration: impact(at: 0.9, peakG: 2.5, durationMs: 30)))
        XCTAssertEqual(f.kind, .groundPracticeSwing)
    }

    func testAnAirSwingOrAPostShotGestureHasNoImpact() throws {
        let air = try XCTUnwrap(WatchSwingFeatureExtractor.features(rotation: rotation(still: 0.2, swing: 0.9, peak: 7), acceleration: []))
        XCTAssertEqual(air.kind, .airSwing)
        XCTAssertNil(air.impactPeakG)
        let gesture = try XCTUnwrap(WatchSwingFeatureExtractor.features(rotation: rotation(still: 0, swing: 0.5, peak: 1.2), acceleration: []))
        XCTAssertEqual(gesture.kind, .unknown, "a half gesture without stillness or impact is not a shot")
    }

    func testAPuttIsASlowSwingWithASmallImpactAfterStillness() throws {
        let rot = rotation(still: 1.4, swing: 0.8, peak: 1.0)
        let f = try XCTUnwrap(WatchSwingFeatureExtractor.features(rotation: rot, acceleration: impact(at: 1.8, peakG: 0.5, durationMs: 8)))
        XCTAssertEqual(f.kind, .putt)
    }

    func testRidingInACartIsNeverAShot() throws {
        let f = try XCTUnwrap(WatchSwingFeatureExtractor.features(
            rotation: rotation(still: 1.5, swing: 1.0, peak: 9),
            acceleration: impact(at: 2.0, peakG: 4, durationMs: 6),
            speedMps: 5
        ))
        XCTAssertEqual(f.kind, .riding)
    }

    func testStillnessAloneIsNoCandidate() {
        let quiet = (0..<200).map { WatchAutoShotRotationSample(timestamp: Double($0) * 0.01, rotationAlongGravity: 0.05) }
        XCTAssertNil(WatchSwingFeatureExtractor.features(rotation: quiet, acceleration: []))
    }

    func testTheCollectorEmitsOneCandidatePerSettledBurst() {
        var collector = WatchSwingCandidateCollector()
        collector.appendAcceleration(impact(at: 2.0, peakG: 4, durationMs: 6))
        let rot = rotation(still: 1.5, swing: 1.0, peak: 9)
        // Streamed in 0.25 s batches, as CoreMotion delivers them.
        var emitted: [WatchSwingFeatures] = []
        var index = 0
        while index < rot.count {
            let batch = Array(rot[index..<min(index + 25, rot.count)])
            if let features = collector.appendRotation(batch) { emitted.append(features) }
            index += 25
        }
        XCTAssertEqual(emitted.map(\.kind), [.fullSwing])
        let second = rotation(start: 3.2, still: 0.3, swing: 0.9, peak: 7)
        var more: [WatchSwingFeatures] = []
        index = 0
        while index < second.count {
            let batch = Array(second[index..<min(index + 25, second.count)])
            if let features = collector.appendRotation(batch) { more.append(features) }
            index += 25
        }
        XCTAssertEqual(more.map(\.kind), [.airSwing], "the next burst is its own candidate")
    }

    func testCandidatesAreStoredPerRoundAndRemovedAfterUpload() {
        let store = WatchSwingCandidateStore(directoryURL: FileManager.default.temporaryDirectory
            .appendingPathComponent("swing-\(UUID().uuidString)", isDirectory: true))
        let features = WatchSwingFeatures(kind: .fullSwing, stillnessBeforeS: 1.2, swingDurationS: 1.0,
                                          cumulativeRotationRad: 5, peakRotationRadS: 9, impactPeakG: 4, impactDurationMs: 6)
        store.append(WatchSwingCandidateRecord(id: "a", capturedAt: "2026-10-02T08:00:00Z", hole: 1, features: features,
                                               horizontalAccuracyM: 6, speedMps: nil, proposedShot: true), roundId: "r-1")
        XCTAssertEqual(store.load(roundId: "r-1").map(\.id), ["a"])
        XCTAssertEqual(store.pendingRoundIds(), ["r-1"])
        store.remove(roundId: "r-1")
        XCTAssertTrue(store.load(roundId: "r-1").isEmpty)
    }

    // MARK: - Codex review on #368

    private func tempStore() -> WatchSwingCandidateStore {
        WatchSwingCandidateStore(directoryURL: FileManager.default.temporaryDirectory
            .appendingPathComponent("swing-\(UUID().uuidString)", isDirectory: true))
    }

    private func record(_ id: String) -> WatchSwingCandidateRecord {
        WatchSwingCandidateRecord(
            id: id, capturedAt: "2026-10-02T08:00:00Z", hole: 1,
            features: WatchSwingFeatures(kind: .fullSwing, stillnessBeforeS: 1.2, swingDurationS: 1.0,
                                         cumulativeRotationRad: 5, peakRotationRadS: 9, impactPeakG: 4, impactDurationMs: 6),
            horizontalAccuracyM: 6, speedMps: nil, proposedShot: false
        )
    }

    private func chunks<T>(_ samples: [T], size: Int = 25) -> [[T]] {
        stride(from: 0, to: samples.count, by: size).map { Array(samples[$0..<min($0 + size, samples.count)]) }
    }

    /// Feeds a real shot through the production session as CoreMotion batches.
    private func feedShot(_ session: inout WatchSwingCollectionSession, start: Double = 0, now: Date) -> [WatchSwingObservation] {
        session.accelerationBatch(impact(at: start + 2.0, peakG: 4, durationMs: 6))
        return chunks(rotation(start: start, still: 1.5, swing: 1.0, peak: 9)).compactMap {
            // The batch is delivered as its newest sample is taken.
            session.rotationBatch($0, now: now, uptime: $0.map(\.timestamp).max() ?? 0)
        }
    }

    func testAMovingCartIsRidingThroughTheProductionSession() throws {
        let now = Date(timeIntervalSince1970: 1_790_000_000)
        var session = WatchSwingCollectionSession()
        session.updateSpeed(WatchSwingSpeedSample(speedMps: 5.5, accuracyMps: 1, capturedAt: now.addingTimeInterval(-3)))
        let observations = feedShot(&session, now: now)
        let only = try XCTUnwrap(observations.first)
        XCTAssertEqual(observations.count, 1)
        XCTAssertEqual(only.features.kind, .riding)
        XCTAssertEqual(only.speedMps, 5.5)
    }

    func testUnknownStaleOrInaccurateSpeedFailsClosed() throws {
        let now = Date(timeIntervalSince1970: 1_790_000_000)
        let readings: [WatchSwingSpeedSample?] = [
            nil,
            WatchSwingSpeedSample(speedMps: 5.5, accuracyMps: 1, capturedAt: now.addingTimeInterval(-30)),
            WatchSwingSpeedSample(speedMps: 5.5, accuracyMps: 6, capturedAt: now.addingTimeInterval(-1)),
        ]
        for reading in readings {
            var session = WatchSwingCollectionSession()
            session.updateSpeed(reading)
            let only = try XCTUnwrap(feedShot(&session, now: now).first)
            // Without a usable speed the riding filter cannot run: never `.riding`, recorded as unknown.
            XCTAssertEqual(only.features.kind, .fullSwing)
            XCTAssertNil(only.speedMps)
        }
        let fix = WatchLocationFix(
            coordinate: .init(latitude: 40, longitude: 116), horizontalAccuracyM: 5,
            capturedAt: "2026-10-02T08:00:00Z", speedMps: nil, speedAccuracyMps: nil
        )
        XCTAssertNil(WatchSwingSpeedSample(fix: fix), "a fix without speed gives no speed reading")
    }

    func testAnInterruptionStopsDetectionAndCollectionButKeepsStoredCandidates() throws {
        let now = Date(timeIntervalSince1970: 1_790_000_000)
        let store = tempStore()
        var session = WatchSwingCollectionSession()
        for observation in feedShot(&session, now: now) {
            store.append(record(observation.id.uuidString), roundId: "r1")
        }
        XCTAssertEqual(store.load(roundId: "r1").count, 1)

        XCTAssertNil(session.rotationBatch([], now: now), "an empty delivery is a quiet batch")
        XCTAssertFalse(session.isInterrupted)
        XCTAssertNil(session.rotationBatch(nil, now: now))
        XCTAssertTrue(session.isInterrupted, "a delivery without data is an interruption")

        XCTAssertTrue(feedShot(&session, start: 4, now: now).isEmpty, "no later automatic candidate")
        XCTAssertFalse(session.detection(at: 6, autoShotWanted: true), "no later automatic shot")
        XCTAssertEqual(store.load(roundId: "r1").count, 1, "stored candidates are kept")

        var gapped = WatchSwingCollectionSession()
        _ = gapped.rotationBatch(rotation(still: 0.5, swing: 0, peak: 0), now: now)
        XCTAssertNil(gapped.rotationBatch(rotation(start: 30, still: 0.5, swing: 0, peak: 0), now: now))
        XCTAssertTrue(gapped.isInterrupted, "a long gap between batches is an interruption")
    }

    func testCollectionAloneNeverProposesAShotButTagsTheCandidate() throws {
        let now = Date(timeIntervalSince1970: 1_790_000_000)
        var session = WatchSwingCollectionSession()
        XCTAssertFalse(session.detection(at: 2.0, autoShotWanted: false))
        let tagged = try XCTUnwrap(feedShot(&session, now: now).first)
        XCTAssertTrue(tagged.proposedShot)
        var withAutoShot = WatchSwingCollectionSession()
        XCTAssertTrue(withAutoShot.detection(at: 2.0, autoShotWanted: true))
    }

    func testOutOfOrderBatchesGiveTheSameCandidate() throws {
        let rot = chunks(rotation(still: 1.5, swing: 1.0, peak: 9))
        let acc = chunks(impact(at: 2.0, peakG: 4, durationMs: 6), size: 20)
        var inOrder = WatchSwingCandidateCollector()
        acc.forEach { inOrder.appendAcceleration($0) }
        let expected = try XCTUnwrap(rot.compactMap { inOrder.appendRotation($0) }.first)

        var shuffled = WatchSwingCandidateCollector()
        acc.reversed().forEach { shuffled.appendAcceleration($0) }
        // Swap every adjacent pair of rotation batches.
        var swapped: [[WatchAutoShotRotationSample]] = []
        var index = 0
        while index < rot.count {
            if index + 1 < rot.count { swapped.append(rot[index + 1]) }
            swapped.append(rot[index])
            index += 2
        }
        let emitted = swapped.compactMap { shuffled.appendRotation($0) }
        XCTAssertEqual(emitted, [expected], "a partial burst is never emitted early")
    }

    func testDistinctRoundIdsNeverShareAFile() {
        let store = tempStore()
        store.append(record("a"), roundId: "live/1")
        store.append(record("b"), roundId: "live_1")
        XCTAssertEqual(store.load(roundId: "live/1").map(\.id), ["a"])
        XCTAssertEqual(store.load(roundId: "live_1").map(\.id), ["b"])
        XCTAssertEqual(store.pendingRoundIds(), ["live/1", "live_1"], "uploads target the original IDs")
    }

    func testACandidateIsRoutedByItsMotionTimeEvenAfterTheNextRoundStarts() {
        var router = WatchSwingCandidateRouter()
        let t0 = Date(timeIntervalSince1970: 1_790_000_000)
        router.roundChanged(to: "A", at: t0)
        router.holeChanged(to: 1, at: t0)
        router.holeChanged(to: 7, at: t0.addingTimeInterval(600))
        // A closes (phone Finish), then B starts; A's last swing is delivered only after that.
        XCTAssertEqual(router.roundChanged(to: nil, at: t0.addingTimeInterval(900)), "A")
        router.holeChanged(to: 0, at: t0.addingTimeInterval(901))
        router.roundChanged(to: "B", at: t0.addingTimeInterval(950))
        router.holeChanged(to: 1, at: t0.addingTimeInterval(950))

        XCTAssertEqual(router.assignment(forMotionAt: t0.addingTimeInterval(895)),
                       .init(roundId: "A", hole: 7), "a late A candidate stays on A, on the hole A was on")
        XCTAssertEqual(router.assignment(forMotionAt: t0.addingTimeInterval(300)), .init(roundId: "A", hole: 1))
        XCTAssertEqual(router.assignment(forMotionAt: t0.addingTimeInterval(960)), .init(roundId: "B", hole: 1))
        XCTAssertNil(router.assignment(forMotionAt: t0.addingTimeInterval(920)), "between rounds: no candidate")
        XCTAssertNil(router.assignment(forMotionAt: t0.addingTimeInterval(-5)), "before any round")
        XCTAssertEqual(router.activeRoundId, "B")
    }

    /// The swing ends just before the phone closes the round; the quiet tail that completes the burst
    /// arrives after the closure. The candidate still belongs to the closed round, on its hole.
    func testASwingEndingBeforeClosureWithItsTailAfterStaysOnTheClosedRound() throws {
        let t0 = Date(timeIntervalSince1970: 1_790_000_000)
        // Sensor clock: the round starts at uptime 100 (= t0); the swing is active 100+1.5 ... 100+2.5.
        let base = 100.0
        var router = WatchSwingCandidateRouter()
        router.roundChanged(to: "A", at: t0)
        router.holeChanged(to: 6, at: t0)
        var session = WatchSwingCollectionSession()
        let samples = rotation(start: base, still: 1.5, swing: 1.0, peak: 9)
        let swingEnd = samples.filter { abs($0.rotationAlongGravity) > WatchSwingFeatureExtractor.quietRotation }
            .map(\.timestamp).max()!
        // Closure 0.1 s after the swing ended (wall time t0 + (swingEnd - base) + 0.1).
        let closedAt = t0.addingTimeInterval(swingEnd - base + 0.1)
        router.roundChanged(to: nil, at: closedAt)
        router.roundChanged(to: "B", at: closedAt.addingTimeInterval(5))
        router.holeChanged(to: 1, at: closedAt.addingTimeInterval(5))

        var observation: WatchSwingObservation?
        for batch in chunks(samples) {
            let deliveredUptime = batch.map(\.timestamp).max()!
            let deliveredAt = t0.addingTimeInterval(deliveredUptime - base)
            if let emitted = session.rotationBatch(batch, now: deliveredAt, uptime: deliveredUptime) {
                observation = emitted
                XCTAssertGreaterThan(deliveredAt, closedAt, "the completing tail arrives after the closure")
            }
        }
        let emitted = try XCTUnwrap(observation)
        XCTAssertLessThan(emitted.observedAt, closedAt, "timed at the swing's end, not the tail's")
        XCTAssertEqual(router.assignment(forMotionAt: emitted.observedAt), .init(roundId: "A", hole: 6))
    }

    func testAClosedRoundsCandidatesUploadAndNeverGoToTheNextRound() async {
        let store = tempStore()
        var router = WatchSwingCandidateRouter()
        let t0 = Date(timeIntervalSince1970: 1_790_000_000)
        router.roundChanged(to: "A", at: t0)
        router.holeChanged(to: 4, at: t0)
        store.append(record("a"), roundId: "A")
        router.roundChanged(to: nil, at: t0.addingTimeInterval(60))
        router.roundChanged(to: "B", at: t0.addingTimeInterval(70))
        router.holeChanged(to: 1, at: t0.addingTimeInterval(70))
        let late = router.assignment(forMotionAt: t0.addingTimeInterval(55))
        XCTAssertEqual(late?.roundId, "A")
        if let late { store.append(record("late"), roundId: late.roundId) }

        var sent: [String: [String]] = [:]
        let outcome = await WatchSwingCandidateUploader(store: store).uploadClosedRounds(activeRoundId: router.activeRoundId) {
            sent[$0] = $1.map(\.id)
        }
        XCTAssertEqual(outcome.uploaded, ["A"])
        XCTAssertEqual(sent["A"], ["a", "late"])
        XCTAssertNil(sent["B"], "the active round is never uploaded, and never receives A's candidates")
        XCTAssertTrue(store.load(roundId: "B").isEmpty)
    }

    func testAFailedUploadIsKeptAndRetriedAfterRecovery() async {
        struct Offline: Error {}
        let store = tempStore()
        store.append(record("a"), roundId: "r1")
        store.append(record("x"), roundId: "active")
        let uploader = WatchSwingCandidateUploader(store: store)

        let failed = await uploader.uploadClosedRounds(activeRoundId: "active") { _, _ in throw Offline() }
        XCTAssertEqual(failed.failed, ["r1"])
        XCTAssertEqual(store.load(roundId: "r1").map(\.id), ["a"], "kept for the next attempt")

        var sent: [String] = []
        let recovered = await uploader.uploadClosedRounds(activeRoundId: "active") { roundId, _ in sent.append(roundId) }
        XCTAssertEqual(recovered.uploaded, ["r1"])
        XCTAssertEqual(sent, ["r1"], "the active round is never uploaded")
        XCTAssertEqual(store.pendingRoundIds(), ["active"])
        XCTAssertFalse(WatchSwingCandidateUploader.retryDelaysS.isEmpty)
    }

    func testACandidateAddedDuringTheUploadIsKept() async {
        let store = tempStore()
        store.append(record("a"), roundId: "r1")
        let outcome = await WatchSwingCandidateUploader(store: store).uploadClosedRounds(activeRoundId: nil) { roundId, _ in
            store.append(self.record("late"), roundId: roundId)
        }
        XCTAssertEqual(outcome.uploaded, ["r1"])
        XCTAssertEqual(store.load(roundId: "r1").map(\.id), ["late"])
    }

    @MainActor
    func testCollectionStaysUnavailableUntilTheCapabilityAndBatteryGateLands() {
        XCTAssertFalse(WatchSwingCollectionAvailability.isAvailable)
        XCTAssertFalse(WatchSwingCollectionAvailability.isCollecting(preference: true))
        XCTAssertFalse(WatchSettingsView.showsSwingCollectionRow, "the accepted settings screen is unchanged")
    }
}
