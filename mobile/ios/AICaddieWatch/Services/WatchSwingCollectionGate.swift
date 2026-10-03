import Foundation
import SwiftUI

/// B7 capability and battery gate (IMPLEMENTATION_PLAN B7: "能力 / 电量门槛"). Swing-candidate
/// collection runs only while every check holds; any failure turns it off for the rest of the round
/// and recording stays manual. Pure, so the production decisions are driven from tests.
///
/// - Capability: batched motion sensors and Health must exist, motion permission must not be denied
///   or restricted, and the round's golf workout session must not have failed to start or run.
/// - Battery: the round's drain while collecting may exceed the measured drain of an ordinary
///   (non-collecting) round by at most `extraDrainPerHour` (5 % per hour). The baseline comes from
///   the player's own recent non-collecting rounds; without one, collection stays off (fail closed).
public enum WatchSwingGateBlocker: String, Codable, Equatable {
    case unsupportedDevice
    case motionPermissionDenied
    case workoutSessionFailed
    case noBatteryBaseline
    case batteryOverBudget
}

/// What the gate needs to know about the device right now.
public struct WatchSwingCapability: Equatable {
    public let sensorsSupported: Bool
    public let motionPermissionDenied: Bool
    public let workoutFailed: Bool

    public init(sensorsSupported: Bool, motionPermissionDenied: Bool, workoutFailed: Bool) {
        self.sensorsSupported = sensorsSupported
        self.motionPermissionDenied = motionPermissionDenied
        self.workoutFailed = workoutFailed
    }

    /// From the AutoShot provider: its state already folds in sensor support, Health availability
    /// and the workout session. Starting/authorizing is not a failure (the gate must not flap while
    /// the session it asked for comes up); `.failed` is a session that would not start or a sensor
    /// interruption.
    public init(provider state: WatchAutoShotRuntimeState, sensorsSupported: Bool, motionPermissionDenied: Bool) {
        self.init(
            sensorsSupported: sensorsSupported && state != .unsupported,
            motionPermissionDenied: motionPermissionDenied,
            workoutFailed: state == .failed
        )
    }
}

/// One battery reading. `level` is 0...1; readings while charging never count as drain.
public struct WatchBatterySample: Codable, Equatable {
    public let at: Date
    public let level: Double
    public let charging: Bool

    public init(at: Date, level: Double, charging: Bool) {
        self.at = at
        self.level = level
        self.charging = charging
    }
}

public enum WatchBatteryBudget {
    /// The plan's budget: at most 5 % per hour more than an ordinary round.
    public static let extraDrainPerHour = 0.05
    /// Drain is judged only over at least this much uncharged time, so one coarse battery step
    /// (watchOS reports whole percent) cannot trip the budget.
    public static let minimumWindowS: TimeInterval = 20 * 60

    /// Fraction of battery per hour over the uncharged stretches of `samples`; nil until they cover
    /// `minimumWindowS`.
    public static func drainPerHour(_ samples: [WatchBatterySample]) -> Double? {
        let sorted = samples.sorted { $0.at < $1.at }
        var drained = 0.0
        var seconds = 0.0
        for (earlier, later) in zip(sorted, sorted.dropFirst())
        where !earlier.charging && !later.charging && later.level <= earlier.level + 0.001 {
            let dt = later.at.timeIntervalSince(earlier.at)
            guard dt > 0 else { continue }
            drained += earlier.level - later.level
            seconds += dt
        }
        guard seconds >= minimumWindowS else { return nil }
        return drained / (seconds / 3600)
    }

    public static func isOverBudget(drainPerHour: Double, baselinePerHour: Double) -> Bool {
        drainPerHour > baselinePerHour + extraDrainPerHour
    }
}

/// One round's battery record: the gate's evidence and, for non-collecting rounds, the baseline.
public struct WatchRoundBatteryReport: Codable, Equatable {
    public let roundId: String
    public let collecting: Bool
    public let startedAt: Date
    public let endedAt: Date
    public let drainPerHour: Double?
    public let disabledReason: WatchSwingGateBlocker?

    public init(roundId: String, collecting: Bool, startedAt: Date, endedAt: Date,
                drainPerHour: Double?, disabledReason: WatchSwingGateBlocker?) {
        self.roundId = roundId
        self.collecting = collecting
        self.startedAt = startedAt
        self.endedAt = endedAt
        self.drainPerHour = drainPerHour
        self.disabledReason = disabledReason
    }
}

/// Recent round battery reports on the Watch. The baseline is the median drain of the last
/// `baselineRounds` non-collecting rounds that measured one.
public struct WatchRoundBatteryReportStore {
    public static let retainedReports = 20
    public static let baselineRounds = 5
    public let fileURL: URL

