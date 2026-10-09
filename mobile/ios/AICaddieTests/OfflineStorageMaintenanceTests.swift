import XCTest
@testable import AICaddie

/// Storage batch PR A: usage bookkeeping, the settings total, and garbage collection that only
/// removes bitmaps nothing on the phone can draw again.
final class OfflineStorageMaintenanceTests: XCTestCase {
    private var root: URL!
    private let now = Date(timeIntervalSince1970: 1_800_000_000)
    private let style = SyncClient.topoStyleVersion

    override func setUpWithError() throws {
        root = FileManager.default.temporaryDirectory
            .appendingPathComponent("storage-maintenance-\(UUID().uuidString)", isDirectory: true)
        try FileManager.default.createDirectory(at: root, withIntermediateDirectories: true)
    }

    override func tearDownWithError() throws {
        try? FileManager.default.removeItem(at: root)
    }

    // MARK: Helpers

    private var topoDirectory: URL {
        root.appendingPathComponent("course_topo", isDirectory: true)
            .appendingPathComponent(style, isDirectory: true)
    }

    private func account(_ id: String) -> URL {
        root.appendingPathComponent("accounts", isDirectory: true)
            .appendingPathComponent(id, isDirectory: true)
    }

    /// A bitmap file, aged so only the reference rules decide whether it stays.
    @discardableResult
    private func writeTopo(_ name: String, in directory: URL? = nil, ageHours: Double = 48) throws -> URL {
        let directory = directory ?? topoDirectory
        try FileManager.default.createDirectory(at: directory, withIntermediateDirectories: true)
        let url = directory.appendingPathComponent(name)
        try validOnePixelPNGData().write(to: url)
        try FileManager.default.setAttributes(
            [.modificationDate: now.addingTimeInterval(-ageHours * 3600)],
            ofItemAtPath: url.path
        )
        return url
    }

    /// The package fields that name a bitmap; the scan decodes only these.
    private func writePackage(
        _ relativePath: String,
        in scope: URL,
        holes: [(number: Int, globalId: Int, localHole: Int, revision: String?)],
        prepRevisions: [Int: String] = [:]
    ) throws {
        var root: [String: Any] = [
            "holes": holes.map { hole -> [String: Any] in
                var row: [String: Any] = [
                    "number": hole.number,
                    "sourceGlobalId": hole.globalId,
                    "sourceLocalHole": hole.localHole,
                ]
                if let revision = hole.revision { row["geometryRevision"] = revision }
                return row
            },
        ]
        if !prepRevisions.isEmpty {
            root["coursePrep"] = [
                "holes": prepRevisions.map { ["hole": $0.key, "geometryRevision": $0.value] as [String: Any] },
            ]
        }
        let url = scope.appendingPathComponent(relativePath)
        try FileManager.default.createDirectory(at: url.deletingLastPathComponent(), withIntermediateDirectories: true)
        try JSONSerialization.data(withJSONObject: root).write(to: url)
    }

    private func exists(_ name: String) -> Bool {
        FileManager.default.fileExists(atPath: topoDirectory.appendingPathComponent(name).path)
    }

    private func collect(activity: TopoWriterActivity = TopoWriterActivity()) -> OfflineStorageGarbageReport {
        OfflineStorageMaintenance.collectGarbage(root: root, currentStyleVersion: style, now: now, activity: activity)
    }

    // MARK: Style directories

    func testOlderStyleDirectoriesAndLooseLegacyBitmapsAreRemovedCurrentAndNewerKept() throws {
        let topoRoot = root.appendingPathComponent("course_topo", isDirectory: true)
        let current = try XCTUnwrap(OfflineStorageMaintenance.styleVersionNumber(style))
        try writeTopo("1-1.png", in: topoRoot.appendingPathComponent("topo-v\(current - 1)"))
        try writeTopo("1-1.png", in: topoRoot.appendingPathComponent("topo-v1"))
        try writeTopo("1-1.png", in: topoRoot.appendingPathComponent("topo-v\(current + 1)"))
        try writeTopo("1-1.png", in: topoRoot.appendingPathComponent("not-a-style"))
        try writeTopo("31795-1.png", in: topoRoot)
        try writeTopo("1-1.png")

        let report = collect()

        XCTAssertEqual(Set(report.removedStyleDirectories), ["topo-v\(current - 1)", "topo-v1"])
        XCTAssertEqual(report.removedTopoFiles, ["31795-1.png"])
        XCTAssertGreaterThan(report.freedBytes, 0)
        let remaining = Set(try FileManager.default.contentsOfDirectory(atPath: topoRoot.path))
        XCTAssertEqual(remaining, [style, "topo-v\(current + 1)", "not-a-style"])
        XCTAssertTrue(exists("1-1.png"), "an unreferenced bitmap with no referenced sibling stays")
    }

