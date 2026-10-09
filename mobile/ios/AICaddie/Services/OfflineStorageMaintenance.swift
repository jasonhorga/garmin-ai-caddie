import Foundation

/// 设置 → 离线球场 footer: what the offline maps take on this phone. Topo bitmaps are shared by
/// every account on the phone; course templates are this account's own.
public struct OfflineStorageUsage: Equatable, Sendable {
    public let topoBytes: Int64
    public let templateBytes: Int64

    public init(topoBytes: Int64, templateBytes: Int64) {
        self.topoBytes = max(0, topoBytes)
        self.templateBytes = max(0, templateBytes)
    }

    public var totalBytes: Int64 { topoBytes + templateBytes }

    /// Decimal megabytes like the iOS storage screen, written out rather than through a
    /// locale-dependent formatter so the settings text is the same on every device.
    public var summaryText: String {
        let megabytes = Double(totalBytes) / 1_000_000
        if megabytes < 1 { return "离线地图共占用不到 1 MB" }
        if megabytes < 10 { return String(format: "离线地图共占用 %.1f MB", megabytes) }
        return "离线地图共占用 \(Int(megabytes.rounded())) MB"
    }
}

/// What one garbage-collection pass removed. Only bytes no build can read again are removed:
/// topo directories of an older renderer style and bitmaps superseded by a newer referenced
/// revision of the same physical hole.
public struct OfflineStorageGarbageReport: Equatable, Sendable {
    public var removedStyleDirectories: [String] = []
    public var removedTopoFiles: [String] = []
    public var freedBytes: Int64 = 0
    /// Set when superseded bitmaps were left alone because the reference scan was incomplete.
    public var revisionSweepSkippedReason: String?
}

/// One account's view of the store root. Value type with fixed paths, safe to use off the main actor.
public struct OfflineStorageScope: Equatable, Sendable {
    let root: URL
    let accountDirectory: URL

    public func usage() -> OfflineStorageUsage {
        OfflineStorageMaintenance.usage(root: root, accountDirectory: accountDirectory)
    }

    /// Cold-start maintenance, at most once a day: seed missing usage entries, then collect topo
    /// garbage. Nil when the last pass is less than a day old.
    @discardableResult
    public func runMaintenanceIfDue(now: Date = Date()) -> OfflineStorageGarbageReport? {
        guard OfflineStorageMaintenance.isDue(root: root, now: now) else { return nil }
        OfflineStorageMaintenance.seedCourseUsage(accountDirectory: accountDirectory, now: now)
        let report = OfflineStorageMaintenance.collectGarbage(
            root: root,
            currentStyleVersion: SyncClient.topoStyleVersion,
            now: now
        )
        OfflineStorageMaintenance.markRun(root: root, at: now)
        AICaddieLog.storage.info(
            "Offline storage maintenance: \(report.removedStyleDirectories.count, privacy: .public) style dirs, \(report.removedTopoFiles.count, privacy: .public) topo files, \(report.freedBytes, privacy: .public) bytes freed; revision sweep skipped: \(report.revisionSweepSkippedReason ?? "no", privacy: .public)"
        )
        return report
    }

    /// Over the cap, the courses this account may give up, oldest use first. Nil when under the
    /// cap, when nothing is idle long enough, or when the reference scan is incomplete.
    public func evictionPlan(
        now: Date = Date(),
        capBytes: Int64 = OfflineStorageEviction.capBytes
    ) -> OfflineStorageEvictionPlan? {
        OfflineStorageEviction.plan(root: root, accountDirectory: accountDirectory, now: now, capBytes: capBytes)
    }

    /// Courses this account's round, current and home packages name, read from disk now. Nil when
    /// one of them cannot be read, so nothing is evicted on a partial view.
    public func protectedGlobalIds() -> Set<Int>? {
        try? OfflineStorageEviction.protectedGlobalIds(accountDirectory: accountDirectory)
    }

    /// Deletes the template only if it is the file the plan measured (same modification date), so
    /// a template rewritten since then is kept.
    public func removeEvictedTemplate(_ candidate: CourseEvictionCandidate) -> Bool {
        OfflineStorageEviction.removeTemplate(candidate, accountDirectory: accountDirectory)
    }

    /// Records evicted courses whose bitmaps still have to be swept, before their templates go.
    /// False when the queue could not be written; the templates must then stay.
    public func queueTopoSweep(globalIds: Set<Int>) -> Bool {
        do {
            try TopoSweepQueue.add(globalIds, root: root)
            return true
        } catch {
            AICaddieLog.storage.error("Topo sweep queue write failed: \(String(describing: error), privacy: .public)")
            return false
        }
    }

