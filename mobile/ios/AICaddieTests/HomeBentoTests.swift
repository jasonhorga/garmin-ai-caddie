import XCTest
@testable import AICaddie

/// 首页 C: the 今天 / 成绩 / 球包 tiles and the in-progress loop dots read only real data.
final class HomeBentoTests: XCTestCase {
    func testTheWeatherTileNamesConditionWindAndRain() throws {
        let json = #"{"schema":"ai-caddie-weather-snapshot-v1","state":"ready","source":"open_meteo","temperatureC":19.4,"windSpeedMps":5.2,"windDirectionDeg":90,"weatherCode":61,"condition":"rain","precipitationProbabilityPct":70,"confidence":"high","missingData":[]}"#
        let weather = try JSONDecoder().decode(HomeWeather.self, from: Data(json.utf8))
        let tile = try XCTUnwrap(weather.presentation)
        XCTAssertEqual(tile.temperatureText, "19°")
        XCTAssertEqual(tile.conditionText, "雨")
        XCTAssertEqual(tile.symbolName, "cloud.rain")
        XCTAssertEqual(tile.windText, "东风 5 m/s · 3 级")
        XCTAssertEqual(tile.rainText, "降雨 70% · 带伞")

        let calm = try XCTUnwrap(HomeWeather(
            temperatureC: 26, windSpeedMps: 1, windDirectionDeg: 315, condition: "clear", precipitationProbabilityPct: 0
        ).presentation)
        XCTAssertEqual(calm.conditionText, "晴")
        XCTAssertEqual(calm.windText, "微风 1 m/s")
        XCTAssertEqual(calm.rainText, "降雨 0%")
    }

    func testMissingWeatherStaysQuiet() {
        XCTAssertNil(HomeWeather(state: "missing", temperatureC: nil, windSpeedMps: nil, windDirectionDeg: nil,
                                 condition: nil, precipitationProbabilityPct: nil).presentation)
        let unknownSky = HomeWeather(temperatureC: 12, windSpeedMps: nil, windDirectionDeg: nil, condition: nil,
                                     precipitationProbabilityPct: nil).presentation
        XCTAssertEqual(unknownSky?.conditionText, nil)
        XCTAssertEqual(unknownSky?.windText, nil)
        XCTAssertEqual(unknownSky?.rainText, nil)
    }

    func testWindDirectionIsWhereTheWindBlowsFromAndForceIsBeaufort() {
        XCTAssertEqual(HomeWeather.windDirectionName(0), "北")
        XCTAssertEqual(HomeWeather.windDirectionName(338), "北")
        XCTAssertEqual(HomeWeather.windDirectionName(315), "西北")
        XCTAssertEqual(HomeWeather.windDirectionName(-90), "西")
        XCTAssertEqual(HomeWeather.beaufortForce(0.1), 0)
        XCTAssertEqual(HomeWeather.beaufortForce(3.0), 2)
        XCTAssertEqual(HomeWeather.beaufortForce(8.0), 5)
        XCTAssertEqual(HomeWeather.beaufortForce(40), 12)
    }

    func testTheLoopDotsAreTheNineHoldingTheActiveHole() {
        let dots = HubHoleDot.loopDots(roundHoles: Array(1...18), activeHole: 12) { hole in hole == 10 ? 1 : nil }
        XCTAssertEqual(dots.map(\.hole), Array(10...18))
        XCTAssertEqual(dots.first?.toPar, 1)
        XCTAssertEqual(dots.filter(\.isCurrent).map(\.hole), [12])
        XCTAssertTrue(HubHoleDot.loopDots(roundHoles: [1, 2], activeHole: 5) { _ in nil }.isEmpty)
    }

    func testTheScoresTileComparesFullRoundsOnlyOldestFirst() throws {
        func card(_ id: String, holes: Int, score: Int) throws -> HistoryRoundCard {
            let json = #"{"id":"\#(id)","courseName":"球场","holesCompleted":\#(holes),"score":\#(score),"scoreStrip":[],"badges":[]}"#
            return try JSONDecoder().decode(HistoryRoundCard.self, from: Data(json.utf8))
        }
        let newestFirst = [try card("a", holes: 18, score: 85), try card("b", holes: 9, score: 44),
                           try card("c", holes: 18, score: 90), try card("d", holes: 18, score: 88)]
        XCTAssertEqual(HubScoresTile.recentScores(history: newestFirst), [88, 90, 85])
        XCTAssertEqual(HubScoresTile.recentScores(history: newestFirst, limit: 2), [90, 85])
    }

    func testTheBagTileListsTheLongestClubsFirstInYards() {
        let profiles = [
            ClubProfile(clubName: "七号铁", sampleSize: 4, medianM: 137, p10M: 130, p90M: 144),
            ClubProfile(clubName: "一号木", sampleSize: 4, medianM: 210, p10M: 200, p90M: 220),
            ClubProfile(clubName: "推杆", sampleSize: 4, medianM: 0, p10M: 0, p90M: 0),
        ]
        let carries = HubBagTile.carries(from: profiles)
        XCTAssertEqual(carries.map(\.club), ["一号木", "七号铁"])
        XCTAssertEqual(carries.map(\.yards), [230, 150])
    }
}
