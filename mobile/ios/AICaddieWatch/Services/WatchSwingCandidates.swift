import Foundation

/// B7 step 1 (IMPLEMENTATION_PLAN B7): every wrist motion that looks like a swing becomes a
/// candidate with a few derived features, so step 2 can label candidates against the round's
/// corrections. Candidates never change a score. Raw samples stay on the Watch; only these
/// features are kept and uploaded. Every threshold here is an assumed starting value (README §4)
/// that step 2's field data will set.
public enum WatchSwingKind: String, Codable, Equatable {
    case fullSwing
    case groundPracticeSwing
    case airSwing
    case putt
    /// Moving faster than walking (a cart ride): never a shot.
    case riding
    case unknown
}

public struct WatchSwingFeatures: Codable, Equatable {
    public let kind: WatchSwingKind
    /// How long the wrist was nearly still before the swing began.
    public let stillnessBeforeS: Double
    /// From the back-tracked swing start to the end of the rotation burst.
    public let swingDurationS: Double
    /// |rotation| integrated over the swing.
    public let cumulativeRotationRad: Double
    public let peakRotationRadS: Double
    /// Peak deviation from 1 g in the impact window; nil without an impact.
    public let impactPeakG: Double?
    /// How long the impact stayed above half its peak deviation; nil without an impact.
    public let impactDurationMs: Double?
}

/// Pure feature extraction and classification for one rotation burst.
public enum WatchSwingFeatureExtractor {
    /// Quieter than this is "still"; a burst starts above it.
    public static let quietRotation = 0.3
    /// Full and practice swings peak at or above this; putts stay between `quietRotation` and it.
    public static let swingPeakRotation = 3.0
    public static let puttPeakRotation = 2.0
    /// Deviation from 1 g that counts as touching the ground / ball.
    public static let impactDeviationG = 1.5
    public static let puttImpactDeviationG = 0.25
    /// A sharp impact (a ball) is shorter than this; a dull one (the ground) is longer.
    public static let sharpImpactMs = 15.0
    public static let ridingSpeedMps = 2.5

    public static func features(
        rotation: [WatchAutoShotRotationSample],
        acceleration: [WatchAutoShotAccelerationSample],
        speedMps: Double? = nil
    ) -> WatchSwingFeatures? {
        let samples = rotation.sorted { $0.timestamp < $1.timestamp }
        guard let peakIndex = samples.indices.max(by: {
            abs(samples[$0].rotationAlongGravity) < abs(samples[$1].rotationAlongGravity)
        }) else { return nil }
        let peak = abs(samples[peakIndex].rotationAlongGravity)
        guard peak > quietRotation else { return nil }
        // Back-track to where the motion rose out of stillness, and forward to where it settled.
        var start = peakIndex
        while start > 0, abs(samples[start - 1].rotationAlongGravity) > quietRotation { start -= 1 }
        var end = peakIndex
        while end < samples.count - 1, abs(samples[end + 1].rotationAlongGravity) > quietRotation { end += 1 }
        var stillStart = start
        while stillStart > 0, abs(samples[stillStart - 1].rotationAlongGravity) <= quietRotation { stillStart -= 1 }
        let stillness = samples[start].timestamp - samples[stillStart].timestamp
        var cumulative = 0.0
        if end > start {
            for index in (start + 1)...end {
                let dt = samples[index].timestamp - samples[index - 1].timestamp
                cumulative += abs(samples[index].rotationAlongGravity) * max(dt, 0)
            }
        }
        let swingStart = samples[start].timestamp
        let swingEnd = samples[end].timestamp
        let impact = impactFeatures(acceleration.filter { $0.timestamp >= swingStart && $0.timestamp <= swingEnd + 0.15 })
        let kind = classify(
            peakRotation: peak,
            stillness: stillness,
            impactPeakG: impact?.peak,
            impactDurationMs: impact?.durationMs,
            speedMps: speedMps
        )
        return WatchSwingFeatures(
            kind: kind,
            stillnessBeforeS: stillness,
            swingDurationS: swingEnd - swingStart,
            cumulativeRotationRad: cumulative,
            peakRotationRadS: peak,
            impactPeakG: impact?.peak,
            impactDurationMs: impact?.durationMs
        )
    }

    /// Peak deviation from 1 g and how long it stayed above half that peak.
    static func impactFeatures(_ samples: [WatchAutoShotAccelerationSample]) -> (peak: Double, durationMs: Double)? {
        let sorted = samples.sorted { $0.timestamp < $1.timestamp }
        func deviation(_ s: WatchAutoShotAccelerationSample) -> Double {
            abs((s.x * s.x + s.y * s.y + s.z * s.z).squareRoot() - 1)
        }
        guard let peakIndex = sorted.indices.max(by: { deviation(sorted[$0]) < deviation(sorted[$1]) }) else { return nil }
        let peak = deviation(sorted[peakIndex])
        guard peak >= puttImpactDeviationG else { return nil }
        let half = peak / 2
        var first = peakIndex, last = peakIndex
        while first > 0, deviation(sorted[first - 1]) >= half { first -= 1 }
        while last < sorted.count - 1, deviation(sorted[last + 1]) >= half { last += 1 }
        return (peak, (sorted[last].timestamp - sorted[first].timestamp) * 1000)
    }