    // MARK: Superseded revisions

    func testSupersededRevisionIsRemovedOnlyWhenUnreferencedOldEnoughAndASiblingIsReferenced() throws {
        try writePackage(
            "course_templates/v2--100--blue--whole.json",
            in: account("a"),
            holes: [(1, 100, 1, "new"), (2, 100, 2, "keep")]
        )
        try writeTopo("100-1-new.png")
        try writeTopo("100-1-old.png")
        try writeTopo("100-1.png")
        try writeTopo("100-1-young.png", ageHours: 2)
        try writeTopo("100-2-keep.png")
        try writeTopo("100-3-orphan.png")

        let report = collect()

        XCTAssertEqual(Set(report.removedTopoFiles), ["100-1-old.png", "100-1.png"])
        XCTAssertNil(report.revisionSweepSkippedReason)
        XCTAssertTrue(exists("100-1-new.png"))
        XCTAssertTrue(exists("100-1-young.png"), "a fresh download may not have written its template yet")
        XCTAssertTrue(exists("100-2-keep.png"))
        XCTAssertTrue(exists("100-3-orphan.png"), "no referenced sibling → not provably superseded")
    }

    func testAnotherAccountsTemplateKeepsTheRevisionItStillReferences() throws {
        try writePackage("course_templates/v2--100--blue--whole.json", in: account("a"), holes: [(1, 100, 1, "new")])
        try writePackage("course_templates/v2--100--blue--whole.json", in: account("b"), holes: [(1, 100, 1, "old")])
        try writeTopo("100-1-new.png")
        try writeTopo("100-1-old.png")

        XCTAssertTrue(collect().removedTopoFiles.isEmpty)
        XCTAssertTrue(exists("100-1-old.png"))
    }

    func testRoundPackagesHomeCurrentAndLegacyRootAllCountAsReferences() throws {
        // An in-progress round on two physical courses, a package awaiting upload, the home package,
        // the current pointer and a pre-account legacy template each pin their own revision.
        try writePackage(
            "packages/round-1.json",
            in: account("a"),
            holes: [(1, 100, 9, "r9"), (2, 200, 1, "r1")]
        )
        try writePackage("packages/finished-unsent.json", in: account("b"), holes: [(1, 300, 1, "pending")])
        try writePackage("home_package.json", in: account("b"), holes: [(1, 400, 1, "home")])
        try writePackage("current_package.json", in: account("a"), holes: [(1, 500, 1, "cur")])
        try writePackage("course_templates/v2--600--blue--whole.json", in: root, holes: [(1, 600, 1, "legacy")])
        // The newer revision of every hole is referenced too, so each older one is a candidate.
        try writePackage(
            "course_templates/v2--999--blue--whole.json",
            in: account("c"),
            holes: [(1, 100, 9, "n"), (2, 200, 1, "n"), (3, 300, 1, "n"), (4, 400, 1, "n"), (5, 500, 1, "n"), (6, 600, 1, "n")]
        )
        for name in ["100-9", "200-1", "300-1", "400-1", "500-1", "600-1"] {
            try writeTopo("\(name)-n.png")
        }
        for name in ["100-9-r9", "200-1-r1", "300-1-pending", "400-1-home", "500-1-cur", "600-1-legacy"] {
            try writeTopo("\(name).png")
        }
        try writeTopo("100-9-stale.png")

        XCTAssertEqual(collect().removedTopoFiles, ["100-9-stale.png"])
    }

    func testPrepRowRevisionAndHoleRevisionAreBothReferenced() throws {
        try writePackage(
            "course_templates/v2--100--blue--whole.json",
            in: account("a"),
            holes: [(1, 100, 1, "holerev")],
            prepRevisions: [1: "preprev"]
        )
        try writeTopo("100-1-holerev.png")
        try writeTopo("100-1-preprev.png")
        try writeTopo("100-1-other.png")

        XCTAssertEqual(collect().removedTopoFiles, ["100-1-other.png"])
    }

    /// With a prep revision and no hole revision the app reads only the prep bitmap.
    func testPrepRevisionWithoutAHoleRevisionDoesNotReferenceTheUnrevisionedBitmap() throws {
        try writePackage(
            "course_templates/v2--100--blue--whole.json",
            in: account("a"),
            holes: [(1, 100, 1, nil)],
            prepRevisions: [1: "preprev"]
        )
        try writeTopo("100-1-preprev.png")
        try writeTopo("100-1.png")

        XCTAssertEqual(collect().removedTopoFiles, ["100-1.png"])
        XCTAssertTrue(exists("100-1-preprev.png"))
    }

