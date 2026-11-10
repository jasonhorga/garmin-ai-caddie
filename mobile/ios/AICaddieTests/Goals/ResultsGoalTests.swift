// size: medium
// goals: I-14
import Foundation
#if canImport(FoundationNetworking)
import FoundationNetworking
#endif
import XCTest
@testable import AICaddie

/// I-14: the results (成绩), stats (统计) and round review (复盘) pages show exactly the numbers the
/// server sent, and a failed or malformed answer still leaves a usable page instead of a blank one.
/// The server is faked at the URLProtocol edge; the real SyncClient fetches, the real load states
/// and the real presentation helpers the views render are exercised.
@MainActor
final class ResultsGoalTests: XCTestCase {
    private var scope: CapturingURLProtocolScope?
    private var savedPlayerScope: (() -> String)!

    override func setUp() {
        super.setUp()
        let base = FileManager.default.temporaryDirectory
            .appendingPathComponent("results-goal-\(UUID().uuidString)", isDirectory: true)
        savedPlayerScope = RoundReviewDiskCache.currentPlayerScope
        RoundReviewDiskCache.rootOverride = base.appendingPathComponent("support", isDirectory: true)
        RoundReviewDiskCache.legacyRootOverride = base.appendingPathComponent("caches", isDirectory: true)
        RoundReviewDiskCache.currentPlayerScope = { "player-goal" }
    }

    override func tearDown() {
        RoundReviewDiskCache.rootOverride = nil
        RoundReviewDiskCache.legacyRootOverride = nil
        RoundReviewDiskCache.currentPlayerScope = savedPlayerScope
        scope = nil
        super.tearDown()
    }

