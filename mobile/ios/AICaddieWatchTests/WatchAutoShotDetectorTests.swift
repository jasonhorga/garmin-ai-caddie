import XCTest
@testable import AICaddieWatch

final class WatchAutoShotDetectorTests: XCTestCase {
    func testImpactWithoutAPrecedingSwingDoesNotCreateCandidate() {
        var detector = WatchAutoShotDetector()
        detector.appendDeviceMotion([
            WatchAutoShotRotationSample(timestamp: 0.0, rotationAlongGravity: 0.1),
            WatchAutoShotRotationSample(timestamp: 0.4, rotationAlongGravity: 0.2),
            WatchAutoShotRotationSample(timestamp: 0.7, rotationAlongGravity: 0.1),
        ])

        let detections = detector.processAccelerometer([
            WatchAutoShotAccelerationSample(timestamp: 0.8, x: 0, y: 0, z: 4.0),
        ])

        XCTAssertTrue(detections.isEmpty)
    }

    func testSwingThenImpactCreatesOneCandidate() {
        var detector = WatchAutoShotDetector()
        detector.appendDeviceMotion(swingSamples(endingAt: 0.7))

        let detections = detector.processAccelerometer([
            WatchAutoShotAccelerationSample(timestamp: 0.78, x: 0, y: 0, z: 1.1),
            WatchAutoShotAccelerationSample(timestamp: 0.80, x: 0, y: 0, z: 4.0),
            WatchAutoShotAccelerationSample(timestamp: 0.81, x: 0, y: 0, z: 3.8),
        ])

        XCTAssertEqual(detections.map(\.timestamp), [0.80])
    }

    func testCooldownSuppressesDuplicateImpactsFromOneSwing() {
        var detector = WatchAutoShotDetector()
        detector.appendDeviceMotion(swingSamples(endingAt: 0.7))
        _ = detector.processAccelerometer([
            WatchAutoShotAccelerationSample(timestamp: 0.8, x: 0, y: 0, z: 4.0),
        ])

        detector.appendDeviceMotion(swingSamples(endingAt: 1.5))
        let duplicate = detector.processAccelerometer([
            WatchAutoShotAccelerationSample(timestamp: 1.6, x: 0, y: 0, z: 4.2),
        ])

        XCTAssertTrue(duplicate.isEmpty)
    }

    func testNewSwingAfterCooldownCreatesAnotherCandidate() {
        var detector = WatchAutoShotDetector()
        detector.appendDeviceMotion(swingSamples(endingAt: 0.7))
        _ = detector.processAccelerometer([
            WatchAutoShotAccelerationSample(timestamp: 0.8, x: 0, y: 0, z: 4.0),
        ])

        detector.appendDeviceMotion(swingSamples(endingAt: 4.1))
        let later = detector.processAccelerometer([
            WatchAutoShotAccelerationSample(timestamp: 4.2, x: 0, y: 0, z: 4.1),
        ])

        XCTAssertEqual(later.map(\.timestamp), [4.2])
    }

    func testDeviceMotionMayArriveAfterTheAccelerometerBatch() {
        var detector = WatchAutoShotDetector()
        let beforeMotion = detector.processAccelerometer([
            WatchAutoShotAccelerationSample(timestamp: 0.8, x: 0, y: 0, z: 4.0),
        ])
        XCTAssertTrue(beforeMotion.isEmpty)

        let afterMotion = detector.appendDeviceMotion(swingSamples(endingAt: 0.7))

        XCTAssertEqual(afterMotion.map(\.timestamp), [0.8])
    }

    private func swingSamples(endingAt end: TimeInterval) -> [WatchAutoShotRotationSample] {
        [
            WatchAutoShotRotationSample(timestamp: end - 0.7, rotationAlongGravity: 0.1),
            WatchAutoShotRotationSample(timestamp: end - 0.6, rotationAlongGravity: 0.2),
            WatchAutoShotRotationSample(timestamp: end - 0.3, rotationAlongGravity: 3.4),
            WatchAutoShotRotationSample(timestamp: end - 0.2, rotationAlongGravity: 4.2),
            WatchAutoShotRotationSample(timestamp: end - 0.1, rotationAlongGravity: 3.1),
            WatchAutoShotRotationSample(timestamp: end, rotationAlongGravity: 2.4),
        ]
    }
}