    func testNoRevisionAtAllReferencesTheUnrevisionedBitmap() throws {
        try writePackage("course_templates/v2--100--blue--whole.json", in: account("a"), holes: [(1, 100, 1, nil)])
        try writePackage("course_templates/v2--100--white--whole.json", in: account("a"), holes: [(1, 100, 1, "white")])
        try writeTopo("100-1.png")
        try writeTopo("100-1-white.png")
        try writeTopo("100-1-stale.png")

        XCTAssertEqual(collect().removedTopoFiles, ["100-1-stale.png"])
        XCTAssertTrue(exists("100-1.png"))
    }

    /// The settings total includes this player's template bytes, so a switch must not keep showing
    /// the previous player's figure while the new scope is measured.
    @MainActor
    func testAccountSwitchForgetsThePreviousPlayersStorageUsage() async throws {
        let previousClubBagPlayer = ClubBagStore.playerId
        defer { ClubBagSyncCoordinator.shared.activate(playerId: previousClubBagPlayer, migrateLegacy: false) }
        let store = OfflineStore(directoryURL: root)
        let model = LiveRoundAppModel(
            offlineStore: store,
            apiBaseURL: URL(string: "https://storage.example.test")!,
            watchBridge: nil,
            garminSessionStore: nil,
            syncClient: nil
        )
        func session(_ id: String) -> AppSession {
            AppSession(token: "token", playerId: id, expiresAt: Date().addingTimeInterval(600))
        }
        model.activateSession(session("player-a"), migrateLegacyData: false)
        try writePackage(
            "course_templates/v2--1--blue--whole.json",
            in: account("player-a"),
            holes: [(1, 1, 1, nil)]
        )
        await model.refreshOfflineStorageUsage()
        XCTAssertGreaterThan(try XCTUnwrap(model.offlineStorageUsage).templateBytes, 0)

        model.activateSession(session("player-b"), migrateLegacyData: false)
        XCTAssertNil(model.offlineStorageUsage, "unknown until player B's scope is measured")
        await model.refreshOfflineStorageUsage()
        XCTAssertEqual(try XCTUnwrap(model.offlineStorageUsage).templateBytes, 0)
    }

    func testUnfinishedPrepDownloadPinsEveryBitmapOfItsCourse() throws {
        try writePackage("course_templates/v2--100--blue--whole.json", in: account("a"), holes: [(1, 100, 1, "old")])
        try writeTopo("100-1-old.png")
        try writeTopo("100-1-older.png")
        let downloading = PrepCourseDownloadRecord(
            course: MobileCourseOption(globalId: 100, name: "球场", holes: 18, teeBox: "blue"),
            teeBox: "blue",
            phase: .downloading
        )
        try FileManager.default.createDirectory(at: account("b"), withIntermediateDirectories: true)
        try JSONEncoder().encode([downloading])
            .write(to: account("b").appendingPathComponent("prep_course_downloads.json"))

        let report = collect()
        XCTAssertNil(report.revisionSweepSkippedReason, "the row decoded and pinned, rather than aborting the scan")
        XCTAssertTrue(report.removedTopoFiles.isEmpty)
        XCTAssertTrue(exists("100-1-older.png"))
    }

    /// A download may reuse an old bitmap that is on disk but not yet named by any template.
    func testNoSupersededBitmapIsRemovedWhileADownloadRuns() throws {
        try writePackage("course_templates/v2--100--blue--whole.json", in: account("a"), holes: [(1, 100, 1, "new")])
        try writeTopo("100-1-new.png")
        try writeTopo("100-1-old.png")
        let activity = TopoWriterActivity()
        activity.begin()

        let report = collect(activity: activity)

        XCTAssertEqual(report.revisionSweepSkippedReason, "download active")
        XCTAssertTrue(exists("100-1-old.png"))
        activity.end()
        XCTAssertEqual(collect(activity: activity).removedTopoFiles, ["100-1-old.png"])
    }

    func testADownloadStartingAfterTheScanStopsFurtherDeletes() throws {
        let activity = TopoWriterActivity()
        let token = try XCTUnwrap(activity.quietToken())
        activity.begin()
        activity.end()
        var ran = false
        XCTAssertFalse(activity.ifQuiet(since: token) { ran = true })
        XCTAssertFalse(ran, "a download that began (even one that already ended) invalidates the scan")
        let fresh = activity.quietToken()
        XCTAssertNotNil(fresh)
        XCTAssertTrue(activity.ifQuiet(since: fresh ?? 0) { ran = true })
        XCTAssertTrue(ran)
    }