    /// README §4's table, with its assumed thresholds.
    static func classify(
        peakRotation: Double,
        stillness: Double,
        impactPeakG: Double?,
        impactDurationMs: Double?,
        speedMps: Double?
    ) -> WatchSwingKind {
        if let speedMps, speedMps > ridingSpeedMps { return .riding }
        if peakRotation >= swingPeakRotation {
            guard let impactPeakG, impactPeakG >= impactDeviationG else { return .airSwing }
            if let impactDurationMs, impactDurationMs > sharpImpactMs { return .groundPracticeSwing }
            return .fullSwing
        }
        if peakRotation <= puttPeakRotation, stillness >= 1, let impactPeakG, impactPeakG < impactDeviationG {
            return .putt
        }
        return .unknown
    }
}

/// Buffers the batched motion streams and emits one feature set per rotation burst once it has
/// settled. Mutating and pure, so it is driven from fixtures in tests.
public struct WatchSwingCandidateCollector {
    /// The burst must stay quiet this long before it is closed.
    static let settleSeconds = 0.4
    /// Keep enough history for the stillness before a swing and the swing itself.
    static let historySeconds = 6.0

    private var rotation: [WatchAutoShotRotationSample] = []
    private var acceleration: [WatchAutoShotAccelerationSample] = []
    /// Bursts ending at or before this were already emitted.
    private var emittedThrough: TimeInterval = -.infinity

    public init() {}

    public mutating func appendAcceleration(_ samples: [WatchAutoShotAccelerationSample]) {
        acceleration.append(contentsOf: samples)
        trim()
    }

    /// Appends a rotation batch; returns the burst that has settled, if any.
    public mutating func appendRotation(_ samples: [WatchAutoShotRotationSample]) -> WatchSwingFeatures? {
        rotation.append(contentsOf: samples)
        rotation.sort { $0.timestamp < $1.timestamp }
        defer { trim() }
        guard let latest = rotation.last?.timestamp else { return nil }
        let active = rotation.filter {
            $0.timestamp > emittedThrough && abs($0.rotationAlongGravity) > WatchSwingFeatureExtractor.quietRotation
        }
        guard let lastActive = active.last?.timestamp, latest - lastActive >= Self.settleSeconds else { return nil }
        // The quiet samples before the burst stay in the window: they are its stillness.
        let window = rotation.filter { $0.timestamp > emittedThrough && $0.timestamp <= lastActive }
        emittedThrough = lastActive
        return WatchSwingFeatureExtractor.features(rotation: window, acceleration: acceleration)
    }

    public mutating func reset() {
        rotation.removeAll()
        acceleration.removeAll()
        emittedThrough = -.infinity
    }

    private mutating func trim() {
        let latest = max(rotation.last?.timestamp ?? -.infinity, acceleration.last?.timestamp ?? -.infinity)
        guard latest.isFinite else { return }
        let oldest = latest - Self.historySeconds
        rotation.removeAll { $0.timestamp < oldest }
        acceleration.removeAll { $0.timestamp < oldest }
    }
}

/// One stored candidate: when, which hole, the features and the GPS quality at the time.
public struct WatchSwingCandidateRecord: Codable, Equatable, Identifiable {
    public let id: String
    public let capturedAt: String
    public let hole: Int
    public let features: WatchSwingFeatures
    public let horizontalAccuracyM: Double?
    public let speedMps: Double?
    /// The existing AutoShot detector also proposed this motion as a shot.
    public let proposedShot: Bool

    public init(id: String = UUID().uuidString, capturedAt: String, hole: Int, features: WatchSwingFeatures,
                horizontalAccuracyM: Double?, speedMps: Double?, proposedShot: Bool) {
        self.id = id
        self.capturedAt = capturedAt
        self.hole = hole
        self.features = features
        self.horizontalAccuracyM = horizontalAccuracyM
        self.speedMps = speedMps
        self.proposedShot = proposedShot
    }
}

/// Per-round candidate files, separate from the round store: nothing here is a round event.
public struct WatchSwingCandidateStore {
    public let directoryURL: URL

    public init(directoryURL: URL? = nil) {
        self.directoryURL = directoryURL ?? FileManager.default
            .urls(for: .applicationSupportDirectory, in: .userDomainMask)[0]
            .appendingPathComponent("SwingCandidates", isDirectory: true)
    }

    private func fileURL(_ roundId: String) -> URL {
        let safe = roundId.map { $0.isLetter || $0.isNumber || $0 == "-" ? $0 : "_" }
        return directoryURL.appendingPathComponent(String(safe) + ".json")
    }

    public func load(roundId: String) -> [WatchSwingCandidateRecord] {
        guard let data = try? Data(contentsOf: fileURL(roundId)),
              let records = try? JSONDecoder().decode([WatchSwingCandidateRecord].self, from: data) else { return [] }
        return records
    }

    public func append(_ record: WatchSwingCandidateRecord, roundId: String) {
        var records = load(roundId: roundId)
        guard records.count < 600 else { return }
        records.append(record)
        try? FileManager.default.createDirectory(at: directoryURL, withIntermediateDirectories: true)
        if let data = try? JSONEncoder().encode(records) {
            try? data.write(to: fileURL(roundId), options: .atomic)
        }
    }

    public func remove(roundId: String) {
        try? FileManager.default.removeItem(at: fileURL(roundId))
    }

    public func pendingRoundIds() -> [String] {
        let files = (try? FileManager.default.contentsOfDirectory(at: directoryURL, includingPropertiesForKeys: nil)) ?? []
        return files.filter { $0.pathExtension == "json" }.map { $0.deletingPathExtension().lastPathComponent }
    }
}
