import XCTest
@testable import AICaddie

/// 可能会打: played courses download on their own, on Wi-Fi by default, after everything asked for.
@MainActor
final class SpeculativePrefetchTests: XCTestCase {
    private let now = Date(timeIntervalSince1970: 1_800_000_000)
    private var directory: URL!

    override func setUpWithError() throws {
        directory = FileManager.default.temporaryDirectory
            .appendingPathComponent("speculative-prefetch-\(UUID().uuidString)", isDirectory: true)
        UserDefaults.standard.removeObject(forKey: SpeculativePrefetchSettings.cellularKey)
        UserDefaults.standard.removeObject(forKey: NewAreaPrefetch.anchorKey)
    }

    override func tearDownWithError() throws {
        try? FileManager.default.removeItem(at: directory)
        UserDefaults.standard.removeObject(forKey: SpeculativePrefetchSettings.cellularKey)
        UserDefaults.standard.removeObject(forKey: NewAreaPrefetch.anchorKey)
        NewAreaURLProtocol.handler = nil
    }

    private func course(_ globalId: Int, rounds: Int, tee: String? = "blue", latest: String? = nil) -> MobileCourseOption {
        MobileCourseOption(globalId: globalId, name: "球场\(globalId)", roundCount: rounds, latestRoundDate: latest, teeBox: tee)
    }

    private func candidates(
        _ options: [MobileCourseOption],
        recent: MobileCourseOption? = nil,
        existing: Set<String> = [],
        lastUsed: [String: Date] = [:],
        installed: Set<Int> = []
    ) -> [PrepCourseDownloadRecord] {
        SpeculativePrefetch.candidates(
            options: options,
            recent: recent,
            existingIDs: existing,
            lastUsed: lastUsed,
            now: now,
            isInstalled: { installed.contains($0.course.globalId) }
        )
    }

    // MARK: Network policy

    func testWiFiOnlyByDefaultAndNeverInLowDataMode() {
        let wifi = SpeculativeNetworkState(isSatisfied: true, isExpensive: false, isConstrained: false)
        let cellular = SpeculativeNetworkState(isSatisfied: true, isExpensive: true, isConstrained: false)
        let lowData = SpeculativeNetworkState(isSatisfied: true, isExpensive: false, isConstrained: true)
        let offline = SpeculativeNetworkState(isSatisfied: false, isExpensive: false, isConstrained: false)

        XCTAssertTrue(wifi.allowsSpeculativeDownloads(cellularAllowed: false))
        XCTAssertFalse(cellular.allowsSpeculativeDownloads(cellularAllowed: false))
        XCTAssertTrue(cellular.allowsSpeculativeDownloads(cellularAllowed: true))
        XCTAssertFalse(lowData.allowsSpeculativeDownloads(cellularAllowed: true))
        XCTAssertFalse(offline.allowsSpeculativeDownloads(cellularAllowed: true))
        XCTAssertFalse(SpeculativeNetworkState.unknown.allowsSpeculativeDownloads(cellularAllowed: true))
        XCTAssertFalse(SpeculativePrefetchSettings.cellularAllowed(), "cellular is off until the player turns it on")
    }

    func testNoLiveObserverInTests() {
        XCTAssertNil(NetworkPathObserver.live(environment: ["UITEST_MODE": "1"]))
        XCTAssertNil(NetworkPathObserver.live(environment: ["XCTestConfigurationFilePath": "/tmp/x"]))
        XCTAssertNotNil(NetworkPathObserver.live(environment: [:]))
    }

    // MARK: Candidates

    func testRecentCourseFirstThenMostPlayedCappedAtFive() {
        let options = (1...8).map { course($0, rounds: $0) }
        let rows = candidates(options, recent: course(2, rounds: 2))

        XCTAssertEqual(rows.map(\.course.globalId), [2, 8, 7, 6, 5])
        XCTAssertTrue(rows.allSatisfy(\.isSpeculative))
        XCTAssertTrue(rows.allSatisfy { !$0.isIntentPrefetch && $0.phase == .queued })
    }

    func testTiesGoToTheMostRecentlyPlayed() {
        let rows = candidates([course(1, rounds: 3, latest: "2026-08-01"), course(2, rounds: 3, latest: "2026-09-01")])
        XCTAssertEqual(rows.map(\.course.globalId), [2, 1])
    }