    func testUnlistableDirectorySkipsTheRevisionSweep() throws {
        try writePackage("course_templates/v2--100--blue--whole.json", in: account("a"), holes: [(1, 100, 1, "new")])
        try writePackage("packages/round.json", in: account("b"), holes: [(1, 100, 1, "old")])
        let packages = account("b").appendingPathComponent("packages", isDirectory: true)
        try FileManager.default.setAttributes([.posixPermissions: 0o000], ofItemAtPath: packages.path)
        defer { try? FileManager.default.setAttributes([.posixPermissions: 0o755], ofItemAtPath: packages.path) }
        try writeTopo("100-1-new.png")
        try writeTopo("100-1-old.png")

        let report = collect()

        XCTAssertNotNil(report.revisionSweepSkippedReason, "an unlistable directory is not an empty one")
        XCTAssertTrue(exists("100-1-old.png"))
    }

    func testUnreadablePackageSkipsTheRevisionSweepButNotOldStyles() throws {
        try writePackage("course_templates/v2--100--blue--whole.json", in: account("a"), holes: [(1, 100, 1, "new")])
        try writePackage("packages/locked.json", in: account("b"), holes: [(1, 100, 1, "old")])
        let locked = account("b").appendingPathComponent("packages/locked.json")
        try FileManager.default.setAttributes([.posixPermissions: 0o000], ofItemAtPath: locked.path)
        defer { try? FileManager.default.setAttributes([.posixPermissions: 0o644], ofItemAtPath: locked.path) }
        try writeTopo("100-1-new.png")
        try writeTopo("100-1-old.png")
        let current = try XCTUnwrap(OfflineStorageMaintenance.styleVersionNumber(style))
        try writeTopo(
            "1-1.png",
            in: root.appendingPathComponent("course_topo/topo-v\(current - 1)", isDirectory: true)
        )

        let report = collect()

        XCTAssertNotNil(report.revisionSweepSkippedReason)
        XCTAssertTrue(exists("100-1-old.png"), "an unknown reference set never deletes")
        XCTAssertEqual(report.removedStyleDirectories, ["topo-v\(current - 1)"])
    }

    func testUndecodablePackageIsIgnoredBecauseTheAppCannotDrawFromItEither() throws {
        try writePackage("course_templates/v2--100--blue--whole.json", in: account("a"), holes: [(1, 100, 1, "new")])
        let junk = account("a").appendingPathComponent("packages/junk.json")
        try FileManager.default.createDirectory(at: junk.deletingLastPathComponent(), withIntermediateDirectories: true)
        try Data("{\"holes\": 3}".utf8).write(to: junk)
        try writeTopo("100-1-new.png")
        try writeTopo("100-1-old.png")

        let report = collect()

        XCTAssertNil(report.revisionSweepSkippedReason)
        XCTAssertEqual(report.removedTopoFiles, ["100-1-old.png"])
    }

    /// The scan's minimal decoder must read what the store really writes, and the bitmap name it
    /// derives must be the one the store saves under.
    func testRealStoredPackageProtectsTheBitmapTheStoreSaved() throws {
        let store = OfflineStore(directoryURL: root)
        store.bindAccount(playerId: "player-a", migrateLegacyData: false)
        let package = try LiveRoundPackageFixture.package(dataMode: "local")
        try store.saveRoundPackage(package)
        let hole = try XCTUnwrap(package.holes.first)
        XCTAssertTrue(try store.saveCourseTopoImage(
            validOnePixelPNGData(),
            globalId: hole.sourceGlobalId,
            localHole: hole.sourceLocalHole,
            geometryRevision: hole.geometryRevision
        ))
        let saved = try XCTUnwrap(store.loadCourseTopoImageURL(
            globalId: hole.sourceGlobalId,
            localHole: hole.sourceLocalHole,
            geometryRevision: hole.geometryRevision
        ))
        try FileManager.default.setAttributes(
            [.modificationDate: now.addingTimeInterval(-48 * 3600)],
            ofItemAtPath: saved.path
        )
        let superseded = "\(hole.sourceGlobalId)-\(hole.sourceLocalHole)-superseded.png"
        try writeTopo(superseded)

        let report = collect()

        XCTAssertEqual(report.removedTopoFiles, [superseded])
        XCTAssertTrue(FileManager.default.fileExists(atPath: saved.path))
        XCTAssertNotNil(store.loadCourseTopoImage(
            globalId: hole.sourceGlobalId,
            localHole: hole.sourceLocalHole,
            geometryRevision: hole.geometryRevision
        ))
    }