    // goals: I-14 [main]
    func testResultsAndStatsPagesShowTheServerNumbers() async throws {
        let recorder = ResultsRequestRecorder()
        let client = makeClient(recorder: recorder) { request in
            switch request.url?.path {
            case "/api/v2/history/stats/mobile": return resultsResponse(request, body: resultsStatsJSON)
            case "/api/v2/history/rounds": return resultsResponse(request, body: resultsArchiveJSON)
            default: return resultsResponse(request, status: 404)
            }
        }

        var landing = ResultsLandingLoad()
        let generation = landing.begin()
        XCTAssertEqual(landing.phase, .loading)
        let statsOutcome = await ResultsFreshLoad.stats(client, store: nil)
        let archiveOutcome = await ResultsFreshLoad.archive(client, store: nil)
        guard case .answer(let statsAnswer) = statsOutcome, let stats = statsAnswer else {
            return XCTFail("stats did not load: \(statsOutcome)")
        }
        guard case .answer(let archiveAnswer) = archiveOutcome, let archive = archiveAnswer else {
            return XCTFail("archive did not load: \(archiveOutcome)")
        }
        XCTAssertTrue(landing.completeStats(generation, stats))
        XCTAssertTrue(landing.completeArchive(generation, archive))
        XCTAssertEqual(landing.phase, .content(notice: nil, refreshing: false))
        XCTAssertNil(landing.errorText)

        let urls = recorder.urls
        let statsURL = try XCTUnwrap(urls.first { $0.path == "/api/v2/history/stats/mobile" })
        XCTAssertNil(statsURL.query, "the landing page asks for the whole career window")
        let roundsURL = try XCTUnwrap(urls.first { $0.path == "/api/v2/history/rounds" })
        XCTAssertEqual(resultsQuery(roundsURL)["limit"], "2000")

        // Career summary: every number is the server's.
        let summary = try XCTUnwrap(landing.stats?.summary)
        XCTAssertEqual(summary.totalRounds, 42)
        XCTAssertEqual(summary.eighteenHoleRounds, 40)
        XCTAssertEqual(summary.nineHoleRounds, 2)
        XCTAssertEqual(summary.courseCount, 7)
        XCTAssertEqual(summary.average18, 88.4)
        XCTAssertEqual(summary.recent10Average, 86.3)
        XCTAssertEqual(summary.recent20Average, 87.15)
        XCTAssertEqual(summary.bestScore, 79)
        XCTAssertEqual(summary.worstScore, 101)
        XCTAssertEqual(summary.handicapEstimate, 15.2)
        XCTAssertEqual(summary.handicapTrend, -0.8)

        // Trend: the scored rounds in server order, with a 10-round rolling average of those scores.
        let trend = ResultsPresentation.trendRows(stats.trend?.points ?? [])
        XCTAssertEqual(trend.map(\.score), [90, 88, 92, 85, 87, 91, 89, 86, 84, 88, 83, 85])
        XCTAssertEqual(trend.map(\.roundId), (1...12).map { Optional("r\($0)") })
        XCTAssertEqual(trend.first?.rollingAverage, 90)
        XCTAssertEqual(trend[1].rollingAverage, 89)
        XCTAssertEqual(try XCTUnwrap(trend.last?.rollingAverage), 87.0, accuracy: 0.0001)

        // Score distribution and per-par rows.
        let scoring = try XCTUnwrap(stats.scoring)
        let outcomes = ResultsPresentation.outcomeSegments(scoring.outcomeDistribution)
        XCTAssertEqual(outcomes.map(\.label), ["老鹰", "小鸟", "标准杆", "柏忌", "双柏忌+"])
        XCTAssertEqual(outcomes.map(\.pct), [0, 5.5, 30.0, 40.5, 24.0])
        let par4 = try XCTUnwrap(scoring.byPar.first)
        let parText = ResultsPresentation.parRow(par4, maxOver: 0.62)
        XCTAssertEqual(parText.title, "Par 4")
        XCTAssertEqual(parText.overPar, "+0.62")
        XCTAssertEqual(parText.detail, "288 洞 · 保帕率 48%")

        // Performance analysis: each phase's big number comes from the server's counts.
        let analysis = ResultsPresentation.analysis(stats, baseline: ResultsPresentation.baseline(stats))
        XCTAssertEqual(analysis.rows.map(\.title), ["开球", "攻果岭", "果岭周边", "推杆"])
        XCTAssertEqual(analysis.rows.map(\.value), ["45", "33", "42", "1.85"])
        let tee = try XCTUnwrap(analysis.rows.first)
        XCTAssertEqual(tee.segments.map(\.label), ["偏左", "球道", "偏右"])
        XCTAssertEqual(tee.segments.map { $0.pct.rounded() }, [35, 45, 20])
        XCTAssertEqual(analysis.focus, ResultsPresentation.Focus(title: "开球偏左", detail: "35% 的开球偏左，是最常见的失误"))

        // Round archive: the cards carry the server's totals and per-hole strip.
        let shownArchive = try XCTUnwrap(landing.archive)
        XCTAssertEqual(shownArchive.total, 42)
        XCTAssertEqual(shownArchive.availableYears, ["2026"])
        let group = try XCTUnwrap(shownArchive.groups.first)
        XCTAssertEqual(group.label, "2026年11月")
        XCTAssertEqual(group.average18, 86.5)
        XCTAssertEqual(group.bestScore, 85)
        XCTAssertEqual(group.rounds.map(\.id), ["round-a", "round-b"])
        XCTAssertEqual(group.rounds.map(\.score), [85, 88])
        XCTAssertEqual(group.rounds.map(\.toPar), [13, 16])
        XCTAssertEqual(group.rounds.map(\.courseName), ["湖畔球场", "未知球场"])
        XCTAssertEqual(group.rounds.first?.scoreStrip.map(\.score), [5, 3])
        XCTAssertEqual(group.rounds.first?.scoreStrip.map(\.toPar), [1, 0])
    }

    // goals: I-14
    func testStatsWindowShowsTheNumbersOfTheWindowItAskedFor() async throws {
        let recorder = ResultsRequestRecorder()
        let client = makeClient(recorder: recorder) { request in
            resultsResponse(request, body: resultsStatsJSON)
        }
        var state = AnalysisLoadState(window: "last20")
        let stale = state.currentRequest
        let request = state.select("last10")
        XCTAssertEqual(state.phase, .loading)

        let stats = try? await client.fetchMobileStats(window: request.window)

        let url = try XCTUnwrap(recorder.urls.last)
        XCTAssertEqual(url.path, "/api/v2/history/stats/mobile")
        XCTAssertEqual(resultsQuery(url)["window"], "last10")
        let loaded = try XCTUnwrap(stats)
        XCTAssertFalse(state.complete(stale, stats: loaded), "an answer for the old window is not shown under the new label")
        XCTAssertEqual(state.phase, .loading)
        XCTAssertTrue(state.complete(request, stats: loaded))
        XCTAssertEqual(state.phase, .loaded(loaded))
        XCTAssertEqual(state.window, "last10")
        XCTAssertEqual(ResultsPresentation.analysis(loaded).rows.map(\.value), ["45", "33", "42", "1.85"])
    }