    func testUnplayedAndTeeLessCoursesAreNeverGuessed() {
        let rows = candidates([
            course(1, rounds: 0),
            course(2, rounds: 4, tee: nil),
            course(3, rounds: 4, tee: " "),
            course(4, rounds: 4, tee: "unknown"),
            course(5, rounds: 1, tee: "White"),
        ])
        XCTAssertEqual(rows.map(\.id), [PrepCourseDownloadRecord.key(globalId: 5, teeBox: "White")])
    }

    /// Ranked first, filtered after: an installed or queued favourite does not pull in a sixth course.
    func testInstalledOrListedCoursesKeepTheirSlot() {
        let options = (1...6).map { course($0, rounds: 10 - $0) }
        let rows = candidates(
            options,
            existing: [PrepCourseDownloadRecord.key(globalId: 2, teeBox: "blue")],
            installed: [1]
        )
        XCTAssertEqual(rows.map(\.course.globalId), [3, 4, 5])
    }

    /// Eviction removed it after 60 idle days; downloading it again would only be evicted again.
    func testACourseIdleForSixtyDaysIsNotDownloadedAgain() {
        let rows = candidates(
            [course(1, rounds: 9), course(2, rounds: 8), course(3, rounds: 7)],
            lastUsed: [
                "1|blue": now.addingTimeInterval(-61 * 86_400),
                "2|blue": now.addingTimeInterval(-5 * 86_400),
            ]
        )
        XCTAssertEqual(rows.map(\.course.globalId), [2, 3])
    }

    func testGuessesNeverPushStoragePastTheCap() {
        let cap = OfflineStorageEviction.capBytes
        let course = SpeculativePrefetch.estimatedCourseBytes
        XCTAssertEqual(SpeculativePrefetch.courseRoom(usedBytes: 0), Int(cap / course))
        XCTAssertEqual(SpeculativePrefetch.courseRoom(usedBytes: cap - course), 1)
        XCTAssertEqual(SpeculativePrefetch.courseRoom(usedBytes: cap - course + 1), 0)
        XCTAssertEqual(SpeculativePrefetch.courseRoom(usedBytes: cap + 1), 0)
    }

    func testRowsFromOlderBuildsAreNotSpeculative() throws {
        let record = PrepCourseDownloadRecord(course: course(1, rounds: 1), teeBox: "blue", isSpeculative: true)
        var json = try XCTUnwrap(JSONSerialization.jsonObject(with: JSONEncoder().encode(record)) as? [String: Any])
        XCTAssertEqual(json["isSpeculative"] as? Bool, true)
        json.removeValue(forKey: "isSpeculative")
        let decoded = try JSONDecoder().decode(
            PrepCourseDownloadRecord.self,
            from: JSONSerialization.data(withJSONObject: json)
        )
        XCTAssertFalse(decoded.isSpeculative)
        XCTAssertFalse(decoded.yieldsToForeground)
    }

    // MARK: Queue

    private func model(rows: [PrepCourseDownloadRecord]) throws -> LiveRoundAppModel {
        let store = OfflineStore(directoryURL: directory)
        try store.savePrepCourseDownloads(rows)
        return LiveRoundAppModel(
            offlineStore: store,
            apiBaseURL: nil,
            watchBridge: nil,
            garminSessionStore: nil,
            syncClient: nil,
            offlineGeometryRetryDelaysNanoseconds: []
        )
    }

    private let wifi = SpeculativeNetworkState(isSatisfied: true, isExpensive: false, isConstrained: false)
    private let empty = OfflineStorageUsage(topoBytes: 0, templateBytes: 0)
    private let cellular = SpeculativeNetworkState(isSatisfied: true, isExpensive: true, isConstrained: false)

    func testASpeculativeJobWaitsForWiFiUnlessCellularIsAllowed() throws {
        let guess = PrepCourseDownloadRecord(course: course(1, rounds: 3), teeBox: "blue", updatedAt: now, isSpeculative: true)
        let model = try model(rows: [guess])
        model.publishOfflineStorageUsageForTesting(empty)
        XCTAssertNil(model.nextPrepCourseDownloadJobIDForTesting, "nothing runs before the first path update")

        model.setNetworkStateForTesting(cellular)
        XCTAssertNil(model.nextPrepCourseDownloadJobIDForTesting)
        model.setNetworkStateForTesting(wifi)
        XCTAssertEqual(model.nextPrepCourseDownloadJobIDForTesting, guess.id)
        model.setNetworkStateForTesting(cellular)
        UserDefaults.standard.set(true, forKey: SpeculativePrefetchSettings.cellularKey)
        model.speculativePrefetchSettingChanged()
        XCTAssertEqual(model.nextPrepCourseDownloadJobIDForTesting, guess.id)
        model.setNetworkStateForTesting(SpeculativeNetworkState(isSatisfied: true, isExpensive: true, isConstrained: true))
        XCTAssertNil(model.nextPrepCourseDownloadJobIDForTesting, "Low Data Mode wins over the setting")
    }