    func testTopoFileNamesRoundTripAndRejectForeignNames() {
        XCTAssertNotNil(TopoFileName("31795-1.png"))
        XCTAssertNil(TopoFileName("31795-1.png")?.revision)
        XCTAssertEqual(TopoFileName("31795-12-abc.png")?.revision, "abc")
        XCTAssertEqual(TopoFileName("31795-12-abc.png")?.fileKey, "31795-12-abc")
        XCTAssertNil(TopoFileName("31795-1-a-b.png"))
        XCTAssertNil(TopoFileName("x-1.png"))
        XCTAssertNil(TopoFileName("31795-0.png"))
        XCTAssertNil(TopoFileName("31795-1.json"))
        XCTAssertEqual(
            TopoFileName.fileKey(globalId: 7, localHole: 3, geometryRevision: " A-B "),
            "7-3-a%2Db",
            "a revision is lowercased and percent-encoded, so it never adds a hyphen"
        )
        XCTAssertEqual(TopoFileName.fileKey(globalId: 7, localHole: 3, geometryRevision: "  "), "7-3")
    }

    // MARK: Daily gate

    func testMaintenanceRunsAtMostOnceADay() throws {
        let scope = OfflineStorageScope(root: root, accountDirectory: account("a"))
        XCTAssertNotNil(scope.runMaintenanceIfDue(now: now))
        XCTAssertNil(scope.runMaintenanceIfDue(now: now.addingTimeInterval(23 * 3600)))
        XCTAssertNotNil(scope.runMaintenanceIfDue(now: now.addingTimeInterval(25 * 3600)))
        XCTAssertNotNil(
            scope.runMaintenanceIfDue(now: now.addingTimeInterval(-3600)),
            "a clock moved backwards does not block maintenance"
        )
    }

    // MARK: Usage

    func testCourseUseKeepsTheLatestTimePerCourseAndTee() throws {
        let store = OfflineStore(directoryURL: root)
        store.bindAccount(playerId: "player-a", migrateLegacyData: false)
        store.recordCourseUse(globalId: 100, teeBox: " Blue ", at: now)
        store.recordCourseUse(globalId: 100, teeBox: "blue", at: now.addingTimeInterval(-60))
        store.recordCourseUse(globalId: 100, teeBox: "white", at: now.addingTimeInterval(-60))
        store.recordCourseUse(globalId: 0, teeBox: "blue", at: now)

        XCTAssertEqual(store.loadCourseUsage(), [
            "100|blue": now,
            "100|white": now.addingTimeInterval(-60),
        ])

        store.bindAccount(playerId: "player-b", migrateLegacyData: false)
        XCTAssertTrue(store.loadCourseUsage().isEmpty, "usage is per account")
    }

    func testRoundUseMarksEveryPhysicalCourseOfThePackage() throws {
        let store = OfflineStore(directoryURL: root)
        store.bindAccount(playerId: "player-a", migrateLegacyData: false)
        let package = try LiveRoundPackageFixture.package(dataMode: "local")
        store.recordCourseUse(for: package, at: now)

        let expected = Set(package.holes.map(\.sourceGlobalId) + [package.course.globalId])
            .map { "\($0)|\(package.course.teeBox.lowercased())" }
        XCTAssertEqual(Set(store.loadCourseUsage().keys), Set(expected))
    }

    func testFirstMaintenanceSeedsInstalledCoursesWithoutMovingRecordedOnes() throws {
        let templates = account("a").appendingPathComponent("course_templates", isDirectory: true)
        try FileManager.default.createDirectory(at: templates, withIntermediateDirectories: true)
        for name in ["v2--100--blue--whole.json", "v2--200--%E7%99%BD--whole.json", "v1-300-blue.json", "notes.txt"] {
            try Data("{}".utf8).write(to: templates.appendingPathComponent(name))
        }
        let earlier = now.addingTimeInterval(-7 * 86_400)
        try CourseUsageLog.record(
            ["100|blue"],
            at: earlier,
            in: account("a").appendingPathComponent(CourseUsageLog.fileName)
        )

        OfflineStorageMaintenance.seedCourseUsage(accountDirectory: account("a"), now: now)

        let usage = CourseUsageLog.load(from: account("a").appendingPathComponent(CourseUsageLog.fileName))
        XCTAssertEqual(usage, ["100|blue": earlier, "200|白": now])
    }