    /// Removes bitmaps of evicted courses that no package of any account references any more.
    @discardableResult
    public func sweepEvictedTopo(now: Date = Date()) -> OfflineStorageGarbageReport {
        let report = OfflineStorageEviction.sweepEvictedTopo(
            root: root,
            currentStyleVersion: SyncClient.topoStyleVersion,
            now: now
        )
        if !report.removedTopoFiles.isEmpty || report.revisionSweepSkippedReason != nil {
            AICaddieLog.storage.info(
                "Evicted topo sweep: \(report.removedTopoFiles.count, privacy: .public) files, \(report.freedBytes, privacy: .public) bytes freed; skipped: \(report.revisionSweepSkippedReason ?? "no", privacy: .public)"
            )
        }
        return report
    }
}

/// Course downloads announce themselves here before they look at which bitmaps are already on
/// disk. A download reuses an existing bitmap without rewriting it, so its file can be old and,
/// until the download writes its template, unreferenced. Garbage collection deletes a superseded
/// bitmap only while no download is running or has started since its reference scan, and does
/// each check-and-delete under this lock, so a `begin()` either precedes the delete (which is then
/// skipped) or follows it (and the download then finds the file missing and fetches it).
public final class TopoWriterActivity: @unchecked Sendable {
    public static let shared = TopoWriterActivity()
    private let lock = NSLock()
    private var active = 0
    private var generation: UInt64 = 0

    public init() {}

    public func begin() {
        lock.lock()
        active += 1
        generation &+= 1
        lock.unlock()
    }

    public func end() {
        lock.lock()
        active = max(0, active - 1)
        lock.unlock()
    }

    /// Nil while a download runs; otherwise a token that a later `begin()` invalidates.
    func quietToken() -> UInt64? {
        lock.lock()
        defer { lock.unlock() }
        return active == 0 ? generation : nil
    }

    /// Runs `body` only if no download has begun since `token` was taken.
    func ifQuiet(since token: UInt64, _ body: () -> Void) -> Bool {
        lock.lock()
        defer { lock.unlock() }
        guard active == 0, generation == token else { return false }
        body()
        return true
    }
}

/// Account-scoped "last used" record per physical course and Tee (`course_usage_v1.json`), read by
/// `OfflineStorageEviction`. Writes merge, keeping the later time.
enum CourseUsageLog {
    static let fileName = "course_usage_v1.json"
    private static let lock = NSLock()

    static func key(globalId: Int, teeBox: String) -> String? {
        let tee = teeBox.trimmingCharacters(in: .whitespacesAndNewlines).lowercased()
        guard globalId > 0, !tee.isEmpty else { return nil }
        return "\(globalId)|\(tee)"
    }

    static func load(from url: URL) -> [String: Date] {
        lock.lock()
        defer { lock.unlock() }
        return loadUnlocked(url)
    }

    /// Records `date` for every key, never moving an existing entry back in time. With
    /// `onlyIfMissing`, an existing entry is kept as is (first-launch seeding).
    static func record(_ keys: Set<String>, at date: Date, onlyIfMissing: Bool = false, in url: URL) throws {
        guard !keys.isEmpty else { return }
        lock.lock()
        defer { lock.unlock() }
        var usage = loadUnlocked(url)
        var changed = false
        for key in keys {
            if let existing = usage[key], onlyIfMissing || existing >= date { continue }
            usage[key] = date
            changed = true
        }
        guard changed else { return }
        try FileManager.default.createDirectory(
            at: url.deletingLastPathComponent(),
            withIntermediateDirectories: true
        )
        let encoder = JSONEncoder()
        encoder.dateEncodingStrategy = .iso8601
        encoder.outputFormatting = [.sortedKeys]
        try encoder.encode(usage).write(to: url, options: [.atomic])
    }

    private static func loadUnlocked(_ url: URL) -> [String: Date] {
        guard let data = try? Data(contentsOf: url) else { return [:] }
        let decoder = JSONDecoder()
        decoder.dateDecodingStrategy = .iso8601
        return (try? decoder.decode([String: Date].self, from: data)) ?? [:]
    }
}

/// Filesystem-only maintenance over the store root. It never touches the account currently bound
/// to `OfflineStore` through mutable state, so it can run off the main actor.
enum OfflineStorageMaintenance {
    static let markerFileName = "offline_storage_maintenance_v1.json"
    /// A bitmap younger than this is never collected: a download may have written it moments
    /// before the template that references it.
    static let minimumTopoAge: TimeInterval = 24 * 60 * 60
    static let minimumInterval: TimeInterval = 24 * 60 * 60

    private struct Marker: Codable {
        let lastRunAt: Date
    }

    // MARK: Usage

    static func usage(root: URL, accountDirectory: URL) -> OfflineStorageUsage {
        OfflineStorageUsage(
            topoBytes: bytes(under: root.appendingPathComponent("course_topo", isDirectory: true)),
            templateBytes: bytes(under: accountDirectory.appendingPathComponent("course_templates", isDirectory: true))
        )
    }

