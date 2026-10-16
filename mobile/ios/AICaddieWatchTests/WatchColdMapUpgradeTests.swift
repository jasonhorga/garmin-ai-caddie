import XCTest
@testable import AICaddieWatch

/// #425 review: the active round's map upgrade against what production actually answers.
@MainActor
final class WatchColdMapUpgradeTests: XCTestCase {
    private final class Log {
        var fullPackages = 0
        var mapOnlyPackages = 0
        var statusReads = 0
        var refuseStatus = true
    }

    private let option = WatchCourseOption(globalId: 31669, name: "北京丽宫", holes: 18, teeBox: "Blue")

    private func makeLibrary(log: Log, status: @escaping (Int) -> (Int, String)) -> WatchCourseLibrary {
        let directory = FileManager.default.temporaryDirectory
            .appendingPathComponent("cold-map-\(UUID().uuidString)", isDirectory: true)
        addTeardownBlock { try? FileManager.default.removeItem(at: directory) }
        // A course whose holes stay pending: no attempt ever completes, so every attempt is counted.
        let package = WatchPackageFixture.packageData(
            roundId: "watch-cold",
            course: #"{"globalId":31669,"name":"北京丽宫","teeBox":"Blue"}"#,
            loops: [.init(31669, "front")]
        )
        return WatchCourseLibrary(
            store: WatchCourseStore(directoryURL: directory),
            imageStore: WatchHoleImageStore(directoryURL: directory),
            makeRoundId: { "watch-cold" },
            now: { "2026-10-15T00:00:00Z" },
            clientFactory: { config in
                WatchBackendClient(
                    baseURL: config.baseURL,
                    sessionToken: config.sessionToken,
                    dataLoader: { request in
                        let url = try XCTUnwrap(request.url)
                        func reply(_ code: Int, _ body: Data) -> (Data, URLResponse) {
                            (body, HTTPURLResponse(url: url, statusCode: code, httpVersion: nil,
                                                   headerFields: ["Content-Type": "application/json"])!)
                        }
                        if url.path.hasSuffix("/package") {
                            if url.query?.contains("map_only=true") == true {
                                log.mapOnlyPackages += 1
                            } else {
                                log.fullPackages += 1
                            }
                            return reply(200, package)
                        }
                        if url.path.hasSuffix("/install/status") {
                            log.statusReads += 1
                            let (code, body) = status(log.statusReads)
                            return reply(code, Data(body.utf8))
                        }
                        return reply(404, Data(#"{"detail":"not found"}"#.utf8))
                    },
                    retrySleep: { _ in }
                )
            },
            retrySleep: { _ in }
        )
    }

    private var config: WatchRoundConfig { config(token: "player") }

    private func config(token: String) -> WatchRoundConfig {
        WatchRoundConfig(baseURL: URL(string: "https://caddie.example")!, adminToken: nil, sessionToken: token)
    }

    private func statusBody(geometryReady: Int) -> String {
        #"{"schema":"ai-caddie-course-install-status-v1","jobId":"j","globalId":31669,"teeBox":"Blue","loopKey":"31669:front","phase":"running","stage":"geometry","generation":1,"totalHoles":9,"#
            + #""geometryReady":\#(geometryReady),"topoReady":0,"holes":[]}"#
    }

    /// The player token gets 403 from the install journal in production: it is asked once, and the
    /// status-only phase then fetches the package every third minute, not every minute.
    func testAForbiddenInstallJournalIsAskedOnceAndDoesNotForceAFullFetchEveryMinute() async {
        let log = Log()
        let library = makeLibrary(log: log) { _ in (403, #"{"detail":"admin token required"}"#) }
        let selection = WatchCourseSelection(front: option, teeBox: "Blue", firstHalf: "front")
        let result = await library.upgradeCourseWhenReady(
            selection, roundId: "watch-cold", config: config, onProgress: { _ in }
        )
        XCTAssertNil(result)
        XCTAssertEqual(log.statusReads, 1, "a refused journal is not asked again")
        XCTAssertEqual(log.mapOnlyPackages, 1, "the factual first map is asked for once, first")
        // Six full attempts, then attempts 6, 9, …, 27: fourteen instead of thirty.
        XCTAssertEqual(log.fullPackages, 14)
        XCTAssertTrue(library.preciseUpgradePaused)
    }

    /// #425 review P2: a 403 is remembered for that course and credential only. Another course in the
    /// same Watch process, or the same course after the credential is refreshed, asks the journal again;
    /// the original course and credential keep the bounded fallback.
    func testARefusedJournalIsScopedToTheCourseAndCredential() async {
        let log = Log()
        let library = makeLibrary(log: log) { _ in
            log.refuseStatus ? (403, #"{"detail":"admin token required"}"#) : (200, self.statusBody(geometryReady: 0))
        }
        let courseA = WatchCourseSelection(front: option, teeBox: "Blue", firstHalf: "front")
        let courseB = WatchCourseSelection(
            front: WatchCourseOption(globalId: 31670, name: "北京丽宫 B", holes: 9, teeBox: "Blue"),
            teeBox: "Blue"
        )

        _ = await library.upgradeCourseWhenReady(courseA, roundId: "watch-cold", config: config, onProgress: { _ in })
        XCTAssertEqual(log.statusReads, 1)
        XCTAssertTrue(library.installStatusForbidden(selection: courseA, config: config))

        // Course B answers 200: it is asked on every status-only attempt, not skipped because of A.
        log.refuseStatus = false
        var before = log.statusReads
        _ = await library.upgradeCourseWhenReady(courseB, roundId: "watch-cold", config: config, onProgress: { _ in })
        XCTAssertGreaterThan(log.statusReads - before, 1, "another course asks its own journal")
        XCTAssertFalse(library.installStatusForbidden(selection: courseB, config: config))

        // Course A with the same credential keeps the bounded fallback: no further status reads.
        before = log.statusReads
        _ = await library.upgradeCourseWhenReady(courseA, roundId: "watch-cold", config: config, onProgress: { _ in })
        XCTAssertEqual(log.statusReads, before, "the refused course and credential are not asked again")

        // A refreshed credential probes course A again.
        let refreshed = config(token: "player-refreshed")
        before = log.statusReads
        _ = await library.upgradeCourseWhenReady(courseA, roundId: "watch-cold", config: refreshed, onProgress: { _ in })
        XCTAssertGreaterThan(log.statusReads - before, 1, "a refreshed credential asks again")
        XCTAssertFalse(library.installStatusForbidden(selection: courseA, config: refreshed))
    }

    /// An authorised journal: after the six full attempts the package is fetched again only when a
    /// hole's vector geometry (not only its raster) became ready.
    func testVectorProgressAloneTriggersTheNextPackageFetch() async {
        let log = Log()
        let library = makeLibrary(log: log) { read in
            (200, self.statusBody(geometryReady: read >= 11 ? 1 : 0))
        }
        let selection = WatchCourseSelection(front: option, teeBox: "Blue", firstHalf: "front")
        _ = await library.upgradeCourseWhenReady(
            selection, roundId: "watch-cold", config: config, onProgress: { _ in }
        )
        XCTAssertEqual(log.fullPackages, 7, "six full attempts, then one more when geometry 0 → 1")
    }
}
