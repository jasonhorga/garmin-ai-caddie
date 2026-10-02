import Combine
import CoreMotion
import Foundation
import HealthKit
import os

public enum WatchAutoShotRuntimeState: Equatable {
    case unsupported
    case off
    case requestingAuthorization
    case starting
    case active
    case failed

    public var menuDetail: String {
        switch self {
        case .unsupported: return "本机不支持"
        case .off: return "关闭"
        case .requestingAuthorization: return "等待授权"
        case .starting: return "启动中"
        case .active: return "已开启"
        case .failed: return "不可用"
        }
    }
}

public struct WatchAutoShotSignal: Equatable, Identifiable {
    public let id: UUID
    public let motionTimestamp: TimeInterval

    public init(id: UUID = UUID(), motionTimestamp: TimeInterval) {
        self.id = id
        self.motionTimestamp = motionTimestamp
    }
}

/// B7 step 1: one settled swing-like motion with its features. `proposedShot` says whether the
/// AutoShot detector also proposed it.
public struct WatchSwingObservation: Equatable, Identifiable {
    public let id: UUID
    public let features: WatchSwingFeatures
    public let proposedShot: Bool
    /// The fresh, accurate ground speed used to classify it; nil when unknown.
    public let speedMps: Double?
    /// Wall-clock time the motion ended, from the sensor timestamps (not the batch delivery time);
    /// it decides the round and hole the candidate belongs to.
    public let observedAt: Date

    public init(
        id: UUID = UUID(),
        features: WatchSwingFeatures,
        proposedShot: Bool,
        speedMps: Double? = nil,
        observedAt: Date = Date()
    ) {
        self.id = id
        self.features = features
        self.proposedShot = proposedShot
        self.speedMps = speedMps
        self.observedAt = observedAt
    }
}

private enum WatchAutoShotProviderError: Error {
    case unsupported
    case authorizationFailed
}

/// Owns the one active golf workout session for a round. watchOS uses that session to keep wrist GPS
/// alive when the display sleeps; AutoShot optionally attaches batched motion streams to the same
/// session. This class never starts a workout builder, reads Health data, or calls finishWorkout, so it
/// does not save a workout to Apple Health. Motion batches stay in memory.
@MainActor
public final class WatchAutoShotProvider: NSObject, ObservableObject {
    @Published public private(set) var state: WatchAutoShotRuntimeState
    @Published public private(set) var latestSignal: WatchAutoShotSignal?
    /// B7 step 1: the latest settled swing candidate while collection is on.
    @Published public private(set) var latestSwing: WatchSwingObservation?

    private let healthStore: HKHealthStore
    private let sensorManager: CMBatchedSensorManager
    private let log = Logger(subsystem: "com.aicaddie.watch", category: "autoshot")
    private var detector = WatchAutoShotDetector()
    /// B7 step 1: candidate collection, speed and interruption state for the current motion run.
    private var swingSession = WatchSwingCollectionSession()
    private var autoShotWanted = false
    private var collectWanted = false
    /// A sensor interruption ends automatic detection and collection for the rest of the round;
    /// cleared only when the round ends (`stop`).
    private var motionInterrupted = false
    private var latestSpeed: WatchSwingSpeedSample?
    private var workoutSession: HKWorkoutSession?
    private var roundSessionDesired = false
    private var startingWorkoutSession = false
    /// Main-actor generation for an authorization/start attempt. Ending round A and immediately
    /// starting round B must make A's suspended authorization continuation inert when it resumes.
    private var workoutStartGeneration: UInt = 0
    private var desiredActive = false
    private var streamsActive = false

    public override convenience init() {
        self.init(healthStore: HKHealthStore(), sensorManager: CMBatchedSensorManager())
    }

    public init(healthStore: HKHealthStore, sensorManager: CMBatchedSensorManager) {
        self.healthStore = healthStore
        self.sensorManager = sensorManager
        self.state = Self.systemSupported ? .off : .unsupported
        super.init()
    }

    public var isSupported: Bool { Self.systemSupported }

    private static var systemSupported: Bool {
        HKHealthStore.isHealthDataAvailable()
            && CMBatchedSensorManager.isAccelerometerSupported
            && CMBatchedSensorManager.isDeviceMotionSupported
    }

    /// The latest Core Location speed for the riding filter.
    public func updateSpeed(_ fix: WatchLocationFix?) {
        guard let sample = fix.flatMap(WatchSwingSpeedSample.init(fix:)) else { return }
        latestSpeed = sample
        swingSession.updateSpeed(sample)
    }

