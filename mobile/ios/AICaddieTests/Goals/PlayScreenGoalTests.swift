// size: medium
// goals: I-05, I-06, I-12

import AICaddieDomain
import XCTest
@testable import AICaddie

final class PlayScreenGoalTests: XCTestCase {
    // goals: I-05 [main]
    func testHomeShowsWeatherOnlyWhenTheProviderHasARealTemperature() {
        let weather = HomeWeather(
            temperatureC: 21.6, windSpeedMps: 3.2, windDirectionDeg: 90,
            condition: "clear", precipitationProbabilityPct: 60
        )
        XCTAssertEqual(weather.presentation?.temperatureText, "22°")
        XCTAssertEqual(weather.presentation?.conditionText, "晴")
        XCTAssertEqual(weather.presentation?.rainText, "降雨 60% · 带伞")
        XCTAssertNil(HomeWeather(state: "unavailable", temperatureC: 21, windSpeedMps: nil, windDirectionDeg: nil, condition: nil, precipitationProbabilityPct: nil).presentation)
        XCTAssertNil(HomeWeather(temperatureC: nil, windSpeedMps: nil, windDirectionDeg: nil, condition: "clear", precipitationProbabilityPct: nil).presentation)
    }

    // goals: I-05
    func testHomeHeroPrioritizesActiveRoundThenNearbyThenSearch() {
        let nearby = HubCourseSuggestion(globalId: 1, courseName: "附近球场", startTitle: "开始", teeBox: "blue", loops: [])
        XCTAssertEqual(HubHeroState.resolve(hasActiveRound: true, hasPendingWatchRound: false, nearby: nearby, replay: nil), .inProgress)
        XCTAssertEqual(HubHeroState.resolve(hasActiveRound: false, hasPendingWatchRound: true, nearby: nearby, replay: nil), .pendingWatch)
        XCTAssertEqual(HubHeroState.resolve(hasActiveRound: false, hasPendingWatchRound: false, nearby: nearby, replay: nil), .nearby(nearby))
        XCTAssertEqual(HubHeroState.resolve(hasActiveRound: false, hasPendingWatchRound: false, nearby: nil, replay: nearby), .search(replay: nearby))
    }

    // goals: I-06 [main]
    func testMapFallsBackToGarminThenWaitsAndNeverDowngradesPrecise() {
        let garmin = LiveMapDisplayState.resolveLive(.init(
            coverage: "partial", preciseTopoImageReady: false,
            garminRaster: GarminRasterResponse(available: true, imageUrl: "/garmin.png"),
            garminImageFailed: false,
            hasCachedPreciseTopo: false, hasRoute: true
        ))
        XCTAssertEqual(garmin, .garminRaster)
        let waiting = LiveMapDisplayState.resolveLive(.init(
            coverage: "partial", preciseTopoImageReady: false, garminRaster: nil,
            garminImageReady: false, garminImageFailed: false, hasCachedPreciseTopo: false, hasRoute: true
        ))
        XCTAssertEqual(waiting, .waiting)
        let precise = LiveMapDisplayState.resolveLive(.init(
            coverage: "ready", preciseTopoImageReady: true, garminRaster: nil,
            garminImageFailed: false,
            hasCachedPreciseTopo: false
        ))
        let after = LiveMapDisplayState.resolveLive(.init(
            coverage: "ready", preciseTopoImageReady: false,
            garminRaster: GarminRasterResponse(available: true, imageUrl: "/garmin.png"),
            garminImageFailed: false,
            hasCachedPreciseTopo: false
        ), previous: precise)
        XCTAssertEqual(after, .factualPending)
    }

    // goals: I-12 [main]
    func testFinishSummaryParUsesRecordedHolesAndWholeCourseOnlyWhenEmpty() {
        let holes = (1...9).map { Hole(number: $0, par: $0 == 1 ? 4 : 3, yards: nil, geometryCoverage: .missing, sourceGlobalId: 1, sourceLocalHole: $0, courseHoleNumber: $0) }
        let recorded = LiveRoundScoreSummary(holes: [LiveHoleScore(hole: 1, par: 4, score: 5, putts: 2, penalties: 0, fairway: nil, source: LiveScoreSource.manualEdit.rawValue)])
        XCTAssertEqual(LiveRoundFinishSummaryView.parLine(summary: recorded, holes: holes), "Par 4 · 1/9 洞")
        XCTAssertEqual(LiveRoundFinishSummaryView.parLine(summary: LiveRoundScoreSummary(holes: []), holes: holes), "Par 28 · 0/9 洞")
    }
}
