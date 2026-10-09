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

/// Account-scoped "last used" record per physical course and Tee (`course_usage_v1.json`). Eviction
/// (a later change) reads it; nothing here deletes by age. Writes merge, keeping the later time.
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

    private static func bytes(under directory: URL) -> Int64 {
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

    private static func remove(_ url: URL, from report: inout OfflineStorageGarbageReport) {
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
        var scopes = [root]
        let accounts = root.appendingPathComponent("accounts", isDirectory: true)
        scopes += try listing(of: accounts).filter { url in
            // `fileExists` follows a symlinked account directory; `isDirectoryKey` would not.
            var isDirectory = ObjCBool(false)
            return FileManager.default.fileExists(atPath: url.path, isDirectory: &isDirectory)
                && isDirectory.boolValue
        }
        var references = TopoReferences()
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
                references.files.formUnion(package.referencedFileKeys)
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
    private static func listing(of directory: URL) throws -> [URL] {
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

        /// Both the prep row's and the hole's own revision: the play screen falls back from one
        /// to the other (`CurrentHoleView.localTopoURL`).
        var referencedFileKeys: Set<String> {
            var keys = Set<String>()
            for hole in holes where hole.sourceGlobalId > 0 && hole.sourceLocalHole > 0 {
                let prepRevision = coursePrep?.holes.first { $0.hole == hole.number }?.geometryRevision
                for revision in [prepRevision, hole.geometryRevision] {
                    keys.insert(TopoFileName.fileKey(
                        globalId: hole.sourceGlobalId,
                        localHole: hole.sourceLocalHole,
                        geometryRevision: revision
                    ))
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