    static func bytes(under directory: URL) -> Int64 {
        let keys: [URLResourceKey] = [.isRegularFileKey, .totalFileAllocatedSizeKey, .fileSizeKey]
        guard let enumerator = FileManager.default.enumerator(
            at: directory,
            includingPropertiesForKeys: keys,
            options: []
        ) else { return 0 }
        var total: Int64 = 0
        for case let url as URL in enumerator {
            guard let values = try? url.resourceValues(forKeys: Set(keys)),
                  values.isRegularFile == true else { continue }
            total += Int64(values.totalFileAllocatedSize ?? values.fileSize ?? 0)
        }
        return total
    }

    /// `v2--<globalId>--<tee>--whole.json` → usage key. Other names are never read by the app.
    static func usageKey(templateFileName name: String) -> String? {
        guard name.hasSuffix(".json") else { return nil }
        let parts = String(name.dropLast(5)).components(separatedBy: "--")
        guard parts.count == 4, parts[0] == "v2", parts[3] == "whole",
              let globalId = Int(parts[1]),
              let tee = parts[2].removingPercentEncoding else { return nil }
        return CourseUsageLog.key(globalId: globalId, teeBox: tee)
    }

    /// Courses installed before usage was recorded count as used now, so the first eviction
    /// window starts at this release instead of deleting every course on day one.
    static func seedCourseUsage(accountDirectory: URL, now: Date) {
        let templates = accountDirectory.appendingPathComponent("course_templates", isDirectory: true)
        guard let names = try? FileManager.default.contentsOfDirectory(atPath: templates.path) else { return }
        let keys = Set(names.compactMap(usageKey(templateFileName:)))
        do {
            try CourseUsageLog.record(
                keys,
                at: now,
                onlyIfMissing: true,
                in: accountDirectory.appendingPathComponent(CourseUsageLog.fileName)
            )
        } catch {
            AICaddieLog.storage.error(
                "Course usage seeding failed: \(String(describing: error), privacy: .public)"
            )
        }
    }

    // MARK: Garbage collection

    static func isDue(root: URL, now: Date) -> Bool {
        let decoder = JSONDecoder()
        decoder.dateDecodingStrategy = .iso8601
        guard let data = try? Data(contentsOf: root.appendingPathComponent(markerFileName)),
              let marker = try? decoder.decode(Marker.self, from: data) else { return true }
        // A clock moved backwards also counts as due rather than blocking for the skew.
        return now.timeIntervalSince(marker.lastRunAt) >= minimumInterval
            || marker.lastRunAt > now
    }

    static func markRun(root: URL, at date: Date) {
        let encoder = JSONEncoder()
        encoder.dateEncodingStrategy = .iso8601
        guard let data = try? encoder.encode(Marker(lastRunAt: date)) else { return }
        try? FileManager.default.createDirectory(at: root, withIntermediateDirectories: true)
        try? data.write(to: root.appendingPathComponent(markerFileName), options: [.atomic])
    }

    /// Removes (1) `course_topo/topo-vN` directories older than the current renderer style and
    /// unversioned bitmaps left directly in `course_topo/`, which no build reads; and (2) in the
    /// current style, a bitmap that no package of any account references while a newer referenced
    /// revision of the same physical hole exists. A bitmap with no referenced sibling is kept
    /// (it may belong to a download that has not written its template yet), and so is anything
    /// younger than `minimumTopoAge`.
    static func collectGarbage(
        root: URL,
        currentStyleVersion: String,
        now: Date,
        minimumAge: TimeInterval = minimumTopoAge,
        activity: TopoWriterActivity = .shared
    ) -> OfflineStorageGarbageReport {
        var report = OfflineStorageGarbageReport()
        let manager = FileManager.default
        let topoRoot = root.appendingPathComponent("course_topo", isDirectory: true)
        guard let currentVersion = styleVersionNumber(currentStyleVersion),
              let entries = try? manager.contentsOfDirectory(
                  at: topoRoot,
                  includingPropertiesForKeys: [.isDirectoryKey, .isSymbolicLinkKey],
                  options: []
              ) else { return report }

        for entry in entries {
            let name = entry.lastPathComponent
            let values = try? entry.resourceValues(forKeys: [.isDirectoryKey, .isSymbolicLinkKey])
            guard values?.isSymbolicLink != true else { continue }
            if values?.isDirectory == true {
                guard let version = styleVersionNumber(name), version < currentVersion else { continue }
                let size = bytes(under: entry)
                do {
                    try manager.removeItem(at: entry)
                    report.removedStyleDirectories.append(name)
                    report.freedBytes += size
                } catch {
                    AICaddieLog.storage.error(
                        "Old topo style removal failed \(name, privacy: .public): \(String(describing: error), privacy: .public)"
                    )
                }
            } else if name.lowercased().hasSuffix(".png") {
                remove(entry, from: &report)
            }
        }

        let currentDirectory = topoRoot.appendingPathComponent(currentStyleVersion, isDirectory: true)
        guard let quietToken = activity.quietToken() else {
            report.revisionSweepSkippedReason = "download active"
            return report
        }
        let references: TopoReferences
        do {
            references = try referencedTopo(root: root)
        } catch {
            report.revisionSweepSkippedReason = String(describing: error)
            return report
        }
        guard let files = try? manager.contentsOfDirectory(
            at: currentDirectory,
            includingPropertiesForKeys: [.isRegularFileKey, .contentModificationDateKey],
            options: []
        ) else { return report }

        var byHole: [String: [(url: URL, file: TopoFileName)]] = [:]
        for url in files {
            guard let file = TopoFileName(url.lastPathComponent) else { continue }
            byHole[file.holeKey, default: []].append((url, file))
        }
        for siblings in byHole.values {
            guard siblings.contains(where: { references.files.contains($0.file.fileKey) }) else { continue }
            for sibling in siblings where !references.files.contains(sibling.file.fileKey) {
                guard !references.pinnedGlobalIds.contains(sibling.file.globalId) else { continue }
                let values = try? sibling.url.resourceValues(forKeys: [.isRegularFileKey, .contentModificationDateKey])
                guard values?.isRegularFile == true,
                      let modified = values?.contentModificationDate,
                      now.timeIntervalSince(modified) >= minimumAge else { continue }
                let quiet = activity.ifQuiet(since: quietToken) {
                    remove(sibling.url, from: &report)
                }
                guard quiet else {
                    report.revisionSweepSkippedReason = "download started"
                    return report
                }
            }
        }
        return report
    }