    // MARK: Settings total

    func testUsageCountsSharedBitmapsAndOnlyThisAccountsTemplates() throws {
        try writeTopo("1-1.png")
        try writePackage("course_templates/v2--1--blue--whole.json", in: account("a"), holes: [(1, 1, 1, nil)])
        try writePackage("course_templates/v2--2--blue--whole.json", in: account("b"), holes: [(1, 2, 1, nil)])

        let usage = OfflineStorageScope(root: root, accountDirectory: account("a")).usage()
        let empty = OfflineStorageScope(root: root, accountDirectory: account("c")).usage()

        XCTAssertGreaterThan(usage.topoBytes, 0)
        XCTAssertGreaterThan(usage.templateBytes, 0)
        XCTAssertEqual(empty.templateBytes, 0)
        XCTAssertEqual(empty.topoBytes, usage.topoBytes, "bitmaps are shared by every account")
    }

    func testSummaryTextUsesDecimalMegabytes() {
        XCTAssertEqual(OfflineStorageUsage(topoBytes: 400_000, templateBytes: 0).summaryText, "离线地图共占用不到 1 MB")
        XCTAssertEqual(OfflineStorageUsage(topoBytes: 3_000_000, templateBytes: 420_000).summaryText, "离线地图共占用 3.4 MB")
        XCTAssertEqual(OfflineStorageUsage(topoBytes: 150_000_000, templateBytes: 2_600_000).summaryText, "离线地图共占用 153 MB")
    }
}

/// Storage batch PR B: over the cap, courses unused for 60 days go, least recently used first;
/// shared bitmaps go only once nothing on the phone references them.
extension OfflineStorageMaintenanceTests {
    private static let day: TimeInterval = 86_400

    private func scope(_ id: String = "a") -> OfflineStorageScope {
        OfflineStorageScope(root: root, accountDirectory: account(id))
    }

    private func template(_ globalId: Int, tee: String = "blue", in id: String = "a") -> URL {
        account(id).appendingPathComponent("course_templates", isDirectory: true)
            .appendingPathComponent("v2--\(globalId)--\(tee)--whole.json")
    }

    /// A one-hole whole-course template of `globalId`, last used `daysAgo` (nil: never recorded).
    private func installCourse(
        _ globalId: Int,
        tee: String = "blue",
        in id: String = "a",
        holes: [(number: Int, globalId: Int, localHole: Int, revision: String?)]? = nil,
        lastUsedDaysAgo daysAgo: Double?
    ) throws {
        try writePackage(
            "course_templates/v2--\(globalId)--\(tee)--whole.json",
            in: account(id),
            holes: holes ?? [(1, globalId, 1, nil)]
        )
        if let daysAgo {
            try CourseUsageLog.record(
                ["\(globalId)|\(tee)"],
                at: now.addingTimeInterval(-daysAgo * Self.day),
                in: account(id).appendingPathComponent(CourseUsageLog.fileName)
            )
        }
    }

    private func allocatedBytes(_ url: URL) -> Int64 {
        let values = try? url.resourceValues(forKeys: [.totalFileAllocatedSizeKey, .fileSizeKey])
        return Int64(values?.totalFileAllocatedSize ?? values?.fileSize ?? 0)
    }

    func testNothingIsPlannedUnderTheCap() throws {
        try installCourse(100, lastUsedDaysAgo: 365)
        XCTAssertNil(scope().evictionPlan(now: now, capBytes: .max))
    }

    func testOnlyCoursesIdleForSixtyDaysAreCandidatesOldestFirst() throws {
        try installCourse(100, lastUsedDaysAgo: 61)
        try installCourse(200, lastUsedDaysAgo: 90)
        try installCourse(300, lastUsedDaysAgo: 59)
        try installCourse(400, lastUsedDaysAgo: nil)
        try installCourse(500, lastUsedDaysAgo: -1)

        let plan = try XCTUnwrap(scope().evictionPlan(now: now, capBytes: 0))

        XCTAssertEqual(plan.candidates.map(\.usageKey), ["200|blue", "100|blue"],
                       "recent, unrecorded and future-stamped courses all stay")
        XCTAssertEqual(plan.candidates.first?.prepDownloadID, PrepCourseDownloadRecord.key(globalId: 200, teeBox: "blue"))
    }

    func testEveryCourseUsedWithinTheWindowMeansNothingIsRemovedOverTheCap() throws {
        try installCourse(100, lastUsedDaysAgo: 30)
        XCTAssertNil(scope().evictionPlan(now: now, capBytes: 0))
    }

