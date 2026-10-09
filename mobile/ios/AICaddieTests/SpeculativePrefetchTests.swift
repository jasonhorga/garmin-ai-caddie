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
    }

    override func tearDownWithError() throws {
        try? FileManager.default.removeItem(at: directory)
        UserDefaults.standard.removeObject(forKey: SpeculativePrefetchSettings.cellularKey)
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
    private let cellular = SpeculativeNetworkState(isSatisfied: true, isExpensive: true, isConstrained: false)

    func testASpeculativeJobWaitsForWiFiUnlessCellularIsAllowed() throws {
        let guess = PrepCourseDownloadRecord(course: course(1, rounds: 3), teeBox: "blue", updatedAt: now, isSpeculative: true)
        let model = try model(rows: [guess])
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
        model.setNetworkStateForTesting(wifi)

        XCTAssertEqual(model.nextPrepCourseDownloadJobIDForTesting, asked.id)
        XCTAssertTrue(model.prepCourseDownloads.contains { $0.id == guess.id && $0.isSpeculative })
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
}
