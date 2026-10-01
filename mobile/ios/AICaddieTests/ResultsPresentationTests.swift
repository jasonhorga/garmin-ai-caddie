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
}