    func testThePlanStopsOnceTheEstimateIsUnderTheCap() throws {
        try installCourse(100, lastUsedDaysAgo: 100)
        try installCourse(200, lastUsedDaysAgo: 80)
        try writeTopo("100-1.png")
        try writeTopo("200-1.png")
        let total = scope().usage().totalBytes

        let plan = try XCTUnwrap(scope().evictionPlan(now: now, capBytes: total - 1))

        XCTAssertEqual(plan.candidates.map(\.globalId), [100])
        XCTAssertEqual(
            plan.estimatedFreedBytes,
            allocatedBytes(template(100)) + allocatedBytes(topoDirectory.appendingPathComponent("100-1.png"))
        )
    }

    func testRoundHomeCurrentAndUnfinishedPrepCoursesAreNeverCandidates() throws {
        for globalId in [100, 200, 300, 400, 500, 600] {
            try installCourse(globalId, lastUsedDaysAgo: 120)
        }
        // A combined round spans two physical courses.
        try writePackage("packages/round-1.json", in: account("a"), holes: [(1, 100, 1, nil), (10, 200, 1, nil)])
        try writePackage("home_package.json", in: account("a"), holes: [(1, 300, 1, nil)])
        try writePackage("current_package.json", in: account("a"), holes: [(1, 400, 1, nil)])
        let downloading = PrepCourseDownloadRecord(
            course: MobileCourseOption(globalId: 500, name: "球场", holes: 18, teeBox: "blue"),
            teeBox: "blue",
            phase: .downloading
        )
        try JSONEncoder().encode([downloading])
            .write(to: account("a").appendingPathComponent("prep_course_downloads.json"))

        let plan = try XCTUnwrap(scope().evictionPlan(now: now, capBytes: 0))

        XCTAssertEqual(plan.candidates.map(\.globalId), [600])
        XCTAssertEqual(scope().protectedGlobalIds(), Set([100, 200, 300, 400]))
    }

    func testUnreadableRoundPackageStopsThePlan() throws {
        try installCourse(100, lastUsedDaysAgo: 120)
        let packages = account("a").appendingPathComponent("packages", isDirectory: true)
        try FileManager.default.createDirectory(at: packages.appendingPathComponent("round-1.json"), withIntermediateDirectories: true)

        XCTAssertNil(scope().evictionPlan(now: now, capBytes: 0), "a package that cannot be read might name the course")
        XCTAssertNil(scope().protectedGlobalIds())
    }

    func testEvictionKeepsBitmapsAnotherAccountStillReferences() throws {
        try installCourse(100, holes: [(1, 100, 1, "r1"), (2, 100, 2, "r1")], lastUsedDaysAgo: 120)
        try installCourse(100, in: "b", holes: [(1, 100, 1, "r1")], lastUsedDaysAgo: 120)
        let shared = try writeTopo("100-1-r1.png")
        let own = try writeTopo("100-2-r1.png")

        let plan = try XCTUnwrap(scope().evictionPlan(now: now, capBytes: 0))
        let candidate = try XCTUnwrap(plan.candidates.first)
        XCTAssertEqual(candidate.estimatedBytes, allocatedBytes(template(100)) + allocatedBytes(own),
                       "the bitmap account b still draws is not counted as freed")

        XCTAssertTrue(scope().queueTopoSweep(globalIds: [candidate.globalId]))
        XCTAssertTrue(scope().removeEvictedTemplate(candidate))
        let report = OfflineStorageEviction.sweepEvictedTopo(
            root: root, currentStyleVersion: style, now: now, activity: TopoWriterActivity()
        )

        XCTAssertEqual(report.removedTopoFiles, ["100-2-r1.png"])
        XCTAssertTrue(FileManager.default.fileExists(atPath: shared.path))
        XCTAssertFalse(FileManager.default.fileExists(atPath: template(100).path))
        XCTAssertTrue(FileManager.default.fileExists(atPath: template(100, in: "b").path), "another account's template is never a candidate")
        XCTAssertTrue(TopoSweepQueue.load(root: root).isEmpty)
    }