    func testJobsSomeoneAskedForRunBeforeANewerGuess() throws {
        let asked = PrepCourseDownloadRecord(course: course(1, rounds: 0), teeBox: "blue", updatedAt: now.addingTimeInterval(-3600))
        let guess = PrepCourseDownloadRecord(course: course(2, rounds: 3), teeBox: "blue", updatedAt: now, isSpeculative: true)
        let model = try model(rows: [guess, asked])
        model.publishOfflineStorageUsageForTesting(empty)
        model.setNetworkStateForTesting(wifi)

        XCTAssertEqual(model.nextPrepCourseDownloadJobIDForTesting, asked.id)
        XCTAssertTrue(model.prepCourseDownloads.contains { $0.id == guess.id && $0.isSpeculative })
    }

    /// Room comes only from a measurement newer than the last download's writes, so a finished guess
    /// can never leave the same room to be spent again.
    func testRoomIsSpentOnceUntilStorageIsMeasuredAgain() async throws {
        let guess = PrepCourseDownloadRecord(course: course(1, rounds: 3), teeBox: "blue", updatedAt: now, isSpeculative: true)
        let model = try model(rows: [guess])
        XCTAssertNil(model.speculativeCourseRoomForTesting, "nothing is queued before storage is measured")

        await model.refreshOfflineStorageUsage()
        let measured = try XCTUnwrap(model.offlineStorageUsage).totalBytes
        let full = SpeculativePrefetch.courseRoom(usedBytes: measured)
        XCTAssertEqual(model.speculativeCourseRoomForTesting, full - 1, "a queued guess holds a whole course")

        // The guess finishes: its row goes, its files land on disk after the measurement.
        model.noteOfflineStorageGrewForTesting()
        XCTAssertNil(model.speculativeCourseRoomForTesting, "the old measurement no longer counts")
        XCTAssertNil(model.speculativeCourseRoomForTesting, "asking again does not reuse it either")

        try await Task.sleep(nanoseconds: 10_000_000)
        await model.refreshOfflineStorageUsage()
        XCTAssertNotNil(model.speculativeCourseRoomForTesting, "a fresh measurement gives room again")
    }

    /// The dequeue itself, not just queueing: a guess already in the list starts only on a fresh
    /// measurement with room for one more course.
    func testAQueuedGuessStartsOnlyOnAFreshMeasurementWithRoom() async throws {
        let guess = PrepCourseDownloadRecord(course: course(1, rounds: 3), teeBox: "blue", updatedAt: now, isSpeculative: true)
        let model = try model(rows: [guess])
        model.setNetworkStateForTesting(wifi)
        XCTAssertNil(model.nextPrepCourseDownloadJobIDForTesting, "a guess left from the last launch waits for a measurement")

        model.publishOfflineStorageUsageForTesting(empty)
        XCTAssertEqual(model.nextPrepCourseDownloadJobIDForTesting, guess.id)

        // Another download (the player's own) wrote files after that measurement.
        try await Task.sleep(nanoseconds: 2_000_000)
        model.noteOfflineStorageGrewForTesting()
        XCTAssertNil(model.nextPrepCourseDownloadJobIDForTesting, "an old measurement does not let it start")

        try await Task.sleep(nanoseconds: 2_000_000)
        let courseBytes = SpeculativePrefetch.estimatedCourseBytes
        model.publishOfflineStorageUsageForTesting(
            OfflineStorageUsage(topoBytes: OfflineStorageEviction.capBytes - courseBytes + 1, templateBytes: 0)
        )
        XCTAssertNil(model.nextPrepCourseDownloadJobIDForTesting, "measured at the cap: no room for a whole course")

        model.publishOfflineStorageUsageForTesting(
            OfflineStorageUsage(topoBytes: OfflineStorageEviction.capBytes - courseBytes, templateBytes: 0)
        )
        XCTAssertEqual(model.nextPrepCourseDownloadJobIDForTesting, guess.id, "room for exactly this one; its own share is not deducted twice")
    }

