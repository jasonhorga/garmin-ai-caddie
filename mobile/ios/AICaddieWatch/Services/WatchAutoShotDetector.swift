import Foundation

/// A timestamped projection of device motion. The provider computes rotation along gravity before
/// handing samples to this pure state machine, keeping CoreMotion and workout lifecycle out of it.
public struct WatchAutoShotRotationSample: Equatable {
    public let timestamp: TimeInterval
    public let rotationAlongGravity: Double

    public init(timestamp: TimeInterval, rotationAlongGravity: Double) {
        self.timestamp = timestamp
        self.rotationAlongGravity = rotationAlongGravity
    }
}

/// Raw acceleration is deliberately short-lived. It is evaluated on the Watch and is never included in
/// a pending round, event, upload, or AutoShot candidate.
public struct WatchAutoShotAccelerationSample: Equatable {
    public let timestamp: TimeInterval
    public let x: Double
    public let y: Double
    public let z: Double

    public init(timestamp: TimeInterval, x: Double, y: Double, z: Double) {
        self.timestamp = timestamp
        self.x = x
        self.y = y
        self.z = z
    }

    fileprivate var magnitude: Double {
        (x * x + y * y + z * z).squareRoot()
    }
}

public struct WatchAutoShotDetection: Equatable {
    public let timestamp: TimeInterval
}

/// Conservative local candidate detector for the opt-in Beta. It requires a quiet setup, sustained
/// swing rotation, and a later impact-sized acceleration before emitting anything. These thresholds are
/// an engineering starting point, not a claimed Garmin rule or calibrated success rate; real-device
/// field data must tune them. A cooldown collapses one impact burst into one candidate.
public struct WatchAutoShotDetector {
    private static let motionHistorySeconds = 1.4
    private static let swingLookbackSeconds = 1.1
    private static let minimumImpactDelaySeconds = 0.02
    private static let quietRotationThreshold = 0.5
    private static let activeRotationThreshold = 2.0
    private static let peakRotationThreshold = 3.0
    private static let minimumActiveSamples = 3
    private static let impactDeviationFromGravity = 2.0
    private static let cooldownSeconds = 3.0

    private var rotationSamples: [WatchAutoShotRotationSample] = []
    private var lastDetectionTimestamp: TimeInterval?

    public init() {}

    public mutating func appendDeviceMotion(_ samples: [WatchAutoShotRotationSample]) {
        guard let newest = samples.last?.timestamp else { return }
        rotationSamples.append(contentsOf: samples)
        let oldestNeeded = newest - Self.motionHistorySeconds
        rotationSamples.removeAll { $0.timestamp < oldestNeeded }
    }

    public mutating func processAccelerometer(
        _ samples: [WatchAutoShotAccelerationSample]
    ) -> [WatchAutoShotDetection] {
        var detections: [WatchAutoShotDetection] = []
        for sample in samples {
            guard isImpact(sample), outsideCooldown(sample.timestamp), hasSwing(before: sample.timestamp) else {
                continue
            }
            lastDetectionTimestamp = sample.timestamp
            detections.append(WatchAutoShotDetection(timestamp: sample.timestamp))
        }
        return detections
    }

    public mutating func reset() {
        rotationSamples.removeAll(keepingCapacity: true)
        lastDetectionTimestamp = nil
    }

    private func isImpact(_ sample: WatchAutoShotAccelerationSample) -> Bool {
        abs(sample.magnitude - 1.0) >= Self.impactDeviationFromGravity
    }

    private func outsideCooldown(_ timestamp: TimeInterval) -> Bool {
        guard let lastDetectionTimestamp else { return true }
        return timestamp - lastDetectionTimestamp >= Self.cooldownSeconds
    }

    private func hasSwing(before impactTimestamp: TimeInterval) -> Bool {
        let start = impactTimestamp - Self.swingLookbackSeconds
        let end = impactTimestamp - Self.minimumImpactDelaySeconds
        let window = rotationSamples.filter { $0.timestamp >= start && $0.timestamp <= end }
        guard window.contains(where: { abs($0.rotationAlongGravity) <= Self.quietRotationThreshold }) else {
            return false
        }
        let active = window.filter { abs($0.rotationAlongGravity) >= Self.activeRotationThreshold }
        return active.count >= Self.minimumActiveSamples
            && active.contains { abs($0.rotationAlongGravity) >= Self.peakRotationThreshold }
    }
}
