import CryptoKit
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
    /// Batches can arrive out of order: a burst is closed only once the burst and its settle tail are
    /// contiguous (no hole longer than this), so a later batch never closes a burst missing its middle.
    static let maximumSampleGapSeconds = 0.1

    private var rotation: [WatchAutoShotRotationSample] = []
    private var acceleration: [WatchAutoShotAccelerationSample] = []
    /// Bursts ending at or before this were already emitted.
    private var emittedThrough: TimeInterval = -.infinity
    /// Sensor timestamp of the last active sample of the burst most recently emitted: when the
    /// swing itself ended, not when its quiet settle tail was delivered.
    public private(set) var lastBurstEnd: TimeInterval?

    public init() {}

    public mutating func appendAcceleration(_ samples: [WatchAutoShotAccelerationSample]) {
        acceleration.append(contentsOf: samples)
        trim()
    }

    /// Appends a rotation batch; returns the burst that has settled, if any. `speedMps` is the
    /// current fresh, accurate ground speed, or nil when unknown (then the burst can never be
    /// classified `.riding`).
    public mutating func appendRotation(
        _ samples: [WatchAutoShotRotationSample],
        speedMps: Double? = nil
    ) -> WatchSwingFeatures? {
        rotation.append(contentsOf: samples)
        rotation.sort { $0.timestamp < $1.timestamp }
        defer { trim() }
        guard let latest = rotation.last?.timestamp else { return nil }
        let active = rotation.filter {
            $0.timestamp > emittedThrough && abs($0.rotationAlongGravity) > WatchSwingFeatureExtractor.quietRotation
        }
        guard let lastActive = active.last?.timestamp, latest - lastActive >= Self.settleSeconds else { return nil }
        // The burst, the sample before it and its settle tail must be contiguous.
        let firstActive = active.first?.timestamp ?? lastActive
        let lead = rotation.last { $0.timestamp < firstActive }?.timestamp ?? firstActive
        let burst = rotation.filter { $0.timestamp >= lead && $0.timestamp <= lastActive + Self.settleSeconds }
        for (earlier, later) in zip(burst, burst.dropFirst())
        where later.timestamp - earlier.timestamp > Self.maximumSampleGapSeconds {
            return nil
        }
        // The quiet samples before the burst stay in the window: they are its stillness.
        let window = rotation.filter { $0.timestamp > emittedThrough && $0.timestamp <= lastActive }
        emittedThrough = lastActive
        lastBurstEnd = lastActive
        return WatchSwingFeatureExtractor.features(rotation: window, acceleration: acceleration, speedMps: speedMps)
    }

    public mutating func reset() {
        rotation.removeAll()
        acceleration.removeAll()
        emittedThrough = -.infinity
        lastBurstEnd = nil
    }

    private mutating func trim() {
        // Batches can arrive out of order, so trim from the newest sample seen, not the last appended.
        let latest = max(
            rotation.map(\.timestamp).max() ?? -.infinity,
            acceleration.map(\.timestamp).max() ?? -.infinity
        )
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

/// Per-round candidate files, separate from the round store: nothing here is a round event. Each
/// file is named by a digest of the round ID and carries the original ID inside, so distinct IDs
/// never share a file and uploads always target the round that recorded them.
public struct WatchSwingCandidateStore {
    public static let maximumCandidatesPerRound = 600
    public let directoryURL: URL

    private struct RoundFile: Codable {
        let roundId: String
        var candidates: [WatchSwingCandidateRecord]
    }

    public init(directoryURL: URL? = nil) {
        self.directoryURL = directoryURL ?? FileManager.default
            .urls(for: .applicationSupportDirectory, in: .userDomainMask)[0]
            .appendingPathComponent("SwingCandidates", isDirectory: true)
    }

    static func fileName(for roundId: String) -> String {
        SHA256.hash(data: Data(roundId.utf8)).map { String(format: "%02x", $0) }.joined() + ".json"
    }

    private func fileURL(_ roundId: String) -> URL {
        directoryURL.appendingPathComponent(Self.fileName(for: roundId))
    }

    private func read(_ url: URL) -> RoundFile? {
        guard let data = try? Data(contentsOf: url) else { return nil }
        return try? JSONDecoder().decode(RoundFile.self, from: data)
    }

    public func load(roundId: String) -> [WatchSwingCandidateRecord] {
        guard let file = read(fileURL(roundId)), file.roundId == roundId else { return [] }
        return file.candidates
    }

    public func append(_ record: WatchSwingCandidateRecord, roundId: String) {
        var file = read(fileURL(roundId)).flatMap { $0.roundId == roundId ? $0 : nil }
            ?? RoundFile(roundId: roundId, candidates: [])
        guard file.candidates.count < Self.maximumCandidatesPerRound else { return }
        file.candidates.append(record)
        try? FileManager.default.createDirectory(at: directoryURL, withIntermediateDirectories: true)
        if let data = try? JSONEncoder().encode(file) {
            try? data.write(to: fileURL(roundId), options: .atomic)
        }
    }

    public func remove(roundId: String) {
        try? FileManager.default.removeItem(at: fileURL(roundId))
    }

    /// The original IDs of every round with stored candidates.
    public func pendingRoundIds() -> [String] {
        let files = (try? FileManager.default.contentsOfDirectory(at: directoryURL, includingPropertiesForKeys: nil)) ?? []
        return files.filter { $0.pathExtension == "json" }.compactMap { read($0)?.roundId }.sorted()
    }
}

/// B7's capability and battery gate (IMPLEMENTATION_PLAN B7: runtime capability, permission,
/// workout-session and per-round battery-budget checks with automatic shutdown) is a separate
/// prerequisite. Until it lands, collection stays unavailable: the settings row is hidden and a
/// stored preference is ignored.
public enum WatchSwingCollectionAvailability {
    public static let isAvailable = false

    public static func isCollecting(preference: Bool) -> Bool {
        isAvailable && preference
    }
}

/// A Core Location ground-speed reading for the riding filter.
public struct WatchSwingSpeedSample: Equatable {
    public let speedMps: Double
    public let accuracyMps: Double
    public let capturedAt: Date

    public init(speedMps: Double, accuracyMps: Double, capturedAt: Date) {
        self.speedMps = speedMps
        self.accuracyMps = accuracyMps
        self.capturedAt = capturedAt
    }

    public init?(fix: WatchLocationFix) {
        guard let speed = fix.speedMps, let accuracy = fix.speedAccuracyMps,
              let capturedAt = ISO8601DateFormatter().date(from: fix.capturedAt) else { return nil }
        self.init(speedMps: speed, accuracyMps: accuracy, capturedAt: capturedAt)
    }
}

/// The motion side of one round's collection, driven by `WatchAutoShotProvider` with every sensor
/// batch, detection and speed reading. Pure, so tests drive the exact production decisions.
///
/// - Speed: a reading is used only while fresh (`maximumSpeedAgeS`) and accurate
///   (`maximumSpeedAccuracyMps`); otherwise speed is unknown. Unknown speed fails closed for the
///   riding filter: the candidate is recorded with `speedMps == nil`, is never `.riding`, and step 2
///   must not count it as either a cart ride or a confirmed walk.
/// - Interruption: a delivery without data (`nil`) or a gap longer than `maximumBatchGapS` between
///   batches is an interruption. Collection and automatic detection stop for the rest of the round;
///   candidates already stored are kept. An empty batch is a normal quiet delivery.
public struct WatchSwingCollectionSession {
    public static let maximumSpeedAgeS: TimeInterval = 10
    public static let maximumSpeedAccuracyMps = 2.0
    public static let maximumBatchGapS: TimeInterval = 10
    /// A detection this close to a candidate's end tags it `proposedShot`.
    public static let proposalWindowS: TimeInterval = 3

    public private(set) var isInterrupted = false
    private var collector = WatchSwingCandidateCollector()
    private var speed: WatchSwingSpeedSample?
    private var newestMotionTimestamp: TimeInterval?
    private var lastDetectionTimestamp: TimeInterval?

    public init() {}

    public mutating func updateSpeed(_ sample: WatchSwingSpeedSample?) {
        guard let sample else { return }
        if let speed, speed.capturedAt > sample.capturedAt { return }
        speed = sample
    }

    public func usableSpeedMps(now: Date) -> Double? {
        guard let speed,
              speed.speedMps >= 0, speed.accuracyMps >= 0,
              speed.accuracyMps <= Self.maximumSpeedAccuracyMps,
              now.timeIntervalSince(speed.capturedAt) >= 0,
              now.timeIntervalSince(speed.capturedAt) <= Self.maximumSpeedAgeS else { return nil }
        return speed.speedMps
    }

    /// Whether an AutoShot detection may become a shot signal: only when AutoShot itself is on.
    /// Collection alone never proposes a shot. The detection still tags the matching candidate.
    public mutating func detection(at timestamp: TimeInterval, autoShotWanted: Bool) -> Bool {
        lastDetectionTimestamp = timestamp
        return autoShotWanted && !isInterrupted
    }

    /// One device-motion delivery. Returns the candidate whose burst settled, if any.
    /// Every delivery goes through here, also while only AutoShot runs, so an interruption ends
    /// automatic detection too; `collect` says whether candidates are recorded.
    /// `uptime` is the clock the sample timestamps use (seconds since boot), so the motion's wall
    /// time is `now - (uptime - timestamp)`.
    public mutating func rotationBatch(
        _ samples: [WatchAutoShotRotationSample]?,
        now: Date,
        uptime: TimeInterval = ProcessInfo.processInfo.systemUptime,
        collect: Bool = true
    ) -> WatchSwingObservation? {
        guard !isInterrupted else { return nil }
        guard let samples else { interrupt(); return nil }
        guard !samples.isEmpty else { return nil }
        guard acceptMotion(samples.map(\.timestamp)), collect else { return nil }
        let speedMps = usableSpeedMps(now: now)
        guard let features = collector.appendRotation(samples, speedMps: speedMps) else { return nil }
        // The swing's own end (its last active sample), not the settle tail that closed it: a swing
        // that ended before a round closed belongs to that round even if the tail arrives after.
        let swingEnd = collector.lastBurstEnd ?? samples.map(\.timestamp).max() ?? 0
        let proposed = lastDetectionTimestamp.map { abs(swingEnd - $0) <= Self.proposalWindowS } ?? false
        let motionEndedAt = now.addingTimeInterval(min(0, swingEnd - uptime))
        return WatchSwingObservation(
            features: features, proposedShot: proposed, speedMps: speedMps, observedAt: motionEndedAt
        )
    }

    /// One accelerometer delivery.
    public mutating func accelerationBatch(_ samples: [WatchAutoShotAccelerationSample]?, collect: Bool = true) {
        guard !isInterrupted else { return }
        guard let samples else { interrupt(); return }
        guard !samples.isEmpty, acceptMotion(samples.map(\.timestamp)), collect else { return }
        collector.appendAcceleration(samples)
    }

    public mutating func interrupt() {
        isInterrupted = true
        collector.reset()
    }

    /// A batch whose oldest sample starts more than `maximumBatchGapS` after everything seen so far
    /// means the stream stopped for a while: an interruption. Older (out-of-order) batches are fine.
    private mutating func acceptMotion(_ timestamps: [TimeInterval]) -> Bool {
        guard let oldest = timestamps.min(), let newest = timestamps.max() else { return true }
        if let seen = newestMotionTimestamp, oldest - seen > Self.maximumBatchGapS {
            interrupt()
            return false
        }
        newestMotionTimestamp = max(newestMotionTimestamp ?? newest, newest)
        return true
    }
}

/// Which round and hole a candidate belongs to, decided by when its motion happened (not when its
/// batch was delivered). Each round is a span from its start to its closure with the holes played in
/// it, so a candidate whose motion happened in round A stays on A even if it is delivered after A
/// closed and round B started, and carries the hole A was on at that moment.
public struct WatchSwingCandidateRouter {
    /// Closed rounds kept for late deliveries.
    public static let retainedClosedRounds = 4

    public struct Assignment: Equatable {
        public let roundId: String
        public let hole: Int
    }

    private struct Span {
        let roundId: String
        let startedAt: Date
        var endedAt: Date?
        var holes: [(at: Date, hole: Int)] = []

        func contains(_ date: Date) -> Bool {
            date >= startedAt && endedAt.map { date < $0 } ?? true
        }

        func hole(at date: Date) -> Int? {
            let valid = holes.filter { (1...36).contains($0.hole) }
            return (valid.last { $0.at <= date } ?? valid.first)?.hole
        }
    }

    private var spans: [Span] = []

    public init() {}

    public var activeRoundId: String? {
        spans.last.flatMap { $0.endedAt == nil ? $0.roundId : nil }
    }

    /// Returns the round that just closed, if the change closed one.
    @discardableResult
    public mutating func roundChanged(to roundId: String?, at date: Date) -> String? {
        guard roundId != activeRoundId else { return nil }
        var closed: String?
        if let last = spans.indices.last, spans[last].endedAt == nil {
            spans[last].endedAt = date
            closed = spans[last].roundId
        }
        if let roundId {
            spans.append(Span(roundId: roundId, startedAt: date))
        }
        let closedSpans = spans.filter { $0.endedAt != nil }
        if closedSpans.count > Self.retainedClosedRounds {
            let drop = closedSpans.count - Self.retainedClosedRounds
            var dropped = 0
            spans.removeAll { span in
                guard span.endedAt != nil, dropped < drop else { return false }
                dropped += 1
                return true
            }
        }
        return closed
    }

    /// The active round moved to `hole` (1-36; other values are ignored).
    public mutating func holeChanged(to hole: Int, at date: Date) {
        guard let last = spans.indices.last, spans[last].endedAt == nil, (1...36).contains(hole) else { return }
        if spans[last].holes.last?.hole != hole {
            spans[last].holes.append((date, hole))
        }
    }

    /// The round and hole in play when the motion ended; nil outside every known round or without
    /// a valid hole (never an invalid candidate).
    public func assignment(forMotionAt date: Date) -> Assignment? {
        guard let span = spans.last(where: { $0.contains(date) }), let hole = span.hole(at: date) else { return nil }
        return Assignment(roundId: span.roundId, hole: hole)
    }
}

/// Uploads the candidates of every round that is no longer active. A successful upload removes the
/// round's file; a failed one keeps it for the next attempt (config, reachability, closure, launch or
/// the retry backoff).
public struct WatchSwingCandidateUploader {
    public let store: WatchSwingCandidateStore
    /// Retry delays after a failed attempt while the app stays alive.
    public static let retryDelaysS: [TimeInterval] = [60, 300, 900]

    public init(store: WatchSwingCandidateStore) {
        self.store = store
    }

    public struct Outcome: Equatable {
        public var uploaded: [String] = []
        public var failed: [String] = []
    }

    public func uploadClosedRounds(
        activeRoundId: String?,
        upload: (String, [WatchSwingCandidateRecord]) async throws -> Void
    ) async -> Outcome {
        var outcome = Outcome()
        for roundId in store.pendingRoundIds() where roundId != activeRoundId {
            let candidates = store.load(roundId: roundId)
            guard !candidates.isEmpty else {
                store.remove(roundId: roundId)
                continue
            }
            do {
                try await upload(roundId, candidates)
                // Only what was sent is removed: a candidate appended during the upload stays.
                let remaining = store.load(roundId: roundId).filter { record in
                    !candidates.contains { $0.id == record.id }
                }
                store.remove(roundId: roundId)
                for record in remaining { store.append(record, roundId: roundId) }
                outcome.uploaded.append(roundId)
            } catch {
                outcome.failed.append(roundId)
            }
        }
        return outcome
    }
}