    /// A download that finishes while the walk runs: the published measurement is already stale and
    /// that download's own request found the walk in flight. One retry measures again; it does not
    /// loop when the measurement can never be fresh (a clock moved backwards).
    func testAMeasurementOvertakenByADownloadIsRetriedOnce() async throws {
        let guess = PrepCourseDownloadRecord(course: course(1, rounds: 3), teeBox: "blue", updatedAt: now, isSpeculative: true)
        let model = try model(rows: [guess])
        model.setNetworkStateForTesting(wifi)
        // Stamped after any measurement this test can take: every walk comes back stale.
        model.noteOfflineStorageGrewForTesting(at: Date().addingTimeInterval(3600))
        let before = model.offlineStorageMeasurementCountForTesting

        await model.remeasureOfflineStorageForTesting()

        XCTAssertEqual(model.offlineStorageMeasurementCountForTesting - before, 2, "the walk and exactly one retry")
        XCTAssertNil(model.nextPrepCourseDownloadJobIDForTesting)

        // The write is in the past now: the next walk is fresh and the guess may start, with no retry.
        model.noteOfflineStorageGrewForTesting(at: Date().addingTimeInterval(-60))
        let fresh = model.offlineStorageMeasurementCountForTesting
        await model.remeasureOfflineStorageForTesting()
        XCTAssertEqual(model.offlineStorageMeasurementCountForTesting - fresh, 1)
        XCTAssertEqual(model.nextPrepCourseDownloadJobIDForTesting, guess.id)
    }

    func testAQueuedGuessWaitsWhileARoundIsBeingPrepared() throws {
        let asked = PrepCourseDownloadRecord(course: course(1, rounds: 0), teeBox: "blue", updatedAt: now.addingTimeInterval(-60))
        let guess = PrepCourseDownloadRecord(course: course(2, rounds: 3), teeBox: "blue", updatedAt: now, isSpeculative: true)
        let model = try model(rows: [guess])
        model.publishOfflineStorageUsageForTesting(empty)
        model.setNetworkStateForTesting(wifi)
        XCTAssertEqual(model.nextPrepCourseDownloadJobIDForTesting, guess.id)

        let token = model.beginRoundPreparationForTesting()
        XCTAssertNil(model.nextPrepCourseDownloadJobIDForTesting)
        // Network and settings callbacks during preparation do not let it through.
        model.setNetworkStateForTesting(cellular)
        UserDefaults.standard.set(true, forKey: SpeculativePrefetchSettings.cellularKey)
        model.speculativePrefetchSettingChanged()
        model.setNetworkStateForTesting(wifi)
        XCTAssertNil(model.nextPrepCourseDownloadJobIDForTesting)
        XCTAssertEqual(model.prepCourseDownloads.first { $0.id == guess.id }?.phase, .queued)

        model.finishRoundPreparationForTesting(token)
        XCTAssertEqual(model.nextPrepCourseDownloadJobIDForTesting, guess.id)

        // A 备战 download the player asked for keeps its existing rules during preparation.
        let playerModel = try self.model(rows: [asked])
        let playerToken = playerModel.beginRoundPreparationForTesting()
        XCTAssertEqual(playerModel.nextPrepCourseDownloadJobIDForTesting, asked.id)
        playerModel.finishRoundPreparationForTesting(playerToken)
    }

    func testOpeningAGuessedCourseInPrepMakesItThePlayersOwn() throws {
        let option = course(1, rounds: 3)
        let guess = PrepCourseDownloadRecord(course: option, teeBox: "blue", updatedAt: now, isSpeculative: true)
        let model = try model(rows: [guess])

        model.downloadPrepCourse(option)

        let row = try XCTUnwrap(model.prepCourseDownloads.first { $0.id == guess.id })
        XCTAssertFalse(row.isSpeculative)
        XCTAssertEqual(model.nextPrepCourseDownloadJobIDForTesting, guess.id, "runs on any network now")
    }

    // MARK: 新区域

    /// Home is 31.0,121.0; the trip is ~1° (≈110 km) north.
    private let home = (latitude: 31.0, longitude: 121.0)
    private let away = (latitude: 32.0, longitude: 121.0)

    private func homeCourse(_ globalId: Int = 900) -> MobileCourseOption {
        MobileCourseOption(globalId: globalId, name: "家", roundCount: 4, teeBox: "white", latitude: home.latitude, longitude: home.longitude)
    }

    private func match(_ globalId: Int, km: Double?, holes: Int? = 18) -> MobileCourseSearchMatch {
        MobileCourseSearchMatch(
            globalId: globalId, name: "球场\(globalId)", holes: holes, city: nil, province: nil, ratio: 1,
            latitude: away.latitude, longitude: away.longitude, distanceKm: km
        )
    }

