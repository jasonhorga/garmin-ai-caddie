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

/// 设置 → 离线球场 → "用蜂窝网络预下载球场" (常打的 and 新区域 courses). Off by default.
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
    /// A whole course on the phone: 18 bitmaps at ~220 KB plus facts and the template, rounded up.
    static let estimatedCourseBytes: Int64 = 8_000_000

    /// How many more whole courses fit under the eviction cap. A guess never pushes storage over
    /// it; a downloaded guess counts as newly installed (seeded as used), so eviction could not
    /// take it back for 60 days.
    static func courseRoom(usedBytes: Int64, capBytes: Int64 = OfflineStorageEviction.capBytes) -> Int {
        guard usedBytes < capBytes else { return 0 }
        return Int((capBytes - usedBytes) / estimatedCourseBytes)
    }

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

/// 新区域: the player is somewhere none of their courses are, so the nearest few courses download
/// on their own like any other guess (Wi-Fi by default, lowest priority, hidden, under the cap).
/// Once per area: the next area must be `areaMetres` away from where the last one was taken.
enum NewAreaPrefetch {
    static let maximumCourses = 3
    /// A played course this close means the player is at home, not somewhere new; the same
    /// distance separates one new area from the next.
    static let areaMetres: Double = 30_000
    /// Where the last new area was taken, as `[latitude, longitude]`.
    static let anchorKey = "aicaddie.prefetch.newAreaAnchor"
    /// The Tee for a course the player never played (Jason, 2026-10-09: "就下蓝 T").
    static let unplayedTee = "blue"

    /// Whether `latitude, longitude` is somewhere new: some played course is known (catalogue
    /// rounds or the last course started; with none there is no home to be away from), none is
    /// among `courseIDs` or within `areaMetres`, and the last area taken is not within it either.
    static func isNewArea(
        latitude: Double,
        longitude: Double,
        courseIDs: [Int],
        played: [MobileCourseOption],
        anchor: (latitude: Double, longitude: Double)?
    ) -> Bool {
        guard !played.isEmpty else { return false }
        if let anchor,
           GeoDistance.haversineMetres(latitude, longitude, anchor.latitude, anchor.longitude) < areaMetres {
            return false
        }
        let playedIDs = Set(played.map(\.globalId))
        guard !courseIDs.contains(where: playedIDs.contains) else { return false }
        return !played.contains { course in
            guard let lat = course.latitude, let lon = course.longitude else { return false }
            return GeoDistance.haversineMetres(latitude, longitude, lat, lon) < areaMetres
        }
    }

    /// The nearby rows to try, nearest first, or [] when this is not a new area (`isNewArea`).
    static func courses(
        matches: [MobileCourseSearchMatch],
        latitude: Double,
        longitude: Double,
        played: [MobileCourseOption],
        anchor: (latitude: Double, longitude: Double)?
    ) -> [MobileCourseOption] {
        guard isNewArea(
            latitude: latitude,
            longitude: longitude,
            courseIDs: matches.map(\.globalId),
            played: played,
            anchor: anchor
        ) else { return [] }
        var seen = Set<Int>()
        return matches
            .filter { $0.globalId > 0 && seen.insert($0.globalId).inserted }
            .sorted { ($0.distanceKm ?? .infinity) < ($1.distanceKm ?? .infinity) }
            .prefix(maximumCourses)
            .compactMap(\.courseOption)
    }

    /// The Tee to download: the blue Tee when the course has one, else none (the course is
    /// skipped rather than downloaded under another colour).
    static func tee(offered: [CourseTee]) -> String? {
        offered.contains { $0.teeBox.lowercased() == unplayedTee } ? unplayedTee : nil
    }

    /// Rows to queue for `courses` with their Tees (nil = skipped). Same skips as the 可能会打 list.
    static func candidates(
        courses: [(course: MobileCourseOption, tee: String?)],
        existingIDs: Set<String>,
        lastUsed: [String: Date],
        now: Date,
        isInstalled: (PrepCourseDownloadRecord) -> Bool
    ) -> [PrepCourseDownloadRecord] {
        courses.compactMap { entry in
            guard let tee = entry.tee else { return nil }
            let record = PrepCourseDownloadRecord(course: entry.course, teeBox: tee, updatedAt: now, isSpeculative: true)
            guard !existingIDs.contains(record.id), !isInstalled(record) else { return nil }
            if let key = CourseUsageLog.key(globalId: entry.course.globalId, teeBox: tee),
               let used = lastUsed[key],
               OfflineStorageEviction.isIdle(lastUsedAt: used, now: now) {
                return nil
            }
            return record
        }
    }

    static func loadAnchor(_ defaults: UserDefaults = .standard) -> (latitude: Double, longitude: Double)? {
        guard let pair = defaults.array(forKey: anchorKey) as? [Double], pair.count == 2 else { return nil }
        return (pair[0], pair[1])
    }

    static func saveAnchor(latitude: Double, longitude: Double, _ defaults: UserDefaults = .standard) {
        defaults.set([latitude, longitude], forKey: anchorKey)
    }
}

/// A nearby answer taken somewhere new: where, its nearest courses, and what is known of their
/// Tees so far (a course answered without a blue Tee, or whose lookup failed, is skipped).
struct NewAreaRequest {
    var latitude: Double
    var longitude: Double
    var courses: [MobileCourseOption]
    /// Blue Tees read so far, by course.
    var tees: [Int: String] = [:]
    /// Courses settled: Tee read (or none), lookup failed, or already on the phone or listed.
    var answered: Set<Int> = []

    var isComplete: Bool { Set(courses.map(\.globalId)).isSubset(of: answered) }

    func isSameArea(as other: NewAreaRequest) -> Bool {
        GeoDistance.haversineMetres(latitude, longitude, other.latitude, other.longitude) < NewAreaPrefetch.areaMetres
    }
}