    public init(fileURL: URL? = nil) {
        self.fileURL = fileURL ?? FileManager.default
            .urls(for: .applicationSupportDirectory, in: .userDomainMask)[0]
            .appendingPathComponent("SwingCandidates", isDirectory: true)
            .appendingPathComponent("battery-reports.json")
    }

    public func load() -> [WatchRoundBatteryReport] {
        guard let data = try? Data(contentsOf: fileURL) else { return [] }
        let decoder = JSONDecoder()
        decoder.dateDecodingStrategy = .iso8601
        return (try? decoder.decode([WatchRoundBatteryReport].self, from: data)) ?? []
    }

    public func append(_ report: WatchRoundBatteryReport) {
        var reports = load().filter { $0.roundId != report.roundId }
        reports.append(report)
        reports = Array(reports.suffix(Self.retainedReports))
        let encoder = JSONEncoder()
        encoder.dateEncodingStrategy = .iso8601
        try? FileManager.default.createDirectory(
            at: fileURL.deletingLastPathComponent(), withIntermediateDirectories: true
        )
        if let data = try? encoder.encode(reports) {
            try? data.write(to: fileURL, options: .atomic)
        }
    }

    public func baselinePerHour() -> Double? {
        let rates = load().filter { !$0.collecting }.compactMap(\.drainPerHour).suffix(Self.baselineRounds).sorted()
        guard !rates.isEmpty else { return nil }
        let mid = rates.count / 2
        return rates.count % 2 == 1 ? rates[rates.startIndex + mid]
            : (rates[rates.startIndex + mid - 1] + rates[rates.startIndex + mid]) / 2
    }
}

/// One round's gate. Every failure is latched for the rest of the round; recording stays manual.
public struct WatchSwingCollectionGate {
    public let roundId: String
    public let startedAt: Date
    public let baselinePerHour: Double?
    public private(set) var samples: [WatchBatterySample] = []
    public private(set) var latchedBlocker: WatchSwingGateBlocker?
    /// Whether this round ever collected (for the report).
    public private(set) var collected = false

    public init(roundId: String, startedAt: Date, baselinePerHour: Double?) {
        self.roundId = roundId
        self.startedAt = startedAt
        self.baselinePerHour = baselinePerHour
    }

    public mutating func record(_ sample: WatchBatterySample) {
        guard (0...1).contains(sample.level) else { return }
        samples.append(sample)
    }

    /// Whether collection may run now, given the player's preference and the device's capability.
    public mutating func allowsCollection(preference: Bool, capability: WatchSwingCapability) -> Bool {
        guard preference else { return false }
        if let blocker = blocker(capability: capability) {
            latchedBlocker = blocker
            return false
        }
        collected = true
        return true
    }

    /// The reason collection is off now, if any.
    public func blocker(capability: WatchSwingCapability) -> WatchSwingGateBlocker? {
        if let latchedBlocker { return latchedBlocker }
        if !capability.sensorsSupported { return .unsupportedDevice }
        if capability.motionPermissionDenied { return .motionPermissionDenied }
        guard let baselinePerHour else { return .noBatteryBaseline }
        if collected, let drain = WatchBatteryBudget.drainPerHour(samples),
           WatchBatteryBudget.isOverBudget(drainPerHour: drain, baselinePerHour: baselinePerHour) {
            return .batteryOverBudget
        }
        if capability.workoutFailed { return .workoutSessionFailed }
        return nil
    }

    public func report(endedAt: Date) -> WatchRoundBatteryReport {
        WatchRoundBatteryReport(
            roundId: roundId,
            collecting: collected,
            startedAt: startedAt,
            endedAt: endedAt,
            drainPerHour: WatchBatteryBudget.drainPerHour(samples),
            disabledReason: latchedBlocker
        )
    }
}

/// The settings row's status line for the collection switch.
public enum WatchSwingCollectionStatus {
    public static func text(preference: Bool, roundActive: Bool, blocker: WatchSwingGateBlocker?) -> String {
        guard preference else { return "关闭 · 实验，只记录挥杆特征，不改成绩" }
        switch blocker {
        case .unsupportedDevice: return "本机不支持"
        case .motionPermissionDenied: return "未授权运动数据，不采集"
        case .workoutSessionFailed: return "锻炼会话不可用，本场不采集"
        case .noBatteryBaseline: return "先打一场不采集的球，测出耗电基准"
        case .batteryOverBudget: return "本场耗电超出预算，已停止采集"
        case nil: return roundActive ? "采集中" : "下一场开始后采集"
        }
    }
}

private struct WatchSwingCollectionStatusKey: EnvironmentKey {
    static let defaultValue: String? = nil
}

extension EnvironmentValues {
    /// The collection row's status; nil (the default) hides the row.
    public var watchSwingCollectionStatus: String? {
        get { self[WatchSwingCollectionStatusKey.self] }
        set { self[WatchSwingCollectionStatusKey.self] = newValue }
    }
}
