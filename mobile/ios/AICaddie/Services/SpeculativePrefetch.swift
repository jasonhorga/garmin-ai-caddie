import Foundation
import Network

/// What the phone's current network lets a "可能会打" (speculative) course download do. The player
/// asked for neither the course nor the data, so it waits for Wi-Fi by default and never runs in
/// Low Data Mode. Downloads the player asked for (备战) and the course about to be played (intent
/// prefetch) ignore this and use any network.
public struct SpeculativeNetworkState: Equatable, Sendable {
    public var isSatisfied: Bool
    /// Cellular or a personal hotspot (`NWPath.isExpensive`).
    public var isExpensive: Bool
    /// Low Data Mode (`NWPath.isConstrained`).
    public var isConstrained: Bool

    public init(isSatisfied: Bool, isExpensive: Bool, isConstrained: Bool) {
        self.isSatisfied = isSatisfied
        self.isExpensive = isExpensive
        self.isConstrained = isConstrained
    }

    /// Before the first path update nothing speculative runs.
    public static let unknown = SpeculativeNetworkState(isSatisfied: false, isExpensive: true, isConstrained: true)

    public func allowsSpeculativeDownloads(cellularAllowed: Bool) -> Bool {
        isSatisfied && !isConstrained && (cellularAllowed || !isExpensive)
    }
}

@MainActor
public protocol NetworkPathObserving: AnyObject {
    func start(_ onChange: @escaping @MainActor (SpeculativeNetworkState) -> Void)
}

/// `NWPathMonitor`, delivered on the main actor.
@MainActor
public final class NetworkPathObserver: NetworkPathObserving {
    private let monitor = NWPathMonitor()
    private var started = false

    nonisolated public init() {}

    /// Nil in UI and unit tests: a speculative download must never join a journey or a model test
    /// that did not ask for it. Tests that need one inject their own observer.
    nonisolated public static func live(environment: [String: String] = ProcessInfo.processInfo.environment) -> NetworkPathObserver? {
        guard environment["UITEST_MODE"] != "1", environment["XCTestConfigurationFilePath"] == nil else { return nil }
        return NetworkPathObserver()
    }

    public func start(_ onChange: @escaping @MainActor (SpeculativeNetworkState) -> Void) {
        guard !started else { return }
        started = true
        monitor.pathUpdateHandler = { path in
            let state = SpeculativeNetworkState(
                isSatisfied: path.status == .satisfied,
                isExpensive: path.isExpensive,
                isConstrained: path.isConstrained
            )
            Task { @MainActor in onChange(state) }
        }
        monitor.start(queue: DispatchQueue(label: "aicaddie.network-path", qos: .utility))
    }

    deinit {
        monitor.cancel()
    }
}

/// 设置 → 离线球场 → "用蜂窝网络预下载常打的球场". Off by default.
public enum SpeculativePrefetchSettings {
    public static let cellularKey = "aicaddie.prefetch.likelyCoursesOnCellular"

    public static func cellularAllowed(_ defaults: UserDefaults = .standard) -> Bool {
        defaults.bool(forKey: cellularKey)
    }
}

/// The courses this player will likely play again: the last course started, then the courses with
/// the most rounds. At most `maximumCourses` are kept on the phone this way, which together with
/// the 200 MB cap bounds what speculative downloads can take.
enum SpeculativePrefetch {
    static let maximumCourses = 5

    /// Rows to queue now. The top `maximumCourses` are ranked first and only then filtered, so an
    /// installed or already queued course does not pull in a less likely one. Skipped: courses
    /// without a known Tee (a guessed Tee is a wasted download), courses already in the download
    /// list, installed courses, and courses eviction already found unused for 60 days (downloading
    /// them again would only be evicted again; a download does not count as a use).
    static func candidates(
        options: [MobileCourseOption],
        recent: MobileCourseOption?,
        existingIDs: Set<String>,
        lastUsed: [String: Date],
        now: Date,
        isInstalled: (PrepCourseDownloadRecord) -> Bool
    ) -> [PrepCourseDownloadRecord] {
        let played = options
            .filter { $0.roundCount > 0 }
            .sorted { lhs, rhs in
                if lhs.roundCount != rhs.roundCount { return lhs.roundCount > rhs.roundCount }
                return (lhs.latestRoundDate ?? "") > (rhs.latestRoundDate ?? "")
            }
        var seen = Set<Int>()
        var ranked: [(course: MobileCourseOption, tee: String)] = []
        for course in [recent].compactMap({ $0 }) + played {
            guard ranked.count < maximumCourses, course.globalId > 0,
                  seen.insert(course.globalId).inserted else { continue }
            guard let tee = course.teeBox?.trimmingCharacters(in: .whitespacesAndNewlines),
                  !tee.isEmpty, tee.lowercased() != "unknown" else { continue }
            ranked.append((course, tee))
        }
        return ranked.compactMap { entry in
            let record = PrepCourseDownloadRecord(
                course: entry.course,
                teeBox: entry.tee,
                updatedAt: now,
                isSpeculative: true
            )
            guard !existingIDs.contains(record.id), !isInstalled(record) else { return nil }
            if let key = CourseUsageLog.key(globalId: entry.course.globalId, teeBox: entry.tee),
               let used = lastUsed[key],
               OfflineStorageEviction.isIdle(lastUsedAt: used, now: now) {
                return nil
            }
            return record
        }
    }
}