    public func start() async {
        await reconcile(roundActive: true, autoShotEnabled: true)
    }

    /// B7 step 1: motion streams run while AutoShot or swing-candidate collection is on. Collection
    /// only records candidates and never proposes a shot.
    public func reconcile(roundActive: Bool, autoShotEnabled: Bool, collectSwingFeatures: Bool) async {
        autoShotWanted = autoShotEnabled
        collectWanted = collectSwingFeatures
        await reconcile(roundActive: roundActive, autoShotEnabled: autoShotEnabled || collectSwingFeatures)
    }

    /// A round always owns a golf workout session so Core Location remains eligible in the
    /// background. Motion streams are independently controlled by the player's AutoShot setting.
    public func reconcile(roundActive: Bool, autoShotEnabled: Bool) async {
        roundSessionDesired = roundActive
        desiredActive = roundActive && autoShotEnabled && !motionInterrupted
        guard roundActive else {
            stop()
            return
        }

        if desiredActive {
            if !isSupported
                || CMBatchedSensorManager.authorizationStatus == .denied
                || CMBatchedSensorManager.authorizationStatus == .restricted {
                state = .unsupported
                stopMotionStreams()
            }
        } else {
            stopMotionStreams()
            state = motionInterrupted ? .failed : (isSupported ? .off : .unsupported)
        }

        if let workoutSession {
            if workoutSession.state == .running {
                applyRunningWorkoutState()
            } else if desiredActive {
                state = .starting
            }
            return
        }
        guard !startingWorkoutSession, HKHealthStore.isHealthDataAvailable() else {
            if desiredActive, !HKHealthStore.isHealthDataAvailable() {
                state = .unsupported
            }
            return
        }

        workoutStartGeneration &+= 1
        let startGeneration = workoutStartGeneration
        startingWorkoutSession = true
        if desiredActive {
            state = .requestingAuthorization
        }
        do {
            try await requestWorkoutAuthorization()
            guard workoutStartGeneration == startGeneration,
                  startingWorkoutSession,
                  roundSessionDesired else { return }
            let configuration = HKWorkoutConfiguration()
            configuration.activityType = .golf
            configuration.locationType = .outdoor
            let session = try HKWorkoutSession(
                healthStore: healthStore,
                configuration: configuration
            )
            session.delegate = self
            workoutSession = session
            startingWorkoutSession = false
            state = desiredActive ? .starting : (isSupported ? .off : .unsupported)
            session.startActivity(with: Date())
        } catch {
            guard workoutStartGeneration == startGeneration else { return }
            startingWorkoutSession = false
            fail(error)
        }
    }

    public func stop() {
        workoutStartGeneration &+= 1
        roundSessionDesired = false
        desiredActive = false
        motionInterrupted = false
        startingWorkoutSession = false
        stopMotionStreams()
        let session = workoutSession
        workoutSession = nil
        session?.end()
        state = isSupported ? .off : .unsupported
    }

    private func requestWorkoutAuthorization() async throws {
        guard HKHealthStore.isHealthDataAvailable() else {
            throw WatchAutoShotProviderError.unsupported
        }
        let workoutTypes: Set<HKSampleType> = [HKObjectType.workoutType()]
        try await withCheckedThrowingContinuation {
            (continuation: CheckedContinuation<Void, Error>) in
            healthStore.requestAuthorization(toShare: workoutTypes, read: nil) { success, error in
                if let error {
                    continuation.resume(throwing: error)
                } else if success {
                    continuation.resume(returning: ())
                } else {
                    continuation.resume(throwing: WatchAutoShotProviderError.authorizationFailed)
                }
            }
        }
    }

    private func startMotionStreams() {
        guard desiredActive, !streamsActive else { return }
        streamsActive = true
        detector.reset()
        swingSession = WatchSwingCollectionSession()
        swingSession.updateSpeed(latestSpeed)

        sensorManager.startDeviceMotionUpdates { [weak self] batch, error in
            if let error {
                Task { @MainActor [weak self] in self?.handleMotionError(error) }
                return
            }
            // nil without an error is an interruption, not a quiet delivery.
            let samples = batch.map { items in
                items.map { item in
                    let rotation = item.rotationRate
                    let gravity = item.gravity
                    return WatchAutoShotRotationSample(
                        timestamp: item.timestamp,
                        rotationAlongGravity: rotation.x * gravity.x
                            + rotation.y * gravity.y
                            + rotation.z * gravity.z
                    )
                }
            }
            Task { @MainActor [weak self] in self?.handleRotation(samples) }
        }

        sensorManager.startAccelerometerUpdates { [weak self] batch, error in
            if let error {
                Task { @MainActor [weak self] in self?.handleMotionError(error) }
                return
            }
            let samples = batch.map { items in
                items.map { item in
                    WatchAutoShotAccelerationSample(
                        timestamp: item.timestamp,
                        x: item.acceleration.x,
                        y: item.acceleration.y,
                        z: item.acceleration.z
                    )
                }
            }
            Task { @MainActor [weak self] in self?.handleAcceleration(samples) }
        }
    }

