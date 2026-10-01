@testable import AICaddie
import XCTest

/// B5 成绩 / 表现分析 / 成绩分布 facts (README §9).
final class ResultsPresentationTests: XCTestCase {
    private func stats(_ json: String) throws -> MobileStats {
        try JSONDecoder().decode(MobileStats.self, from: Data(json.utf8))
    }

    private func points(_ scores: [Int?]) throws -> [StatsTrendPoint] {
        let rows = scores.enumerated().map { index, score in
            #"{"date":"2026-01-\#(String(format: "%02d", index + 1))","score":\#(score.map(String.init) ?? "null"),"roundId":"r\#(index)"}"#
        }
        return try JSONDecoder().decode([StatsTrendPoint].self, from: Data("[\(rows.joined(separator: ","))]".utf8))
    }

    func testTrendShowsTheNewestTwentyRoundsWithAWholeSeriesTenRoundAverage() throws {
        let scores = (0..<25).map { 80 + $0 }
        let rows = ResultsPresentation.trendRows(try points(scores.map(Optional.init) + [nil]))
        XCTAssertEqual(rows.count, 20, "an unscored round is not a dot")
        XCTAssertEqual(rows.map(\.score), Array(scores.suffix(20)))
        XCTAssertEqual(rows.map(\.index), Array(0..<20))
        XCTAssertEqual(rows.first?.roundId, "r5")
        // The first shown dot (score 85) averages every earlier round of the series too (80...85),
        // not only the shown ones.
        XCTAssertEqual(try XCTUnwrap(rows.first?.rollingAverage), 82.5, accuracy: 1e-9)
        XCTAssertEqual(try XCTUnwrap(rows.last?.rollingAverage), Double((95...104).reduce(0, +)) / 10, accuracy: 1e-9)
        // Fewer than ten rounds: the average is over the rounds there are.
        let short = ResultsPresentation.trendRows(try points([90, 80]))
        XCTAssertEqual(short.map(\.rollingAverage), [90, 85])
    }

    func testScoreBinsAreFiveStrokesWideWithEmptyBinsAndTheMostCommonOneMarked() throws {
        let bins = ResultsPresentation.scoreBins(try points([78, 82, 84, 91, 93, 94, nil]))
        XCTAssertEqual(bins.map(\.lower), [75, 80, 85, 90])
        XCTAssertEqual(bins.map(\.count), [1, 2, 0, 3])
        XCTAssertEqual(bins.map(\.label), ["75–79", "80–84", "85–89", "90–94"])
        XCTAssertEqual(bins.filter(\.isMostCommon).map(\.lower), [90])
        XCTAssertEqual(bins[1].roundIds, ["r1", "r2"])
        // A tie marks the lower scores.
        XCTAssertEqual(ResultsPresentation.scoreBins(try points([80, 90])).filter(\.isMostCommon).map(\.lower), [80])
        XCTAssertEqual(ResultsPresentation.scoreBins([]), [])
    }