    private func newArea(
        _ matches: [MobileCourseSearchMatch],
        at point: (latitude: Double, longitude: Double)? = nil,
        played: [MobileCourseOption]? = nil,
        anchor: (latitude: Double, longitude: Double)? = nil
    ) -> [Int] {
        let at = point ?? away
        return NewAreaPrefetch.courses(
            matches: matches, latitude: at.latitude, longitude: at.longitude,
            played: played ?? [homeCourse()], anchor: anchor
        ).map(\.globalId)
    }

    func testANewAreaTakesTheNearestThreeCourses() {
        let matches = [match(4, km: 4.0), match(1, km: 0.5), match(3, km: 2.5), match(2, km: 1.2), match(5, km: nil)]
        XCTAssertEqual(newArea(matches), [1, 2, 3])
        XCTAssertEqual(newArea([match(1, km: 1), match(1, km: 1)]), [1], "a duplicate row counts once")
        XCTAssertEqual(
            newArea([match(1, km: 0.5, holes: nil), match(2, km: 1), match(3, km: 2), match(4, km: 3)]),
            [2, 3],
            "the nearest three are ranked first; a row without a hole count cannot be downloaded and does not pull in a fourth"
        )
    }

    func testHomeAndPlayedAreasAreNotNew() {
        let matches = [match(1, km: 0.5), match(2, km: 1)]
        XCTAssertEqual(newArea(matches, at: (31.1, 121.0)), [], "a played course within 30 km: home")
        XCTAssertEqual(
            newArea(matches + [match(900, km: 3)], played: [MobileCourseOption(globalId: 900, name: "去年", roundCount: 1)]),
            [],
            "a played course among the nearby rows, even without coordinates"
        )
        XCTAssertEqual(newArea(matches, played: []), [], "no played course known: no home to be away from")
    }

    func testAnAreaIsTakenOnce() {
        let matches = [match(1, km: 0.5)]
        XCTAssertEqual(newArea(matches, anchor: (32.1, 121.0)), [], "within 30 km of the last area taken")
        XCTAssertEqual(newArea(matches, anchor: (33.0, 121.0)), [1], "a new area far enough from the last one")

        NewAreaPrefetch.saveAnchor(latitude: 32.0, longitude: 121.0)
        let anchor = NewAreaPrefetch.loadAnchor()
        XCTAssertEqual(anchor?.latitude, 32.0)
        XCTAssertEqual(anchor?.longitude, 121.0)
    }

    func testOnlyTheBlueTeeIsDownloaded() {
        XCTAssertEqual(NewAreaPrefetch.tee(offered: [CourseTee(teeBox: "white", name: "白"), CourseTee(teeBox: "Blue", name: "蓝")]), "blue")
        XCTAssertNil(
            NewAreaPrefetch.tee(offered: [CourseTee(teeBox: "black", name: "黑", isDefault: true), CourseTee(teeBox: "white", name: "白")]),
            "no blue Tee: skipped, not downloaded under the default"
        )
        XCTAssertNil(NewAreaPrefetch.tee(offered: []))

        let a = MobileCourseOption(globalId: 1, name: "A")
        let b = MobileCourseOption(globalId: 2, name: "B")
        let c = MobileCourseOption(globalId: 3, name: "C")
        let d = MobileCourseOption(globalId: 4, name: "D")
        let rows = NewAreaPrefetch.candidates(
            courses: [(a, "blue"), (b, nil), (c, "blue"), (d, "blue")],
            existingIDs: [PrepCourseDownloadRecord.key(globalId: 3, teeBox: "blue")],
            lastUsed: [:],
            now: now,
            isInstalled: { $0.course.globalId == 4 }
        )
        XCTAssertEqual(rows.map(\.id), [PrepCourseDownloadRecord.key(globalId: 1, teeBox: "blue")])
        XCTAssertTrue(rows.allSatisfy(\.isSpeculative))
    }

    /// Records the Tee lookups the stubbed backend received; lookups of `held` courses never answer.
    private final class TeeLookups: @unchecked Sendable {
        private let lock = NSLock()
        private var ids: [Int] = []
        private var heldIDs: Set<Int> = []
        func append(_ id: Int) { lock.withLock { ids.append(id) } }
        var all: [Int] { lock.withLock { ids } }
        var held: Set<Int> {
            get { lock.withLock { heldIDs } }
            set { lock.withLock { heldIDs = newValue } }
        }
    }