    private func handleRotation(_ samples: [WatchAutoShotRotationSample]?) {
        guard desiredActive, streamsActive else { return }
        let observation = swingSession.rotationBatch(samples, now: Date(), collect: collectWanted)
        guard !swingSession.isInterrupted else { return interruptMotion() }
        if let samples, !samples.isEmpty {
            publish(detector.appendDeviceMotion(samples))
        }
        if collectWanted, let observation {
            latestSwing = observation
        }
    }

    private func handleAcceleration(_ samples: [WatchAutoShotAccelerationSample]?) {
        guard desiredActive, streamsActive else { return }
        swingSession.accelerationBatch(samples, collect: collectWanted)
        guard !swingSession.isInterrupted else { return interruptMotion() }
        if let samples, !samples.isEmpty {
            publish(detector.processAccelerometer(samples))
        }
    }

    /// The sensors stopped delivering: automatic detection and collection end for the rest of the
    /// round (manual recording continues), the workout session keeps GPS alive, and candidates already
    /// stored stay on the Watch.
    private func interruptMotion() {
        log.error("AutoShot motion stream interrupted; manual recording for the rest of the round")
        motionInterrupted = true
        desiredActive = false
        stopMotionStreams()
        state = .failed
    }

    private func stopMotionStreams() {
        if streamsActive {
            sensorManager.stopDeviceMotionUpdates()
            sensorManager.stopAccelerometerUpdates()
        }
        streamsActive = false
        detector.reset()
    }

    private func publish(_ detections: [WatchAutoShotDetection]) {
        for detection in detections {
            // Collection alone never proposes a shot; the detection still tags the candidate.
            guard swingSession.detection(at: detection.timestamp, autoShotWanted: autoShotWanted) else { continue }
            latestSignal = WatchAutoShotSignal(motionTimestamp: detection.timestamp)
        }
    }

    /// An explicit sensor error has the same fail-closed semantics as a nil delivery or a gap:
    /// no automatic detection or collection again until the round ends.
    private func handleMotionError(_ error: Error) {
        guard desiredActive else { return }
        motionInterrupted = true
        fail(error)
    }

    private func fail(_ error: Error) {
        log.error("AutoShot Beta unavailable: \(String(describing: error), privacy: .public)")
        stopMotionStreams()
        let session = workoutSession
        workoutSession = nil
        session?.end()
        state = desiredActive ? (isSupported ? .failed : .unsupported) : (isSupported ? .off : .unsupported)
    }

    private func applyRunningWorkoutState() {
        guard roundSessionDesired else {
            stop()
            return
        }
        if desiredActive, isSupported {
            state = .active
            startMotionStreams()
        } else {
            stopMotionStreams()
            state = motionInterrupted ? .failed : (isSupported ? .off : .unsupported)
        }
    }

    private func handleWorkoutState(_ newState: HKWorkoutSessionState) {
        switch newState {
        case .running:
            applyRunningWorkoutState()
        case .ended:
            stopMotionStreams()
            workoutSession = nil
            state = desiredActive ? (isSupported ? .failed : .unsupported) : (isSupported ? .off : .unsupported)
        default:
            break
        }
    }
}

extension WatchAutoShotProvider: HKWorkoutSessionDelegate {
    nonisolated public func workoutSession(
        _ workoutSession: HKWorkoutSession,
        didChangeTo toState: HKWorkoutSessionState,
        from fromState: HKWorkoutSessionState,
        date: Date
    ) {
        Task { @MainActor [weak self] in
            guard let self, self.workoutSession === workoutSession else { return }
            self.handleWorkoutState(toState)
        }
    }

    nonisolated public func workoutSession(
        _ workoutSession: HKWorkoutSession,
        didFailWithError error: Error
    ) {
        Task { @MainActor [weak self] in
            guard let self, self.workoutSession === workoutSession else { return }
            self.fail(error)
        }
    }
}