    // goals: I-14
    func testAMalformedSectionStillShowsTheRestOfTheStatsPage() async throws {
        let client = makeClient(recorder: ResultsRequestRecorder()) { request in
            switch request.url?.path {
            case "/api/v2/history/stats/mobile": return resultsResponse(request, body: resultsMalformedStatsJSON)
            case "/api/v2/history/rounds": return resultsResponse(request, body: resultsArchiveJSON)
            default: return resultsResponse(request, status: 404)
            }
        }

        var landing = ResultsLandingLoad()
        let generation = landing.begin()
        let statsOutcome = await ResultsFreshLoad.stats(client, store: nil)
        guard case .answer(let answer) = statsOutcome, let stats = answer else {
            return XCTFail("one bad section must not fail the whole stats page: \(statsOutcome)")
        }
        landing.completeStats(generation, stats)
        landing.completeArchive(generation, nil)

        XCTAssertNil(stats.diagnosis)
        XCTAssertTrue(stats.clubs.isEmpty)
        XCTAssertTrue(stats.courses.isEmpty)
        XCTAssertEqual(ResultsPresentation.trendRows(stats.trend?.points ?? []), [])
        XCTAssertEqual(stats.summary?.totalRounds, 42)
        XCTAssertEqual(stats.summary?.bestScore, 79)
        let scoring = try XCTUnwrap(stats.scoring)
        XCTAssertTrue(scoring.byPar.isEmpty, "the malformed per-par section is dropped, not shown as zeros")
        let analysis = ResultsPresentation.analysis(stats)
        XCTAssertEqual(analysis.rows.map(\.title), ["开球", "攻果岭", "果岭周边", "推杆"])
        XCTAssertEqual(analysis.rows.map(\.value), ["45", "33", "42", "1.85"])
        XCTAssertEqual(landing.phase, .content(notice: "球局档案暂时取不到", refreshing: false))
    }