    func testOutcomeSegmentsFoldDoubleTripleAndWorseIntoOne() throws {
        let scoring = try stats(#"""
        {"scoring":{"outcomeDistribution":[{"key":"birdie","pct":5},{"key":"par","pct":40},{"key":"bogey","pct":35},
        {"key":"double","pct":12},{"key":"triple","pct":5},{"key":"quadPlus","pct":3}]}}
        """#).scoring
        let segments = ResultsPresentation.outcomeSegments(scoring?.outcomeDistribution ?? [])
        XCTAssertEqual(segments.map(\.label), ["老鹰", "小鸟", "标准杆", "柏忌", "双柏忌+"])
        XCTAssertEqual(segments.map(\.pct), [0, 5, 40, 35, 20])
        XCTAssertEqual(ResultsPresentation.outcomeSegments([]), [])
    }

    func testAnalysisWritesFourPhasesOneWayAndNamesTheMostCommonMiss() throws {
        let current = try stats(#"""
        {"summary":{"totalRounds":10},
         "scoring":{"teeDirection":{"recorded":100,"hit":50,"left":30,"right":20},
          "approachMiss":{"recorded":100,"gir":30,"short":38,"long":8,"left":12,"right":12},
          "scrambling":{"chances":50,"saves":12,"pct":24},
          "phaseStats":[{"phase":"Short Game","roughOrBunkerShots":34}],
          "putting":{"averagePutts":1.92,"holesWithPutts":180,"zeroPuttPct":2,"onePuttPct":19,"twoPuttPct":66,"threePlusPuttPct":13}}}
        """#)
        let baseline = try stats(#"""
        {"scoring":{"teeDirection":{"recorded":100,"hit":51,"left":25,"right":24},
          "approachMiss":{"recorded":100,"gir":27,"short":30},
          "scrambling":{"chances":50,"saves":12,"pct":24},
          "putting":{"averagePutts":1.86,"holesWithPutts":180}}}
        """#)
        let analysis = ResultsPresentation.analysis(current, baseline: baseline)
        XCTAssertEqual(analysis.rows.map(\.title), ["开球", "攻果岭", "果岭周边", "推杆"])
        XCTAssertEqual(analysis.rows.map(\.value), ["50", "30", "24", "1.92"])
        XCTAssertEqual(analysis.focus, ResultsPresentation.Focus(title: "攻果岭偏短", detail: "38% 的攻果岭落在果岭前面，是最常见的失误"))

        let tee = analysis.rows[0]
        XCTAssertEqual(tee.delta, ResultsPresentation.Delta(text: "↓ 1%", isBetter: false))
        XCTAssertEqual(tee.segments.map(\.label), ["偏左", "球道", "偏右"])
        XCTAssertEqual(tee.segments.map(\.tone), [.warn, .good, .neutral], "the larger miss is the yellow one")

        let approach = analysis.rows[1]
        XCTAssertEqual(approach.delta, ResultsPresentation.Delta(text: "↑ 3%", isBetter: true))
        XCTAssertEqual(approach.segments.map(\.label), ["上果岭", "短", "长", "左", "右"])
        XCTAssertEqual(approach.segments.map(\.tone), [.good, .warn, .neutral, .neutral, .neutral])

        let scramble = analysis.rows[2]
        XCTAssertEqual(scramble.delta, ResultsPresentation.Delta(text: "和之前持平", isBetter: nil))
        XCTAssertEqual(scramble.note, "每场从长草、沙坑起杆 3.4 次")

        let putting = analysis.rows[3]
        XCTAssertEqual(putting.delta, ResultsPresentation.Delta(text: "↑ 0.06", isBetter: false), "more putts is worse")
        XCTAssertEqual(putting.segments.map(\.label), ["零推", "一推", "两推", "三推+"])
        XCTAssertEqual(putting.segments.last?.tone, .warn)
    }

    func testAnalysisLeavesOutUnrecordedPhasesAndHasNoDeltaWithoutABaseline() throws {
        let current = try stats(#"""
        {"scoring":{"teeDirection":{"recorded":0},"approachMiss":{"recorded":20,"gir":10,"long":6,"short":4},
          "putting":{"averagePutts":2.0,"holesWithPutts":0}}}
        """#)
        let analysis = ResultsPresentation.analysis(current)
        XCTAssertEqual(analysis.rows.map(\.title), ["攻果岭"], "no recorded tee, scrambling or putts: no 0% rows")
        XCTAssertNil(analysis.rows[0].delta)
        XCTAssertEqual(analysis.focus?.title, "攻果岭偏长")
        XCTAssertEqual(ResultsPresentation.analysis(try stats("{}")), ResultsPresentation.Analysis(focus: nil, rows: []))
    }

    // MARK: 表现分析 load state (Codex review of #364, P1)

    func testASwitchedWindowNeverShowsTheOldWindowsDataAndOnlyItsOwnRequestWritesBack() throws {
        let twenty = try stats(#"{"summary":{"totalRounds":20}}"#)
        let ten = try stats(#"{"summary":{"totalRounds":10}}"#)
        let year = try stats(#"{"summary":{"totalRounds":31}}"#)
        var state = AnalysisLoadState()
        let first = state.currentRequest
        XCTAssertEqual(first, AnalysisLoadState.Request(window: "last20", generation: 0))
        XCTAssertTrue(state.complete(first, stats: twenty))
        XCTAssertEqual(state.phase, .loaded(twenty))

        // Switching shows loading at once: the 20-round numbers are gone under the "10 场" label.
        let toTen = state.select("last10")
        XCTAssertEqual(state.window, "last10")
        XCTAssertEqual(state.phase, .loading)
        // A fast second switch: the 10-round answer arrives late and is ignored.
        let toYear = state.select("12m")
        XCTAssertFalse(state.complete(toTen, stats: ten))
        XCTAssertEqual(state.phase, .loading)
        XCTAssertTrue(state.complete(toYear, stats: year))
        XCTAssertEqual(state.phase, .loaded(year))
        // An out-of-order stale answer after the current one cannot overwrite it either.
        XCTAssertFalse(state.complete(toTen, stats: ten))
        XCTAssertEqual(state.phase, .loaded(year))
    }

    func testAFailedWindowIsAFailureNotTheOldWindowsNumbers() throws {
        var state = AnalysisLoadState()
        XCTAssertTrue(state.complete(state.currentRequest, stats: try stats(#"{"summary":{"totalRounds":20}}"#)))
        let toTen = state.select("last10")
        XCTAssertTrue(state.complete(toTen, stats: nil))
        XCTAssertEqual(state.window, "last10")
        guard case .failed = state.phase else { return XCTFail("a failed 10-round request is a failure") }
    }

    func testARefreshInvalidatesTheCurrentWindowAndItsComparisonTogether() throws {
        let before = try stats(#"{"summary":{"totalRounds":10},"previous":{"window":"prev10","roundCount":10,"scoring":{}}}"#)
        let after = try stats(#"{"summary":{"totalRounds":10}}"#)
        var state = AnalysisLoadState(window: "last10")
        let first = state.currentRequest
        XCTAssertTrue(state.complete(first, stats: before))
        let refresh = state.refresh()
        XCTAssertEqual(refresh, AnalysisLoadState.Request(window: "last10", generation: 1))
        XCTAssertEqual(state.phase, .loading, "the stale window and its baseline are both gone")
        // The pre-refresh request answering late is ignored; the refreshed one wins.
        XCTAssertFalse(state.complete(first, stats: before))
        XCTAssertTrue(state.complete(refresh, stats: after))
        guard case .loaded(let loaded) = state.phase else { return XCTFail("refreshed stats load") }
        XCTAssertNil(ResultsPresentation.baseline(loaded), "the refreshed response has no previous period")
        XCTAssertNotNil(ResultsPresentation.baseline(before))
    }

    func testEachWindowComparesWithItsOwnPreviousPeriod() {
        XCTAssertEqual(AnalysisLoadState.windows.map(\.id), ["last10", "last20", "12m", "all"])
        XCTAssertEqual(AnalysisLoadState.comparisonLabel("last10"), "和前 10 场比")
        XCTAssertEqual(AnalysisLoadState.comparisonLabel("last20"), "和前 20 场比")
        XCTAssertEqual(AnalysisLoadState.comparisonLabel("12m"), "和前一年比")
        XCTAssertNil(AnalysisLoadState.comparisonLabel("all"))
    }

    func testAnalysisDeltasAreAgainstThePreviousPeriodTheResponseCarries() throws {
        // Prototype 近 10 场: tee hit 51 vs the 10 before at 52 -> ↓ 1%.
        let current = try stats(#"""
        {"scoring":{"teeDirection":{"recorded":100,"hit":51,"left":22,"right":27}},
         "previous":{"window":"prev10","roundCount":10,"scoring":{"teeDirection":{"recorded":100,"hit":52,"left":24,"right":24}}}}
        """#)
        let analysis = ResultsPresentation.analysis(current, baseline: ResultsPresentation.baseline(current))
        XCTAssertEqual(analysis.rows.first?.delta, ResultsPresentation.Delta(text: "↓ 1%", isBetter: false))
    }

    // MARK: 成绩 landing states (Codex review of #364)

    func testTheLandingNeverCallsAnUnansweredFirstLoadEmpty() throws {
        let loaded = try stats(#"{"summary":{"totalRounds":3}}"#)
        let archive = try JSONDecoder().decode(HistoryRoundsArchive.self, from: Data(#"{"total":3,"groups":[]}"#.utf8))
        let noRounds = try stats(#"{"summary":{"totalRounds":0}}"#)
        let noArchive = try JSONDecoder().decode(HistoryRoundsArchive.self, from: Data(#"{"total":0,"groups":[]}"#.utf8))
        typealias P = ResultsPresentation
        XCTAssertEqual(P.landingPhase(stats: nil, archive: nil, isLoading: true, errorText: nil), .loading)
        XCTAssertEqual(P.landingPhase(stats: nil, archive: nil, isLoading: false, errorText: "生涯与趋势、球局档案暂时取不到"),
                       .failed("生涯与趋势、球局档案暂时取不到"))
        XCTAssertEqual(P.landingPhase(stats: loaded, archive: archive, isLoading: true, errorText: nil),
                       .content(notice: nil, refreshing: true), "cached content stays while it refreshes")
        XCTAssertEqual(P.landingPhase(stats: loaded, archive: nil, isLoading: false, errorText: "球局档案暂时取不到"),
                       .content(notice: "球局档案暂时取不到", refreshing: false))
        XCTAssertEqual(P.landingPhase(stats: noRounds, archive: noArchive, isLoading: false, errorText: nil), .empty)
        // Zero rounds while one side is still loading is not yet "empty".
        XCTAssertEqual(P.landingPhase(stats: noRounds, archive: nil, isLoading: true, errorText: nil),
                       .content(notice: nil, refreshing: true))
    }

    // MARK: 成绩分布 · 按 Par (Codex review of #364)

    func testAParRowShowsMissingFieldsAsMissingNotZero() throws {
        let rows = try JSONDecoder().decode([StatsByPar].self, from: Data(#"""
        [{"par":3,"holeCount":4,"averageToPar":0.62,"parOrBetterPct":38},
         {"par":4,"averageToPar":0.44},
         {"par":5,"holeCount":4}]
        """#.utf8))
        let three = ResultsPresentation.parRow(rows[0], maxOver: 0.62)
        XCTAssertEqual(three.title, "Par 3")
        XCTAssertEqual(three.overPar, "+0.62")
        XCTAssertEqual(three.detail, "4 洞 · 保帕率 38%")
        XCTAssertEqual(try XCTUnwrap(three.fraction), 0.8, accuracy: 1e-9)
        XCTAssertEqual(ResultsPresentation.parRow(rows[1], maxOver: 0.62).detail, "", "no 0 洞, no 保帕率 0%")
        let five = ResultsPresentation.parRow(rows[2], maxOver: 0.62)
        XCTAssertEqual(five.overPar, "—")
        XCTAssertNil(five.fraction)
        XCTAssertEqual(five.detail, "4 洞")
    }

    // MARK: 成绩 landing load coordinator (Codex review of #364, round 2)

    private func archive(_ total: Int) throws -> HistoryRoundsArchive {
        try JSONDecoder().decode(HistoryRoundsArchive.self, from: Data(#"{"total":\#(total),"groups":[]}"#.utf8))
    }

    func testACachedPageIsGenuinelyRefreshingWhileItsRequestsRun() throws {
        let cached = try stats(#"{"summary":{"totalRounds":3}}"#)
        var load = ResultsLandingLoad()
        load.seed(stats: cached, archive: try archive(3))
        let generation = load.begin()
        XCTAssertTrue(load.isLoading)
        XCTAssertEqual(load.phase, .content(notice: nil, refreshing: true), "cache on screen, request running")
        // The archive answers first and is published at once; the page is still refreshing stats.
        XCTAssertTrue(load.completeArchive(generation, try archive(4)))
        XCTAssertEqual(load.archive?.total, 4)
        XCTAssertTrue(load.isLoading)
        XCTAssertTrue(load.completeStats(generation, try stats(#"{"summary":{"totalRounds":4}}"#)))
        XCTAssertFalse(load.isLoading)
        XCTAssertEqual(load.phase, .content(notice: nil, refreshing: false))
    }

    func testAnOlderLoadNeitherOverwritesANewerOneNorEndsItsLoading() throws {
        var load = ResultsLandingLoad()
        let first = load.begin()
        let second = load.begin() // pull-to-refresh while the first load runs
        XCTAssertFalse(load.completeStats(first, try stats(#"{"summary":{"totalRounds":1}}"#)))
        XCTAssertFalse(load.completeArchive(first, nil), "a stale failure is not reported either")
        XCTAssertNil(load.stats)
        XCTAssertNil(load.errorText)
        XCTAssertTrue(load.isLoading, "the older answer cannot clear the newer load")
        XCTAssertEqual(load.phase, .loading)
        XCTAssertTrue(load.completeStats(second, try stats(#"{"summary":{"totalRounds":2}}"#)))
        XCTAssertTrue(load.completeArchive(second, nil))
        XCTAssertEqual(load.stats?.summary?.totalRounds, 2)
        XCTAssertEqual(load.errorText, "球局档案暂时取不到")
        XCTAssertEqual(load.phase, .content(notice: "球局档案暂时取不到", refreshing: false))
    }

    func testAFailedRefreshKeepsTheCachedSectionAndNamesIt() throws {
        var load = ResultsLandingLoad(stats: try stats(#"{"summary":{"totalRounds":3}}"#), archive: try archive(3))
        let generation = load.begin()
        load.completeStats(generation, nil)
        load.completeArchive(generation, nil)
        XCTAssertEqual(load.stats?.summary?.totalRounds, 3)
        XCTAssertEqual(load.errorText, "生涯与趋势、球局档案暂时取不到")
        // A later successful refresh clears the notice.
        let next = load.begin()
        XCTAssertNil(load.errorText)
        load.completeStats(next, try stats(#"{"summary":{"totalRounds":3}}"#))
        load.completeArchive(next, try archive(3))
        XCTAssertEqual(load.phase, .content(notice: nil, refreshing: false))
    }

    func testACancelledLoadStopsLoadingWithoutCommittingAndFirstLoadIsNeverEmpty() throws {
        var load = ResultsLandingLoad()
        let generation = load.begin()
        XCTAssertEqual(load.phase, .loading, "first load with nothing cached is loading, never 暂无成绩")
        load.cancel(generation)
        XCTAssertFalse(load.isLoading)
        XCTAssertNil(load.stats)
        XCTAssertFalse(load.completeStats(generation, try stats("{}")), "a cancelled generation commits nothing")
        // A stale cancel cannot stop a newer load.
        let next = load.begin()
        load.cancel(generation)
        XCTAssertTrue(load.isLoading)
        XCTAssertTrue(load.completeStats(next, try stats(#"{"summary":{"totalRounds":0}}"#)))
        XCTAssertTrue(load.completeArchive(next, try archive(0)))
        XCTAssertEqual(load.phase, .empty)
    }

    // MARK: 和之前比 with a short previous sample (Codex review of #364, round 2)

    func testAShortPreviousCountSampleIsNamedNotLabelledAsTheFullWindow() throws {
        let short = try JSONDecoder().decode(MobileStatsPrevious.self, from: Data(#"{"window":"prev10","roundCount":5,"requiredRounds":10}"#.utf8))
        let full = try JSONDecoder().decode(MobileStatsPrevious.self, from: Data(#"{"window":"prev10","roundCount":10,"requiredRounds":10,"scoring":{}}"#.utf8))
        let year = try JSONDecoder().decode(MobileStatsPrevious.self, from: Data(#"{"window":"prev12m","roundCount":3,"scoring":{}}"#.utf8))
        XCTAssertEqual(AnalysisLoadState.comparisonNote(window: "last10", previous: short), "前 10 场只有 5 场，暂不比较")
        XCTAssertEqual(AnalysisLoadState.comparisonNote(window: "last10", previous: full), "↑ ↓ 和前 10 场比")
        XCTAssertEqual(AnalysisLoadState.comparisonNote(window: "12m", previous: year), "↑ ↓ 和前一年比")
        XCTAssertEqual(AnalysisLoadState.comparisonNote(window: "last20", previous: nil), "前一段没有球局，暂不比较")
        XCTAssertNil(AnalysisLoadState.comparisonNote(window: "all", previous: full))
        // No scoring, no baseline: the short sample never feeds a delta.
        let current = try stats(#"{"previous":{"window":"prev10","roundCount":5,"requiredRounds":10}}"#)
        XCTAssertNil(ResultsPresentation.baseline(current))
    }
}