    static func remove(_ url: URL, from report: inout OfflineStorageGarbageReport) {
        let size = Int64((try? url.resourceValues(forKeys: [.fileSizeKey]))?.fileSize ?? 0)
        do {
            try FileManager.default.removeItem(at: url)
            report.removedTopoFiles.append(url.lastPathComponent)
            report.freedBytes += size
        } catch {
            AICaddieLog.storage.error(
                "Topo removal failed \(url.lastPathComponent, privacy: .public): \(String(describing: error), privacy: .public)"
            )
        }
    }

    static func styleVersionNumber(_ name: String) -> Int? {
        guard name.hasPrefix("topo-v") else { return nil }
        return Int(name.dropFirst("topo-v".count))
    }

    // MARK: References

    struct TopoReferences: Equatable {
        /// `TopoFileName.fileKey` of every bitmap some package can render.
        var files: Set<String> = []
        /// Courses with an unfinished 备战 download in some account: every bitmap stays, because
        /// the job may already have written new revisions its template does not name yet.
        var pinnedGlobalIds: Set<Int> = []
    }

    enum ReferenceScanError: Error, CustomStringConvertible {
        case unreadable(String)

        var description: String {
            switch self {
            case .unreadable(let name): return "unreadable \(name)"
            }
        }
    }

    /// Every package-shaped file of every account (and the pre-account legacy root): course
    /// templates, round packages (in-progress and awaiting upload; a finished round's package is
    /// removed once uploaded), the current and home packages, plus unfinished prep downloads.
    /// A file that cannot be read aborts the scan; a file that reads but does not decode as a
    /// package is skipped, because the app cannot open it to draw any bitmap either.
    static func referencedTopo(root: URL) throws -> TopoReferences {
        let sources = try referenceSources(root: root)
        var references = TopoReferences(pinnedGlobalIds: sources.pinnedGlobalIds)
        for keys in sources.filesByPackage.values {
            references.files.formUnion(keys)
        }
        return references
    }

    /// Same file, same key, however the path was spelled (iOS `/private/var` vs `/var`).
    static func packageKey(_ url: URL) -> String {
        url.resolvingSymlinksInPath().standardizedFileURL.path
    }

    struct TopoReferenceSources: Equatable {
        /// `packageKey` of each decodable package file → the bitmaps it can render.
        var filesByPackage: [String: Set<String>] = [:]
        var pinnedGlobalIds: Set<Int> = []
    }

    /// `referencedTopo`, kept per package file so eviction can tell which bitmaps lose their last
    /// reference when a template goes.
    static func referenceSources(root: URL) throws -> TopoReferenceSources {
        var scopes = [root]
        let accounts = root.appendingPathComponent("accounts", isDirectory: true)
        scopes += try listing(of: accounts).filter { url in
            // `fileExists` follows a symlinked account directory; `isDirectoryKey` would not.
            var isDirectory = ObjCBool(false)
            return FileManager.default.fileExists(atPath: url.path, isDirectory: &isDirectory)
                && isDirectory.boolValue
        }
        var references = TopoReferenceSources()
        let decoder = JSONDecoder()
        for scope in scopes {
            var packageFiles = [
                scope.appendingPathComponent("current_package.json"),
                scope.appendingPathComponent("home_package.json"),
            ]
            for directory in ["course_templates", "packages"] {
                let url = scope.appendingPathComponent(directory, isDirectory: true)
                packageFiles += try listing(of: url).filter { $0.pathExtension.lowercased() == "json" }
            }
            for url in packageFiles where FileManager.default.fileExists(atPath: url.path) {
                let data: Data
                do {
                    data = try Data(contentsOf: url)
                } catch {
                    throw ReferenceScanError.unreadable(url.lastPathComponent)
                }
                guard let package = try? decoder.decode(TopoReferencingPackage.self, from: data) else {
                    continue
                }
                references.filesByPackage[packageKey(url)] = package.referencedFileKeys
            }
            let downloads = scope.appendingPathComponent("prep_course_downloads.json")
            if FileManager.default.fileExists(atPath: downloads.path) {
                guard let data = try? Data(contentsOf: downloads) else {
                    throw ReferenceScanError.unreadable(downloads.lastPathComponent)
                }
                if let rows = try? decoder.decode([PrepDownloadRow].self, from: data) {
                    for row in rows where row.phase != PrepCourseDownloadPhase.ready.rawValue {
                        references.pinnedGlobalIds.insert(row.course.globalId)
                    }
                } else {
                    throw ReferenceScanError.unreadable(downloads.lastPathComponent)
                }
            }
        }
        return references
    }

