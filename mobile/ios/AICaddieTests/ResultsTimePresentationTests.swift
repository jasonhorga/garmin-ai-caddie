@testable import AICaddie
import XCTest

/// B5b 时间与频率 (README §9, `stats.html` 4).
final class ResultsTimePresentationTests: XCTestCase {
    private func stats(_ json: String) throws -> MobileStats {
        try JSONDecoder().decode(MobileStats.self, from: Data(json.utf8))
    }

    private let fixture = #"""
    {"trend":{"points":[{"date":"2026-05-01","score":90,"roundId":"a"},{"date":"2026-05-09","score":null,"roundId":"b"},
     {"date":"2026-06-01","score":86,"roundId":"c"}]},
     "time":{
      "byYear":[{"key":"2026","roundCount":12,"average18":88.4,"bestScore":82,"worstScore":96,"outcomes":{"birdie":6,"doubleOrWorse":30}},
                {"key":"2025","roundCount":40,"average18":91.0,"bestScore":84,"worstScore":101}],
      "byQuarter":[{"key":"2026-Q2","roundCount":4,"average18":87.5,"bestScore":82,"worstScore":93,"outcomes":{"birdie":3,"doubleOrWorse":9}},
                   {"key":"2026-Q1","roundCount":8,"average18":null},
                   {"key":"unknown","roundCount":1,"average18":95}],
      "byMonth":[{"key":"2026-06","roundCount":1,"average18":86},{"key":"2026-05","roundCount":3,"average18":89}],
      "byDay":[{"key":"2026-05-01","roundCount":1},{"key":"2026-05-09","roundCount":2},{"key":"2026-06-01","roundCount":1},
               {"key":"2025-11-02","roundCount":1}]}}
    """#

    func testTheChartIsScoresForRoundsAndAveragesForPeriodsOldestFirst() throws {
        let stats = try stats(fixture)
        let rounds = ResultsTimePresentation.chartRows(stats, grain: .round)
        XCTAssertEqual(rounds.map(\.value), [90, 86], "an unscored round is not a point")
        XCTAssertEqual(rounds.map(\.label), ["2026-05-01", "2026-06-01"])
        let quarters = ResultsTimePresentation.chartRows(stats, grain: .quarter)
        XCTAssertEqual(quarters.map(\.label), ["2026-Q2"], "no average and the unknown bucket are left out")
        XCTAssertEqual(ResultsTimePresentation.chartRows(stats, grain: .month).map(\.label), ["2026-05", "2026-06"])
        XCTAssertEqual(ResultsTimePresentation.chartRows(stats, grain: .year).map(\.value), [91.0, 88.4])
        XCTAssertEqual(quarters.first?.target, .period("2026-Q2"))
    }

    func testCardsListQuartersOrYearsWithPerRoundBirdiesAndDoubles() throws {
        let stats = try stats(fixture)
        let quarters = ResultsTimePresentation.periodCards(stats.time, grain: .month)
        XCTAssertEqual(quarters.heading, "按季度")
        XCTAssertEqual(quarters.cards.map(\.key), ["2026-Q2", "2026-Q1"])
        let q2 = quarters.cards[0]
        XCTAssertEqual(q2.title, "2026 年第 2 季度")
        XCTAssertEqual(q2.headline, "4 场 · 均杆 87.5")
        XCTAssertEqual([q2.best, q2.worst, q2.birdiesPerRound, q2.doublesPerRound], ["82", "93", "0.8", "2.3"])
        let q1 = quarters.cards[1]
        XCTAssertEqual(q1.headline, "8 场 · 均杆 —", "a missing average is —, never 0")
        XCTAssertEqual([q1.best, q1.birdiesPerRound], ["—", "—"])
        let years = ResultsTimePresentation.periodCards(stats.time, grain: .year)
        XCTAssertEqual(years.heading, "历年")
        XCTAssertEqual(years.cards.map(\.title), ["2026 年", "2025 年"])
        XCTAssertEqual(ResultsTimePresentation.periodTitle("2026-05"), "2026 年 5 月")
    }

    func testTheCalendarSummarisesTheNewestPlayedYear() throws {
        let summary = try XCTUnwrap(ResultsTimePresentation.calendarSummary(try stats(fixture).time))
        XCTAssertEqual(summary.year, 2026)
        XCTAssertEqual(summary.rounds, 4)
        XCTAssertEqual(try XCTUnwrap(summary.perActiveMonth), 2.0, accuracy: 1e-9)
        XCTAssertEqual(summary.busiestMonth, 5)
        XCTAssertEqual(summary.text, "4 场 · 月均 2.0 · 5 月最多")
        XCTAssertNil(ResultsTimePresentation.calendarSummary(nil))
    }
}