    /// A model whose backend answers nearby with `nearby` rows (id, km, holes) and each course's
    /// Tees with blue + white, except `noBlue` courses (black only) and `failing` courses (an
    /// unreadable answer). Every other request (the queued downloads) never answers, so queued
    /// rows stay put. The home course is the last one started.
    private func newAreaModel(
        nearby: [(id: Int, km: Double, holes: Int)],
        noBlue: Set<Int> = [],
        failing: Set<Int> = []
    ) throws -> (LiveRoundAppModel, TeeLookups) {
        let store = OfflineStore(directoryURL: directory)
        try store.saveRecentCourseSelection(homeCourse())
        let lookups = TeeLookups()
        let rows = nearby
            .map { #"{"globalId":\#($0.id),"name":"球场\#($0.id)","holes":\#($0.holes),"ratio":1,"distanceKm":\#($0.km)}"# }
            .joined(separator: ",")
        NewAreaURLProtocol.handler = { request in
            guard let path = request.url?.path else { return nil }
            if path == "/api/v2/courses/nearby" {
                return #"{"schema":"ai-caddie-nearby-courses-v1","radiusKm":5,"matches":[\#(rows)]}"#
            }
            let parts = path.split(separator: "/")
            guard parts.count == 5, parts[2] == "courses", parts[4] == "tees", let id = Int(parts[3]) else {
                return nil
            }
            lookups.append(id)
            if lookups.held.contains(id) { return nil }
            if failing.contains(id) { return "{}" }
            let tees = noBlue.contains(id)
                ? #"[{"teeBox":"black","name":"黑","default":true}]"#
                : #"[{"teeBox":"white","name":"白"},{"teeBox":"blue","name":"蓝","default":true}]"#
            return #"{"schema":"ai-caddie-course-tees-v1","globalId":\#(id),"tees":\#(tees)}"#
        }
        let configuration = URLSessionConfiguration.ephemeral
        configuration.protocolClasses = [NewAreaURLProtocol.self]
        let baseURL = try XCTUnwrap(URL(string: "https://example.test"))
        let model = LiveRoundAppModel(
            offlineStore: store,
            apiBaseURL: baseURL,
            adminToken: "admin-secret",
            watchBridge: nil,
            garminSessionStore: nil,
            syncClient: SyncClient(baseURL: baseURL, adminToken: "admin-secret", session: URLSession(configuration: configuration)),
            offlineGeometryRetryDelaysNanoseconds: []
        )
        return (model, lookups)
    }

    /// New-area guesses in the list (the home course is a 可能会打 guess of its own).
    private func newAreaGuesses(_ model: LiveRoundAppModel) -> Set<Int> {
        Set(model.prepCourseDownloads.filter { $0.isSpeculative && $0.course.globalId != 900 }.map(\.course.globalId))
    }

    /// The real path: a nearby answer somewhere new reads the Tees and queues the blue-Tee courses as
    /// guesses, anchors the area, and the same area does not ask again.
    func testANearbyAnswerSomewhereNewQueuesItsBlueTeeCourses() async throws {
        let (model, lookups) = try newAreaModel(
            nearby: [(11, 0.4, 18), (12, 1.0, 18), (13, 2.0, 9), (14, 3.0, 18)],
            noBlue: [12]
        )
        model.publishOfflineStorageUsageForTesting(empty)
        model.setNetworkStateForTesting(wifi)

        _ = try await model.nearbyCourses(latitude: away.latitude, longitude: away.longitude, radiusKm: 5)
        await model.waitForNewAreaPassForTesting()

        XCTAssertEqual(lookups.all.sorted(), [11, 12, 13], "only the nearest three")
        XCTAssertEqual(newAreaGuesses(model), [11, 13], "12 has no blue Tee")
        XCTAssertTrue(model.prepCourseDownloads.filter { $0.course.globalId == 11 || $0.course.globalId == 13 }.allSatisfy { $0.teeBox == "blue" })
        let anchor = try XCTUnwrap(NewAreaPrefetch.loadAnchor())
        XCTAssertEqual(anchor.latitude, away.latitude)

        // The same area again (the home card re-asks every ~100 m): no more lookups.
        _ = try await model.nearbyCourses(latitude: away.latitude + 0.01, longitude: away.longitude, radiusKm: 5)
        await model.waitForNewAreaPassForTesting()
        XCTAssertEqual(lookups.all.count, 3)
    }

    /// Off Wi-Fi nothing is looked up; the area waits and is taken once Wi-Fi comes back.
    func testANewAreaWaitsForWiFi() async throws {
        let (model, lookups) = try newAreaModel(nearby: [(21, 0.4, 18)])
        model.publishOfflineStorageUsageForTesting(empty)
        model.setNetworkStateForTesting(cellular)

        _ = try await model.nearbyCourses(latitude: away.latitude, longitude: away.longitude, radiusKm: 5)
        await model.waitForNewAreaPassForTesting()
        XCTAssertEqual(lookups.all, [], "nothing is looked up on cellular")
        XCTAssertNil(NewAreaPrefetch.loadAnchor(), "the area is not taken yet")

        model.setNetworkStateForTesting(wifi)
        await model.waitForNewAreaPassForTesting()
        XCTAssertEqual(lookups.all, [21])
        XCTAssertEqual(newAreaGuesses(model), [21])
        XCTAssertNotNil(NewAreaPrefetch.loadAnchor())
    }

    /// Room for one more course: the nearest goes now, the next waits with its Tee for room (no
    /// second lookup), and only then is the area taken.
    func testCoursesThatDoNotFitWaitForRoom() async throws {
        let (model, lookups) = try newAreaModel(nearby: [(31, 0.4, 18), (32, 1.0, 18)])
        let course = SpeculativePrefetch.estimatedCourseBytes
        let cap = OfflineStorageEviction.capBytes
        model.publishOfflineStorageUsageForTesting(OfflineStorageUsage(topoBytes: cap - 2 * course, templateBytes: 0))
        model.setNetworkStateForTesting(wifi)
        XCTAssertEqual(model.speculativeCourseRoomForTesting, 1, "the home course took one of the two")

        _ = try await model.nearbyCourses(latitude: away.latitude, longitude: away.longitude, radiusKm: 5)
        await model.waitForNewAreaPassForTesting()
        XCTAssertEqual(newAreaGuesses(model), [31])
        XCTAssertNil(NewAreaPrefetch.loadAnchor(), "not taken while a course still waits")

        try await Task.sleep(nanoseconds: 2_000_000)
        model.publishOfflineStorageUsageForTesting(empty)
        XCTAssertEqual(newAreaGuesses(model), [31, 32])
        XCTAssertEqual(lookups.all.sorted(), [31, 32], "the waiting course kept its Tee")
        XCTAssertNotNil(NewAreaPrefetch.loadAnchor())
    }

    /// A course whose lookup fails is skipped, not looked up again; the area is still taken.
    func testAFailedLookupSkipsItsCourse() async throws {
        let (model, lookups) = try newAreaModel(nearby: [(51, 0.4, 18), (52, 1.0, 18)], failing: [51])
        model.publishOfflineStorageUsageForTesting(empty)
        model.setNetworkStateForTesting(wifi)

        _ = try await model.nearbyCourses(latitude: away.latitude, longitude: away.longitude, radiusKm: 5)
        await model.waitForNewAreaPassForTesting()
        XCTAssertEqual(newAreaGuesses(model), [52])
        XCTAssertNotNil(NewAreaPrefetch.loadAnchor())
        XCTAssertEqual(lookups.all.sorted(), [51, 52])
    }

    /// Losing Wi-Fi mid-lookup stops the lookups (none runs on cellular); the area waits, and Wi-Fi
    /// again reads only what was not read.
    func testLosingWiFiStopsTheLookups() async throws {
        let (model, lookups) = try newAreaModel(nearby: [(61, 0.4, 18), (62, 1.0, 18)])
        lookups.held = [61]
        model.publishOfflineStorageUsageForTesting(empty)
        model.setNetworkStateForTesting(wifi)

        _ = try await model.nearbyCourses(latitude: away.latitude, longitude: away.longitude, radiusKm: 5)
        for _ in 0..<2_000 where lookups.all.isEmpty { try await Task.sleep(nanoseconds: 1_000_000) }
        XCTAssertEqual(lookups.all, [61], "the first lookup is in flight")
        model.setNetworkStateForTesting(cellular)
        await model.waitForNewAreaPassForTesting()
        XCTAssertEqual(lookups.all, [61], "62 is not looked up on cellular")
        XCTAssertEqual(newAreaGuesses(model), [])
        XCTAssertNil(NewAreaPrefetch.loadAnchor())

        lookups.held = []
        model.setNetworkStateForTesting(wifi)
        await model.waitForNewAreaPassForTesting()
        XCTAssertEqual(lookups.all, [61, 61, 62])
        XCTAssertEqual(newAreaGuesses(model), [61, 62])
        XCTAssertNotNil(NewAreaPrefetch.loadAnchor())
    }

    /// Played there since: a waiting area is dropped before any lookup.
    func testAWaitingAreaIsDroppedOncePlayedThere() {
        XCTAssertTrue(NewAreaPrefetch.isNewArea(latitude: away.latitude, longitude: away.longitude, courseIDs: [1], played: [homeCourse()], anchor: nil))
        let playedHere = MobileCourseOption(globalId: 1, name: "这里", roundCount: 1, teeBox: "white")
        XCTAssertFalse(NewAreaPrefetch.isNewArea(latitude: away.latitude, longitude: away.longitude, courseIDs: [1], played: [homeCourse(), playedHere], anchor: nil))
    }

    /// Back home while A's lookup is in flight: A's late completion queues, keeps and anchors
    /// nothing, and nothing is looked up afterwards.
    func testAPassForAnAreaLeftBehindQueuesNothing() async throws {
        let (model, lookups) = try newAreaModel(nearby: [(71, 0.4, 18), (72, 1.0, 18)])
        lookups.held = [71]
        model.publishOfflineStorageUsageForTesting(empty)
        model.setNetworkStateForTesting(wifi)

        _ = try await model.nearbyCourses(latitude: away.latitude, longitude: away.longitude, radiusKm: 5)
        for _ in 0..<2_000 where lookups.all.isEmpty { try await Task.sleep(nanoseconds: 1_000_000) }
        XCTAssertEqual(lookups.all, [71], "A's first lookup is in flight")

        // The same rows, answered at home: not a new area.
        lookups.held = []
        _ = try await model.nearbyCourses(latitude: home.latitude, longitude: home.longitude, radiusKm: 5)
        await model.waitForNewAreaPassForTesting()
        try await Task.sleep(nanoseconds: 2_000_000)
        model.publishOfflineStorageUsageForTesting(empty)
        await model.waitForNewAreaPassForTesting()

        XCTAssertEqual(newAreaGuesses(model), [])
        XCTAssertNil(NewAreaPrefetch.loadAnchor())
        XCTAssertEqual(lookups.all, [71], "A is not taken up again")
    }

    /// A → B while A's pass is in flight, with one of A's Tees already read: A's late completion
    /// queues none of it (taking none of B's room) and anchors nothing; B gets the room.
    func testAPassForAReplacedAreaTakesNoneOfTheNewAreasRoom() async throws {
        let (model, lookups) = try newAreaModel(nearby: [(71, 0.4, 18), (72, 1.0, 18)])
        lookups.held = [72]
        let course = SpeculativePrefetch.estimatedCourseBytes
        model.publishOfflineStorageUsageForTesting(
            OfflineStorageUsage(topoBytes: OfflineStorageEviction.capBytes - 2 * course, templateBytes: 0)
        )
        model.setNetworkStateForTesting(wifi)
        XCTAssertEqual(model.speculativeCourseRoomForTesting, 1, "the home course took one of the two")

        _ = try await model.nearbyCourses(latitude: away.latitude, longitude: away.longitude, radiusKm: 5)
        for _ in 0..<2_000 where lookups.all.count < 2 { try await Task.sleep(nanoseconds: 1_000_000) }
        XCTAssertEqual(lookups.all, [71, 72], "71's blue Tee is read; 72's lookup is in flight")

        // B is noted before A's pass can complete (this runs on the main actor first).
        let b = (latitude: 33.5, longitude: 121.0)
        model.noteNearbyCoursesForTesting(
            [MobileCourseSearchMatch(globalId: 81, name: "乙", holes: 18, city: nil, province: nil, ratio: 1, distanceKm: 0.4)],
            latitude: b.latitude,
            longitude: b.longitude
        )
        await model.waitForNewAreaPassForTesting()

        XCTAssertEqual(newAreaGuesses(model), [81], "A's 71 took none of B's room")
        XCTAssertEqual(lookups.all, [71, 72, 81])
        XCTAssertEqual(NewAreaPrefetch.loadAnchor()?.latitude, b.latitude, "B is taken, A is not")
    }
}

/// Answers 200 with the handler's JSON, or never answers when the handler returns nil (a download
/// that must stay in flight for the test's assertions), without blocking the loading thread.
private final class NewAreaURLProtocol: URLProtocol {
    static var handler: ((URLRequest) -> String?)?

    override class func canInit(with request: URLRequest) -> Bool { true }
    override class func canonicalRequest(for request: URLRequest) -> URLRequest { request }

    override func startLoading() {
        guard let url = request.url, let body = Self.handler?(request) else { return }
        let response = HTTPURLResponse(url: url, statusCode: 200, httpVersion: nil, headerFields: ["Content-Type": "application/json"])!
        client?.urlProtocol(self, didReceive: response, cacheStoragePolicy: .notAllowed)
        client?.urlProtocol(self, didLoad: Data(body.utf8))
        client?.urlProtocolDidFinishLoading(self)
    }

    override func stopLoading() {}
}