    /// A missing directory has no references; one that exists but cannot be listed aborts the scan
    /// like an unreadable file, rather than counting as empty.
    static func listing(of directory: URL) throws -> [URL] {
        guard FileManager.default.fileExists(atPath: directory.path) else { return [] }
        do {
            return try FileManager.default.contentsOfDirectory(
                at: directory,
                includingPropertiesForKeys: nil,
                options: [.skipsHiddenFiles]
            )
        } catch {
            throw ReferenceScanError.unreadable(directory.lastPathComponent)
        }
    }

    private struct PrepDownloadRow: Decodable {
        struct Course: Decodable { let globalId: Int }
        let course: Course
        let phase: String
    }

    /// The fields of `LiveRoundPackage` that name a bitmap, decoded on their own so the scan does
    /// not depend on the rest of the package schema.
    private struct TopoReferencingPackage: Decodable {
        struct Hole: Decodable {
            let number: Int
            let geometryRevision: String?
            let sourceGlobalId: Int
            let sourceLocalHole: Int
        }
        struct Prep: Decodable {
            struct Row: Decodable {
                let hole: Int
                let geometryRevision: String?
            }
            let holes: [Row]
        }
        let holes: [Hole]
        let coursePrep: Prep?

        /// Exactly the lookups the app makes (`CurrentHoleView.localTopoURL`, `PrepHoleRows.build`,
        /// `hasCourseTopoImages`): the prep row's revision, else the hole's; then the hole's own
        /// revision only when it exists. The unrevisioned bitmap is read only when both are absent.
        var referencedFileKeys: Set<String> {
            var keys = Set<String>()
            for hole in holes where hole.sourceGlobalId > 0 && hole.sourceLocalHole > 0 {
                let prepRevision = coursePrep?.holes.first { $0.hole == hole.number }?.geometryRevision
                func key(_ revision: String?) -> String {
                    TopoFileName.fileKey(
                        globalId: hole.sourceGlobalId,
                        localHole: hole.sourceLocalHole,
                        geometryRevision: revision
                    )
                }
                keys.insert(key(prepRevision ?? hole.geometryRevision))
                if let holeRevision = hole.geometryRevision {
                    keys.insert(key(holeRevision))
                }
            }
            return keys
        }
    }
}

/// `<globalId>-<localHole>[-<revision>].png`, as `OfflineStore.courseTopoURL` writes it. The
/// revision is percent-encoded over alphanumerics, so it never contains a hyphen.
struct TopoFileName: Equatable {
    let globalId: Int
    let localHole: Int
    let revision: String?

    init?(_ name: String) {
        guard name.hasSuffix(".png") else { return nil }
        let parts = String(name.dropLast(4)).split(separator: "-", omittingEmptySubsequences: false)
        guard parts.count == 2 || parts.count == 3,
              let globalId = Int(parts[0]), globalId > 0,
              let localHole = Int(parts[1]), localHole > 0 else { return nil }
        if parts.count == 3 {
            guard !parts[2].isEmpty else { return nil }
            revision = String(parts[2])
        } else {
            revision = nil
        }
        self.globalId = globalId
        self.localHole = localHole
    }

    var holeKey: String { "\(globalId)-\(localHole)" }
    var fileKey: String { revision.map { "\(holeKey)-\($0)" } ?? holeKey }

    static func normalizedRevision(_ value: String?) -> String? {
        guard let trimmed = value?.trimmingCharacters(in: .whitespacesAndNewlines).lowercased(),
              !trimmed.isEmpty else { return nil }
        return trimmed.addingPercentEncoding(withAllowedCharacters: .alphanumerics)
    }

    static func fileKey(globalId: Int, localHole: Int, geometryRevision: String?) -> String {
        let base = "\(globalId)-\(localHole)"
        return normalizedRevision(geometryRevision).map { "\(base)-\($0)" } ?? base
    }
}

// MARK: - Eviction

/// One course + Tee this account may give up: its template, and the bitmaps that lose their
/// last reference with it.
public struct CourseEvictionCandidate: Equatable, Sendable {
    public let usageKey: String
    public let globalId: Int
    public let teeBox: String
    let templateFileName: String
    let templateModifiedAt: Date
    public let lastUsedAt: Date
    public let estimatedBytes: Int64

