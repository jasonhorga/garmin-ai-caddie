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
}
