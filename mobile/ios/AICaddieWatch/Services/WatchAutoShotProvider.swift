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

private enum WatchAutoShotProviderError: Error {
    case unsupported
    case authorizationFailed
}

/// Thin system adapter around the pure detector. The active HealthKit workout exists only because Apple
/// requires one for CMBatchedSensorManager; this class never starts a workout builder, reads Health data,
/// or calls finishWorkout, so it does not save a workout to Apple Health. Motion batches stay in memory.
@MainActor
public final class WatchAutoShotProvider: NSObject, ObservableObject {
    @Published public private(set) var state: WatchAutoShotRuntimeState
    @Published public private(set) var latestSignal: WatchAutoShotSignal?

    private let healthStore: HKHealthStore
    private let sensorManager: CMBatchedSensorManager
    private let log = Logger(subsystem: "com.aicaddie.watch", category: "autoshot")
    private var detector = WatchAutoShotDetector()
    private var workoutSession: HKWorkoutSession?
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

    public func start() async {
        desiredActive = true
        guard isSupported else {
            state = .unsupported
            return
        }
        guard state != .requestingAuthorization, state != .starting, state != .active else {
            return
        }
        guard CMBatchedSensorManager.authorizationStatus != .denied,
              CMBatchedSensorManager.authorizationStatus != .restricted else {
            fail(WatchAutoShotProviderError.authorizationFailed)
            return
        }

        state = .requestingAuthorization
        do {
            try await requestWorkoutAuthorization()
            guard desiredActive else {
                state = .off
                return
            }
            let configuration = HKWorkoutConfiguration()
            configuration.activityType = .golf
            configuration.locationType = .outdoor
            let session = try HKWorkoutSession(
                healthStore: healthStore,
                configuration: configuration
            )
            session.delegate = self
            workoutSession = session
            state = .starting
            session.startActivity(with: Date())
        } catch {
            fail(error)
        }
    }

    public func stop() {
        desiredActive = false
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

        sensorManager.startDeviceMotionUpdates { [weak self] batch, error in
            if let error {
                Task { @MainActor [weak self] in self?.handleMotionError(error) }
                return
            }
            let samples = (batch ?? []).map { item in
                let rotation = item.rotationRate
                let gravity = item.gravity
                return WatchAutoShotRotationSample(
                    timestamp: item.timestamp,
                    rotationAlongGravity: rotation.x * gravity.x
                        + rotation.y * gravity.y
                        + rotation.z * gravity.z
                )
            }
            guard !samples.isEmpty else { return }
            Task { @MainActor [weak self] in
                guard let self, self.desiredActive else { return }
                self.publish(self.detector.appendDeviceMotion(samples))
            }
        }

        sensorManager.startAccelerometerUpdates { [weak self] batch, error in
            if let error {
                Task { @MainActor [weak self] in self?.handleMotionError(error) }
                return
            }
            let samples = (batch ?? []).map { item in
                WatchAutoShotAccelerationSample(
                    timestamp: item.timestamp,
                    x: item.acceleration.x,
                    y: item.acceleration.y,
                    z: item.acceleration.z
                )
            }
            guard !samples.isEmpty else { return }
            Task { @MainActor [weak self] in
                guard let self, self.desiredActive else { return }
                self.publish(self.detector.processAccelerometer(samples))
            }
        }
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
            latestSignal = WatchAutoShotSignal(motionTimestamp: detection.timestamp)
        }
    }

    private func handleMotionError(_ error: Error) {
        guard desiredActive else { return }
        fail(error)
    }

    private func fail(_ error: Error) {
        log.error("AutoShot Beta unavailable: \(String(describing: error), privacy: .public)")
        stopMotionStreams()
        let session = workoutSession
        workoutSession = nil
        session?.end()
        state = isSupported ? .failed : .unsupported
    }

    private func handleWorkoutState(_ newState: HKWorkoutSessionState) {
        switch newState {
        case .running:
            guard desiredActive else {
                stop()
                return
            }
            state = .active
            startMotionStreams()
        case .ended:
            stopMotionStreams()
            workoutSession = nil
            state = desiredActive ? .failed : .off
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
        Task { @MainActor [weak self] in self?.handleWorkoutState(toState) }
    }

    nonisolated public func workoutSession(
        _ workoutSession: HKWorkoutSession,
        didFailWithError error: Error
    ) {
        Task { @MainActor [weak self] in self?.fail(error) }
    }
}