    /// The 备战 row (`PrepCourseDownloadRecord.id`) that this template makes ready.
    public var prepDownloadID: String { PrepCourseDownloadRecord.key(globalId: globalId, teeBox: teeBox) }
}

public struct OfflineStorageEvictionPlan: Equatable, Sendable {
    public let usageBefore: OfflineStorageUsage
    /// Least recently used first; just enough to bring the estimate under the cap.
    public let candidates: [CourseEvictionCandidate]

    public var estimatedFreedBytes: Int64 { candidates.reduce(0) { $0 + $1.estimatedBytes } }
}

/// Over `capBytes`, this account gives up whole courses it has neither played nor opened in 备战
/// for `idleInterval`, least recently used first, until the estimate is back under the cap. When
/// every course was used within that window nothing is removed: the settings total simply stays
/// above the cap. Silent by design (IMPLEMENTATION_PLAN: process status goes to logs and settings).
///
/// Only this account's templates are candidates; another account's templates, and every package
/// of any account, keep the bitmaps they name. Removal runs in three steps so the app never sees
/// a ready 备战 row without its template: (1) the plan is computed off the main actor; (2) the
/// main actor re-checks it against live state, queues the bitmap sweep, saves the 备战 list
/// without the courses' ready rows, then deletes the templates; (3) the sweep removes the
/// courses' unreferenced bitmaps under `TopoWriterActivity`. The sweep queue is on disk, so a
/// pass that is skipped or interrupted resumes at the next maintenance.
public enum OfflineStorageEviction {
    public static let capBytes: Int64 = 200_000_000
    public static let idleInterval: TimeInterval = 60 * 24 * 60 * 60

    /// A use stamped in the future (clock moved back) is not idle.
    public static func isIdle(lastUsedAt: Date, now: Date) -> Bool {
        lastUsedAt <= now && now.timeIntervalSince(lastUsedAt) >= idleInterval
    }

    static func plan(
        root: URL,
        accountDirectory: URL,
        now: Date,
        capBytes: Int64,
        currentStyleVersion: String = SyncClient.topoStyleVersion
    ) -> OfflineStorageEvictionPlan? {
        let usage = OfflineStorageMaintenance.usage(root: root, accountDirectory: accountDirectory)
        guard usage.totalBytes > capBytes else { return nil }
        let lastUsed = CourseUsageLog.load(from: accountDirectory.appendingPathComponent(CourseUsageLog.fileName))
        let protected: Set<Int>
        let sources: OfflineStorageMaintenance.TopoReferenceSources
        let templateURLs: [URL]
        do {
            protected = try protectedGlobalIds(accountDirectory: accountDirectory)
            sources = try OfflineStorageMaintenance.referenceSources(root: root)
            templateURLs = try OfflineStorageMaintenance.listing(
                of: accountDirectory.appendingPathComponent("course_templates", isDirectory: true)
            )
        } catch {
            AICaddieLog.storage.error(
                "Offline storage over cap, eviction skipped: \(String(describing: error), privacy: .public)"
            )
            return nil
        }

        struct IdleCourse {
            let url: URL
            let key: String
            let globalId: Int
            let teeBox: String
            let lastUsedAt: Date
            let modifiedAt: Date
            let bytes: Int64
        }
        let templateKeys: [URLResourceKey] = [
            .isRegularFileKey, .isSymbolicLinkKey, .contentModificationDateKey, .totalFileAllocatedSizeKey, .fileSizeKey,
        ]
        var idle: [IdleCourse] = []
        for url in templateURLs {
            guard let key = OfflineStorageMaintenance.usageKey(templateFileName: url.lastPathComponent),
                  let identity = courseIdentity(usageKey: key),
                  let used = lastUsed[key], isIdle(lastUsedAt: used, now: now),
                  !protected.contains(identity.globalId),
                  !sources.pinnedGlobalIds.contains(identity.globalId),
                  let values = try? url.resourceValues(forKeys: Set(templateKeys)),
                  values.isRegularFile == true, values.isSymbolicLink != true,
                  let modifiedAt = values.contentModificationDate else { continue }
            idle.append(IdleCourse(
                url: url,
                key: key,
                globalId: identity.globalId,
                teeBox: identity.teeBox,
                lastUsedAt: used,
                modifiedAt: modifiedAt,
                bytes: Int64(values.totalFileAllocatedSize ?? values.fileSize ?? 0)
            ))
        }
        guard !idle.isEmpty else {
            AICaddieLog.storage.info(
                "Offline storage over cap (\(usage.totalBytes, privacy: .public) bytes), every course used within the idle window"
            )
            return nil
        }
        idle.sort { ($0.lastUsedAt, $0.key) < ($1.lastUsedAt, $1.key) }

        // Bitmaps of the current style by course, and how many packages name each one.
        var bitmaps: [Int: [(fileKey: String, bytes: Int64)]] = [:]
        let topoDirectory = root.appendingPathComponent("course_topo", isDirectory: true)
            .appendingPathComponent(currentStyleVersion, isDirectory: true)
        let bitmapKeys: [URLResourceKey] = [.isRegularFileKey, .totalFileAllocatedSizeKey, .fileSizeKey]
        for url in (try? FileManager.default.contentsOfDirectory(
            at: topoDirectory,
            includingPropertiesForKeys: bitmapKeys,
            options: []
        )) ?? [] {
            guard let file = TopoFileName(url.lastPathComponent),
                  let values = try? url.resourceValues(forKeys: Set(bitmapKeys)),
                  values.isRegularFile == true else { continue }
            bitmaps[file.globalId, default: []].append(
                (file.fileKey, Int64(values.totalFileAllocatedSize ?? values.fileSize ?? 0))
            )
        }
        var referenceCounts: [String: Int] = [:]
        for keys in sources.filesByPackage.values {
            for key in keys { referenceCounts[key, default: 0] += 1 }
        }

        var projected = usage.totalBytes
        var claimed = Set<String>()
        var candidates: [CourseEvictionCandidate] = []
        for course in idle {
            guard projected > capBytes else { break }
            for key in sources.filesByPackage[OfflineStorageMaintenance.packageKey(course.url)] ?? [] {
                referenceCounts[key, default: 0] -= 1
            }
            var freed = course.bytes
            for bitmap in bitmaps[course.globalId] ?? []
            where !claimed.contains(bitmap.fileKey) && referenceCounts[bitmap.fileKey, default: 0] <= 0 {
                claimed.insert(bitmap.fileKey)
                freed += bitmap.bytes
            }
            projected -= freed
            candidates.append(CourseEvictionCandidate(
                usageKey: course.key,
                globalId: course.globalId,
                teeBox: course.teeBox,
                templateFileName: course.url.lastPathComponent,
                templateModifiedAt: course.modifiedAt,
                lastUsedAt: course.lastUsedAt,
                estimatedBytes: freed
            ))
        }
        return OfflineStorageEvictionPlan(usageBefore: usage, candidates: candidates)
    }