    func testSweepKeepsBitmapsOfAnInProgressRoundAndOfAnUnfinishedDownload() throws {
        try writePackage("packages/round-1.json", in: account("b"), holes: [(1, 100, 1, nil), (10, 200, 1, nil)])
        let downloading = PrepCourseDownloadRecord(
            course: MobileCourseOption(globalId: 300, name: "球场", holes: 18, teeBox: "blue"),
            teeBox: "blue",
            phase: .queued
        )
        try FileManager.default.createDirectory(at: account("c"), withIntermediateDirectories: true)
        try JSONEncoder().encode([downloading])
            .write(to: account("c").appendingPathComponent("prep_course_downloads.json"))
        for name in ["100-1.png", "200-1.png", "300-1.png", "100-2.png"] { try writeTopo(name) }
        try TopoSweepQueue.add([100, 200, 300], root: root)

        let report = OfflineStorageEviction.sweepEvictedTopo(
            root: root, currentStyleVersion: style, now: now, activity: TopoWriterActivity()
        )

        XCTAssertEqual(report.removedTopoFiles, ["100-2.png"])
        for name in ["100-1.png", "200-1.png", "300-1.png"] { XCTAssertTrue(exists(name), name) }
    }

    func testSweepSkippedByADownloadResumesAtTheNextPass() throws {
        try writeTopo("100-1.png")
        try writeTopo("100-2.png", ageHours: 2)
        try TopoSweepQueue.add([100], root: root)
        let activity = TopoWriterActivity()
        activity.begin()

        let skipped = OfflineStorageEviction.sweepEvictedTopo(root: root, currentStyleVersion: style, now: now, activity: activity)
        XCTAssertEqual(skipped.revisionSweepSkippedReason, "download active")
        XCTAssertTrue(exists("100-1.png"))
        XCTAssertEqual(TopoSweepQueue.load(root: root), [100], "the course stays queued")

        activity.end()
        let resumed = OfflineStorageEviction.sweepEvictedTopo(root: root, currentStyleVersion: style, now: now, activity: activity)
        XCTAssertEqual(resumed.removedTopoFiles, ["100-1.png"])
        XCTAssertTrue(exists("100-2.png"), "a bitmap younger than a day may belong to a download about to write its template")
        XCTAssertEqual(TopoSweepQueue.load(root: root), [100], "the young bitmap is looked at again later")

        let later = OfflineStorageEviction.sweepEvictedTopo(
            root: root, currentStyleVersion: style, now: now.addingTimeInterval(Self.day), activity: activity
        )
        XCTAssertEqual(later.removedTopoFiles, ["100-2.png"])
        XCTAssertTrue(TopoSweepQueue.load(root: root).isEmpty)
    }

    func testATemplateRewrittenSinceThePlanIsKept() throws {
        try installCourse(100, lastUsedDaysAgo: 120)
        try FileManager.default.setAttributes(
            [.modificationDate: now.addingTimeInterval(-100 * Self.day)],
            ofItemAtPath: template(100).path
        )
        let candidate = try XCTUnwrap(scope().evictionPlan(now: now, capBytes: 0)?.candidates.first)
        try FileManager.default.setAttributes([.modificationDate: now], ofItemAtPath: template(100).path)

        XCTAssertFalse(scope().removeEvictedTemplate(candidate))
        XCTAssertTrue(FileManager.default.fileExists(atPath: template(100).path))
    }

    func testCoursesUsedOrBusySinceThePlanAreDropped() throws {
        for globalId in [100, 200, 300] {
            try installCourse(globalId, lastUsedDaysAgo: 120)
        }
        let plan = try XCTUnwrap(scope().evictionPlan(now: now, capBytes: 0))
        XCTAssertEqual(plan.candidates.count, 3)
        var usage = CourseUsageLog.load(from: account("a").appendingPathComponent(CourseUsageLog.fileName))
        usage["100|blue"] = now

        let confirmed = OfflineStorageEviction.confirmedCandidates(plan, usage: usage, busyGlobalIds: [200], now: now)

        XCTAssertEqual(confirmed.map(\.globalId), [300])
    }

    /// A ready row left behind would be re-queued as stale at launch and download the course again.
    func testOnlyTheEvictedCoursesReadyRowsAreRemoved() throws {
        try installCourse(100, lastUsedDaysAgo: 120)
        let candidates = try XCTUnwrap(scope().evictionPlan(now: now, capBytes: 0)?.candidates)
        func row(_ globalId: Int, _ tee: String, _ phase: PrepCourseDownloadPhase) -> PrepCourseDownloadRecord {
            PrepCourseDownloadRecord(
                course: MobileCourseOption(globalId: globalId, name: "球场", holes: 18, teeBox: tee),
                teeBox: tee,
                phase: phase
            )
        }
        let rows = [row(100, "blue", .ready), row(100, "white", .ready), row(200, "blue", .ready)]

        let remaining = OfflineStorageEviction.prepRows(rows, withoutReadyRowsOf: candidates)

        XCTAssertEqual(remaining.map(\.id), [row(100, "white", .ready).id, row(200, "blue", .ready).id])
    }
}