    // goals: I-14
    func testStatsFailureKeepsTheArchiveAndNamesTheMissingSection() async throws {
        let client = makeClient(recorder: ResultsRequestRecorder()) { request in
            switch request.url?.path {
            case "/api/v2/history/stats/mobile": return resultsResponse(request, status: 500, body: #"{"detail":"model failed"}"#)
            case "/api/v2/history/rounds": return resultsResponse(request, body: resultsArchiveJSON)
            default: return resultsResponse(request, status: 404)
            }
        }

        var landing = ResultsLandingLoad()
        let generation = landing.begin()
        let statsOutcome = await ResultsFreshLoad.stats(client, store: nil)
        let archiveOutcome = await ResultsFreshLoad.archive(client, store: nil)
        guard case .answer(let statsAnswer) = statsOutcome else { return XCTFail("\(statsOutcome)") }
        guard case .answer(let archiveAnswer) = archiveOutcome else { return XCTFail("\(archiveOutcome)") }
        XCTAssertNil(statsAnswer)
        landing.completeStats(generation, statsAnswer)
        landing.completeArchive(generation, archiveAnswer)

        XCTAssertEqual(landing.phase, .content(notice: "生涯与趋势暂时取不到", refreshing: false))
        XCTAssertEqual(landing.archive?.total, 42)
        XCTAssertEqual(landing.archive?.groups.first?.rounds.map(\.score), [85, 88])

        var analysis = AnalysisLoadState(window: "last20")
        let request = analysis.currentRequest
        analysis.complete(request, stats: statsAnswer)
        XCTAssertEqual(analysis.phase, .failed("统计暂时取不到(网络或数据)"))

        var nothing = ResultsLandingLoad()
        let second = nothing.begin()
        nothing.completeStats(second, nil)
        nothing.completeArchive(second, nil)
        XCTAssertEqual(nothing.phase, .failed("生涯与趋势、球局档案暂时取不到"))
    }

    // goals: I-14
    func testRoundReviewNumbersMatchTheServerScorecard() async throws {
        let recorder = ResultsRequestRecorder()
        let body = try resultsRoundDetailJSON()
        let client = makeClient(recorder: recorder) { request in
            request.url?.path == "/api/v2/history/rounds/round-a"
                ? resultsResponse(request, body: body)
                : resultsResponse(request, status: 404)
        }

        let outcome = await RoundReviewFreshLoad.detail(
            client, roundRef: "round-a", globalId: 501, backGlobalId: nil, nine: nil, teeBox: "blue"
        )
        guard case .answer(let answer) = outcome, let detail = answer else {
            return XCTFail("round detail did not load: \(outcome)")
        }
        let url = try XCTUnwrap(recorder.urls.last)
        XCTAssertEqual(resultsQuery(url)["global_id"], "501")
        XCTAssertEqual(resultsQuery(url)["tee_box"], "blue")

        XCTAssertTrue(detail.found)
        XCTAssertEqual(detail.round?.score, 85)
        XCTAssertEqual(detail.round?.toPar, 13)
        let card = RoundReviewScorecard(detail.scorecard)
        XCTAssertEqual(card.holes.map(\.number), Array(1...18))
        XCTAssertEqual(card.holes.map(\.par), resultsPars)
        XCTAssertEqual(card.strokes, 85)
        XCTAssertEqual(card.nineTotal(card.holes.prefix(9)), 42)
        XCTAssertEqual(card.nineTotal(card.holes.dropFirst(9)), 43)
        XCTAssertEqual(card.nineLabels?.front, "前九")
        XCTAssertEqual(card.nineLabels?.back, "后九")
        XCTAssertEqual(card.cumulativeToPar, [1, 1, 2, 2, 4, 5, 5, 6, 6, 6, 7, 8, 8, 9, 9, 11, 12, 13])
        XCTAssertEqual(card.scores[5]?.putts, 3)
        XCTAssertEqual(card.scores[16]?.penalties, 2)

        XCTAssertEqual(RoundReviewContent.reviewMetrics(detail), [
            RoundReviewContent.ReviewMetric(id: "fairway", title: "球道命中", value: "57%", detail: "8/14"),
            RoundReviewContent.ReviewMetric(id: "gir", title: "GIR 上果岭", value: "39%", detail: "7/18"),
            RoundReviewContent.ReviewMetric(id: "putts", title: "推杆", value: "36", detail: "2.0/洞"),
            RoundReviewContent.ReviewMetric(id: "penalties", title: "罚杆", value: "3", detail: nil),
        ])
    }

    // goals: I-14
    func testRoundReviewFallsBackToPhaseTotalsAndOmitsMissingTiles() async throws {
        let body = #"""
        {"roundRef":"round-p","found":true,
         "round":{"score":40,"par":36,"toPar":4},
         "scorecard":[{"hole":1,"par":4,"score":5},{"hole":2,"par":3,"score":4},{"hole":3,"par":5,"score":"bad"}],
         "phaseSummary":[
           {"phase":"Tee","metrics":{"fairwaysHit":5,"fairwaysRecorded":10}},
           {"phase":"putting","metrics":{"totalPutts":33}},
           {"phase":"approach","metrics":{"gir":2,"girRecorded":0}}
         ],
         "missingData":"garbage"}
        """#
        let client = makeClient(recorder: ResultsRequestRecorder()) { request in
            resultsResponse(request, body: body)
        }

        let outcome = await RoundReviewFreshLoad.detail(
            client, roundRef: "round-p", globalId: nil, backGlobalId: nil, nine: nil, teeBox: nil
        )
        guard case .answer(let answer) = outcome, let detail = answer else {
            return XCTFail("a partly malformed round must still load: \(outcome)")
        }
        XCTAssertTrue(detail.missingData.isEmpty)
        XCTAssertEqual(detail.scorecard.map(\.score), [5, 4, nil])
        XCTAssertEqual(RoundReviewContent.reviewMetrics(detail), [
            RoundReviewContent.ReviewMetric(id: "fairway", title: "球道命中", value: "50%", detail: "5/10"),
            RoundReviewContent.ReviewMetric(id: "putts", title: "推杆", value: "33", detail: nil),
        ], "a phase without recorded facts is left out, never shown as 0%")
        let card = RoundReviewScorecard(detail.scorecard)
        XCTAssertEqual(card.strokes, 9)
        XCTAssertEqual(card.cumulativeToPar, [1, 2])
    }

    // goals: I-14
    func testRoundReviewFailureIsNoAnswerNotAnEmptyRound() async throws {
        let client = makeClient(recorder: ResultsRequestRecorder()) { request in
            resultsResponse(request, status: 404, body: #"{"detail":"not found"}"#)
        }

        let outcome = await RoundReviewFreshLoad.detail(
            client, roundRef: "round-missing", globalId: nil, backGlobalId: nil, nine: nil, teeBox: nil
        )

        guard case .answer(let answer) = outcome else { return XCTFail("\(outcome)") }
        XCTAssertNil(answer, "a failed load is reported as failed, not as a round with zero strokes")
    }

    // goals: I-14
    func testShotMapShowsTheServerShotsInOrder() async throws {
        let recorder = ResultsRequestRecorder()
        let body = #"""
        {"found":true,"hole":5,"par":4,"map":"garbage","manualPenalty":1,
         "shots":[
           {"id":"s:round-a:1","order":1,"club":"Driver","lie":"tee","start":[10,20],"end":[30,40]},
           {"id":"s:round-a:2","order":2,"club":"7I","lie":"fairway","start":[30,40],"end":[50,60]},
           {"id":"s:round-a:3","order":3,"club":"Putter","lie":"green"}
         ]}
        """#
        let client = makeClient(recorder: recorder) { request in
            resultsResponse(request, body: body)
        }

        let map = try await client.fetchRoundShotMap(roundRef: "round-a", hole: 5, globalId: 501)

        let url = try XCTUnwrap(recorder.urls.last)
        XCTAssertEqual(url.path, "/api/v2/history/rounds/round-a/holes/5/shotmap")
        XCTAssertEqual(resultsQuery(url)["includeImage"], "false")
        XCTAssertEqual(resultsQuery(url)["global_id"], "501")
        XCTAssertTrue(map.found)
        XCTAssertEqual(map.hole, 5)
        XCTAssertEqual(map.par, 4)
        XCTAssertNil(map.map, "a broken map image does not hide the shots")
        XCTAssertEqual(map.manualPenalty, 1)
        XCTAssertEqual(map.shots.map(\.id), ["s:round-a:1", "s:round-a:2", "s:round-a:3"])
        XCTAssertEqual(map.shots.map(\.order), [1, 2, 3])
        XCTAssertEqual(map.shots.map(\.club), ["Driver", "7I", "Putter"])
        XCTAssertEqual(map.shots.first?.end, [30, 40])
    }

    // MARK: helpers

    private func makeClient(
        recorder: ResultsRequestRecorder,
        handler: @escaping (URLRequest) throws -> (HTTPURLResponse, Data)
    ) -> SyncClient {
        let scope = CapturingURLProtocolScope { request in
            recorder.record(request)
            return try handler(request)
        }
        self.scope = scope
        return SyncClient(
            baseURL: URL(string: "https://example.test")!,
            session: URLSession(configuration: scope.configuration()),
            retrySleep: { _ in }
        )
    }
}

private final class ResultsRequestRecorder: @unchecked Sendable {
    private let lock = NSLock()
    private var stored: [URL] = []

    var urls: [URL] {
        lock.lock()
        defer { lock.unlock() }
        return stored
    }

    func record(_ request: URLRequest) {
        guard let url = request.url else { return }
        lock.lock()
        stored.append(url)
        lock.unlock()
    }
}

private func resultsResponse(_ request: URLRequest, status: Int = 200, body: String = "{}") -> (HTTPURLResponse, Data) {
    (
        HTTPURLResponse(
            url: request.url!,
            statusCode: status,
            httpVersion: nil,
            headerFields: ["Content-Type": "application/json"]
        )!,
        Data(body.utf8)
    )
}

private func resultsQuery(_ url: URL) -> [String: String] {
    let items = URLComponents(url: url, resolvingAgainstBaseURL: false)?.queryItems ?? []
    return Dictionary(items.map { ($0.name, $0.value ?? "") }, uniquingKeysWith: { _, last in last })
}

private let resultsTrendScores = [90, 88, 92, 85, 87, 91, 89, 86, 84, 88, 83, 85]

private var resultsTrendJSON: String {
    var points = resultsTrendScores.enumerated().map { index, score in
        #"{"date":"2026-10-\#(String(format: "%02d", index + 1))","score":\#(score),"toPar":\#(score - 72),"roundId":"r\#(index + 1)"}"#
    }
    points.insert(#"{"date":"2026-09-30","score":null,"roundId":"r0"}"#, at: 0)
    return "[" + points.joined(separator: ",") + "]"
}

private let resultsScoringJSON = #"""
"outcomeDistribution":[{"key":"birdie","pct":5.5},{"key":"par","pct":30.0},{"key":"bogey","pct":40.5},
  {"key":"double","pct":15.0},{"key":"triple","pct":9.0}],
"putting":{"holesWithPutts":360,"averagePutts":1.85,"onePuttPct":25.0,"twoPuttPct":65.0,"threePlusPuttPct":10.0},
"teeDirection":{"recorded":20,"hit":9,"left":7,"right":4},
"approachMiss":{"recorded":18,"gir":6,"short":5,"long":2,"left":3,"right":2},
"scrambling":{"chances":12,"saves":5,"pct":41.7}
"""#

private let resultsSummaryJSON = #"""
"summary":{"totalRounds":42,"eighteenHoleRounds":40,"nineHoleRounds":2,"courseCount":7,"average18":88.4,
  "median18":88.0,"recent10Average":86.3,"recent20Average":87.15,"bestScore":79,"worstScore":101,
  "handicapEstimate":15.2,"handicapTrend":-0.8}
"""#

private var resultsStatsJSON: String {
    """
    {\(resultsSummaryJSON),
     "scoring":{\(resultsScoringJSON),
       "byPar":[{"key":"par4","label":"Par 4","par":4,"holeCount":288,"averageToPar":0.62,"parOrBetterPct":48.4}]},
     "trend":{"points":\(resultsTrendJSON)},
     "courses":[],"clubs":[]}
    """
}

/// The same numbers with several sections the server got wrong (the stats model failing on part of
/// the payload): those sections drop out, the rest of the page keeps the server's numbers.
private var resultsMalformedStatsJSON: String {
    """
    {\(resultsSummaryJSON),
     "scoring":{\(resultsScoringJSON),
       "byPar":[{"par":"four","holeCount":"many"}],"hardestHoles":"oops"},
     "trend":{"points":"not-a-list"},
     "diagnosis":"model unavailable",
     "courses":{"broken":true},"clubs":7}
    """
}

private let resultsArchiveJSON = #"""
{"total":42,
 "groups":[{"key":"2026-11","label":"2026年11月","count":2,"average18":86.5,"bestScore":85,"rounds":[
   {"id":"round-a","date":"2026-11-02","courseName":"湖畔球场","holesCompleted":18,"score":85,"par":72,"toPar":13,
    "scoreStrip":[{"hole":1,"par":4,"score":5,"toPar":1},{"hole":2,"par":3,"score":3,"toPar":0}]},
   {"id":"round-b","date":"2026-11-01","holesCompleted":18,"score":88,"par":72,"toPar":16}
 ]}],
 "availableYears":["2026"],
 "availableCourses":[{"key":"lake","label":"湖畔球场"}]}
"""#

private let resultsPars = [4, 4, 3, 5, 4, 4, 3, 4, 5, 4, 3, 4, 5, 4, 4, 3, 5, 4]

/// An 18-hole round: front 42, back 43 (85, +13); 36 putts; 3 penalty strokes; 8 of 14 fairways;
/// 7 of 18 greens in regulation.
private func resultsRoundDetailJSON() throws -> String {
    let overs = [1, 0, 1, 0, 2, 1, 0, 1, 0, 0, 1, 1, 0, 1, 0, 2, 1, 1]
    let putts = [2, 2, 1, 2, 3, 2, 2, 2, 2, 2, 2, 2, 1, 2, 2, 3, 2, 2]
    let penalties: [Int: Int] = [5: 1, 16: 2]
    let fairways: [Int: String] = [
        1: "hit", 2: "left", 4: "hit", 5: "right", 6: "hit", 8: "hit", 9: "left", 10: "hit",
        12: "hit", 13: "left", 14: "hit", 15: "hit", 17: "right", 18: "left",
    ]
    let girs: Set<Int> = [2, 3, 7, 9, 10, 13, 14]
    let holes: [[String: Any]] = (1...18).map { hole in
        var row: [String: Any] = [
            "hole": hole,
            "par": resultsPars[hole - 1],
            "score": resultsPars[hole - 1] + overs[hole - 1],
            "toPar": overs[hole - 1],
            "putts": putts[hole - 1],
            "penalties": penalties[hole] ?? 0,
            "gir": girs.contains(hole),
        ]
        if let fairway = fairways[hole] { row["fairway"] = fairway }
        return row
    }
    let payload: [String: Any] = [
        "roundRef": "round-a",
        "found": true,
        "title": "湖畔球场",
        "round": ["courseName": "湖畔球场", "date": "2026-11-02", "score": 85, "par": 72, "toPar": 13, "holesCompleted": 18],
        "scorecard": holes,
        "phaseSummary": [
            ["phase": "tee", "metrics": ["fairwaysHit": 1, "fairwaysRecorded": 1]],
            ["phase": "putting", "metrics": ["totalPutts": 99]],
        ],
        "missingData": [],
    ]
    let data = try JSONSerialization.data(withJSONObject: payload)
    return String(decoding: data, as: UTF8.self)
}