    /// `"<globalId>|<tee>"` → its parts.
    static func courseIdentity(usageKey key: String) -> (globalId: Int, teeBox: String)? {
        let parts = key.split(separator: "|", maxSplits: 1, omittingEmptySubsequences: false)
        guard parts.count == 2, let globalId = Int(parts[0]), globalId > 0, !parts[1].isEmpty else { return nil }
        return (globalId, String(parts[1]))
    }

    /// Every course named by this account's round packages (in progress or awaiting upload, a
    /// round may span two courses), current package and home package.
    static func protectedGlobalIds(accountDirectory: URL) throws -> Set<Int> {
        var urls = [
            accountDirectory.appendingPathComponent("current_package.json"),
            accountDirectory.appendingPathComponent("home_package.json"),
        ]
        urls += try OfflineStorageMaintenance.listing(
            of: accountDirectory.appendingPathComponent("packages", isDirectory: true)
        ).filter { $0.pathExtension.lowercased() == "json" }
        var globalIds = Set<Int>()
        let decoder = JSONDecoder()
        for url in urls where FileManager.default.fileExists(atPath: url.path) {
            let data: Data
            do {
                data = try Data(contentsOf: url)
            } catch {
                throw OfflineStorageMaintenance.ReferenceScanError.unreadable(url.lastPathComponent)
            }
            // Like the bitmap scan: bytes the app cannot decode cannot be played either.
            guard let package = try? decoder.decode(CourseNamingPackage.self, from: data) else { continue }
            globalIds.formUnion(package.globalIds)
        }
        return globalIds
    }

    private struct CourseNamingPackage: Decodable {
        struct Course: Decodable { let globalId: Int }
        struct Hole: Decodable { let sourceGlobalId: Int }
        let course: Course?
        let holes: [Hole]

        var globalIds: Set<Int> {
            var ids = Set(holes.map(\.sourceGlobalId))
            if let course { ids.insert(course.globalId) }
            return ids
        }
    }

    /// The main actor's last look before deleting: a course used since the plan (`usage` is read
    /// again), or one a 备战 job or the live round is on (`busyGlobalIds`), is kept.
    public static func confirmedCandidates(
        _ plan: OfflineStorageEvictionPlan,
        usage: [String: Date],
        busyGlobalIds: Set<Int>,
        now: Date
    ) -> [CourseEvictionCandidate] {
        plan.candidates.filter { candidate in
            guard !busyGlobalIds.contains(candidate.globalId),
                  let used = usage[candidate.usageKey] else { return false }
            return isIdle(lastUsedAt: used, now: now)
        }
    }

    /// The 备战 list without the evicted courses' ready rows. It is saved before the templates go:
    /// a ready row whose template is missing is re-queued at launch and would download again.
    public static func prepRows(
        _ rows: [PrepCourseDownloadRecord],
        withoutReadyRowsOf candidates: [CourseEvictionCandidate]
    ) -> [PrepCourseDownloadRecord] {
        let evicted = Set(candidates.map(\.prepDownloadID))
        return rows.filter { !($0.phase == .ready && evicted.contains($0.id)) }
    }

    static func removeTemplate(_ candidate: CourseEvictionCandidate, accountDirectory: URL) -> Bool {
        let url = accountDirectory.appendingPathComponent("course_templates", isDirectory: true)
            .appendingPathComponent(candidate.templateFileName)
        let values = try? url.resourceValues(forKeys: [.isRegularFileKey, .contentModificationDateKey])
        guard values?.isRegularFile == true,
              values?.contentModificationDate == candidate.templateModifiedAt else { return false }
        do {
            try FileManager.default.removeItem(at: url)
            return true
        } catch {
            AICaddieLog.storage.error(
                "Template eviction failed \(candidate.templateFileName, privacy: .public): \(String(describing: error), privacy: .public)"
            )
            return false
        }
    }

    /// Removes the queued courses' bitmaps that no package of any account references and no
    /// unfinished 备战 download pins, under the same gate and age rule as garbage collection.
    /// A course leaves the queue once a full pass has removed all its unreferenced bitmaps.
    static func sweepEvictedTopo(
        root: URL,
        currentStyleVersion: String,
        now: Date,
        minimumAge: TimeInterval = OfflineStorageMaintenance.minimumTopoAge,
        activity: TopoWriterActivity = .shared
    ) -> OfflineStorageGarbageReport {
        var report = OfflineStorageGarbageReport()
        let pending = TopoSweepQueue.load(root: root)
        guard !pending.isEmpty else { return report }
        guard let quietToken = activity.quietToken() else {
            report.revisionSweepSkippedReason = "download active"
            return report
        }
        let references: OfflineStorageMaintenance.TopoReferences
        let files: [URL]
        do {
            references = try OfflineStorageMaintenance.referencedTopo(root: root)
            files = try OfflineStorageMaintenance.listing(
                of: root.appendingPathComponent("course_topo", isDirectory: true)
                    .appendingPathComponent(currentStyleVersion, isDirectory: true)
            )
        } catch {
            report.revisionSweepSkippedReason = String(describing: error)
            return report
        }
        var retry = Set<Int>()
        for url in files {
            guard let file = TopoFileName(url.lastPathComponent),
                  pending.contains(file.globalId),
                  !references.files.contains(file.fileKey),
                  !references.pinnedGlobalIds.contains(file.globalId) else { continue }
            let values = try? url.resourceValues(forKeys: [.isRegularFileKey, .contentModificationDateKey])
            guard values?.isRegularFile == true, let modified = values?.contentModificationDate else { continue }
            guard now.timeIntervalSince(modified) >= minimumAge else {
                // Too new to tell from a download about to write its template: look again later.
                retry.insert(file.globalId)
                continue
            }
            let quiet = activity.ifQuiet(since: quietToken) {
                OfflineStorageMaintenance.remove(url, from: &report)
            }
            guard quiet else {
                report.revisionSweepSkippedReason = "download started"
                return report
            }
            if FileManager.default.fileExists(atPath: url.path) { retry.insert(file.globalId) }
        }
        TopoSweepQueue.remove(pending.subtracting(retry), root: root)
        return report
    }
}

/// Courses whose templates were evicted and whose bitmaps are still to be swept
/// (`topo_sweep_pending_v1.json` at the store root; bitmaps are shared by every account).
enum TopoSweepQueue {
    static let fileName = "topo_sweep_pending_v1.json"
    private static let lock = NSLock()

    static func load(root: URL) -> Set<Int> {
        lock.lock()
        defer { lock.unlock() }
        return loadUnlocked(root)
    }

    static func add(_ globalIds: Set<Int>, root: URL) throws {
        try update(root) { $0.formUnion(globalIds) }
    }

    static func remove(_ globalIds: Set<Int>, root: URL) {
        do {
            try update(root) { $0.subtract(globalIds) }
        } catch {
            AICaddieLog.storage.error("Topo sweep queue write failed: \(String(describing: error), privacy: .public)")
        }
    }

    private static func update(_ root: URL, _ body: (inout Set<Int>) -> Void) throws {
        lock.lock()
        defer { lock.unlock() }
        var globalIds = loadUnlocked(root)
        let before = globalIds
        body(&globalIds)
        guard globalIds != before else { return }
        try FileManager.default.createDirectory(at: root, withIntermediateDirectories: true)
        try JSONEncoder().encode(globalIds.sorted())
            .write(to: root.appendingPathComponent(fileName), options: [.atomic])
    }

    private static func loadUnlocked(_ root: URL) -> Set<Int> {
        guard let data = try? Data(contentsOf: root.appendingPathComponent(fileName)),
              let globalIds = try? JSONDecoder().decode([Int].self, from: data) else { return [] }
        return Set(globalIds)
    }
}
