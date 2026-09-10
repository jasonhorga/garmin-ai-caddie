import SwiftUI
import XCTest
@testable import AICaddie

/// round-10 反馈的纯逻辑回归:障碍物语义命名/排序、issue 中文映射、传输枚举兼容。
final class RoundTenUITests: XCTestCase {
    func testRouteModesMapToTransportOptionIds() {
        XCTAssertEqual(caddieOptionId(forStrategyMode: "stock"), "stock")
        XCTAssertEqual(caddieOptionId(forStrategyMode: "protect_score"), "safe")
        XCTAssertEqual(caddieOptionId(forStrategyMode: "attack"), "attack")
        XCTAssertEqual(caddieOptionId(forStrategyMode: "unknown_route"), "unknown_route")
    }

    func testHazardRowsExposeSemanticKindsForSystemIcons() throws {
        let hazards = LiveHazardDisplayItem.rows(
            for: makeHole(hazards: CoursePrepHazards(waterCarry: [[175, 195]], bunkers: [[138, 12]])),
            liveReadouts: nil
        )

        XCTAssertEqual(try XCTUnwrap(hazards.first { $0.kind == "bunker" }).kind, "bunker")
        XCTAssertTrue(try XCTUnwrap(hazards.first { $0.kind == "water" }).isWater)
    }

    func testUncalibratedExpectedStrokesStayOutOfPlayerFacingCopy() {
        let option = CaddiePlanOption(
            id: "stock", label: "标准", carryM: 180, riskScore: 1, clubName: "3W",
            p10M: 160, p90M: 205, sampleSize: 24, confidence: "high", coverageText: "24/24",
            expectedStrokes: 2.4, expectedStrokesDelta: -0.2, scoreImpactModel: "heuristic_v1",
            sourceRefs: [], missingDataLabels: []
        )

        XCTAssertNil(option.scoreImpactText)
    }

    func testHazardsNameAndSortMultipleBunkersNearToFar() throws {
        let route: [[Double]] = [[100, 500, 0], [100, 100, 260]]
        let hazards = LiveHazardDisplayItem.rows(
            for: makeHole(
                hazards: CoursePrepHazards(
                waterCarry: [[175, 195]],
                bunkers: [[210, 18], [138, 12]],
                details: [
                    CoursePrepHazardDetail(
                        kind: "water", frontM: 175, backM: 195,
                        frontRouteM: 175, backRouteM: 195,
                        frontPx: [100, 300], backPx: [100, 280], sideM: nil
                    ),
                    CoursePrepHazardDetail(
                        kind: "bunker", frontM: 207, backM: 224,
                        frontRouteM: 205, backRouteM: 225,
                        frontPx: [130, 260], backPx: [132, 240], sideM: 18
                    ),
                    CoursePrepHazardDetail(
                        kind: "bunker", frontM: 134, backM: 149,
                        frontRouteM: 132, backRouteM: 151,
                        frontPx: [112, 390], backPx: [114, 371], sideM: 12
                    ),
                ]
                ),
                route: route,
                map: CoursePrepMap(
                    image: nil,
                    overlay: CoursePrepOverlay(w: 240, h: 520, ppm: 1, ln: 260, route: route)
                )
            ),
            liveReadouts: nil
        )
        let bunkers = hazards.filter { $0.kind == "bunker" }
        XCTAssertEqual(bunkers.count, 2)
        // Name by actionable side/area, sort by measured front edge, and keep S70 front/back facts.
        XCTAssertEqual(bunkers[0].label, "右侧球道沙坑")
        XCTAssertEqual(bunkers[1].label, "右侧果岭沙坑")
        let nearYards = CoursePrepRoute.yards(fromMetres: 134)
        let nearClearYards = CoursePrepRoute.yards(fromMetres: 149)
        let farYards = CoursePrepRoute.yards(fromMetres: 207)
        let farClearYards = CoursePrepRoute.yards(fromMetres: 224)
        XCTAssertEqual(bunkers[0].frontYards, nearYards)
        XCTAssertEqual(bunkers[0].backYards, nearClearYards)
        XCTAssertEqual(bunkers[1].frontYards, farYards)
        XCTAssertEqual(bunkers[1].backYards, farClearYards)
        XCTAssertLessThan(nearYards, farYards)  // sort order: nearer bunker first

        let water = try XCTUnwrap(hazards.first { $0.kind == "water" })
        XCTAssertEqual(water.frontYards, 191)
        XCTAssertEqual(water.backYards, 213)

        // Every iPhone surface consumes one proximity order, regardless of hazard kind. A water
        // edge between two bunkers must not be appended after every bunker simply because of type.
        XCTAssertEqual(hazards.map(\.label), ["右侧球道沙坑", "前方水障碍", "右侧果岭沙坑"])
        XCTAssertEqual(hazards[0].label, "右侧球道沙坑")
        XCTAssertEqual(hazards[0].frontYards, 147)
        XCTAssertEqual(hazards[0].backYards, 163)
    }

    func testLegacyBunkerNeverTreatsItsLateralGapAsTheBackEdge() throws {
        let bunker = try XCTUnwrap(
            LiveHazardDisplayItem.rows(
                for: makeHole(hazards: CoursePrepHazards(bunkers: [[138, 12]])),
                liveReadouts: nil
            ).first
        )

        XCTAssertEqual(bunker.frontYards, 151)
        XCTAssertNil(bunker.backYards)
    }

    func testSingleHazardOfAKindIsNotNumbered() {
        let hazards = LiveHazardDisplayItem.rows(
            for: makeHole(hazards: CoursePrepHazards(waterCarry: [[175, 195]], bunkers: [[138, 12]])),
            liveReadouts: nil
        )
        XCTAssertEqual(hazards.first { $0.kind == "bunker" }?.label, "球道沙坑")
        XCTAssertEqual(hazards.first { $0.kind == "water" }?.label, "前方水障碍")
    }

    func testLegacyHazardsUseAreaAndDistanceInsteadOfDecoderOrderNumbers() {
        let route: [[Double]] = [[100, 500, 0], [100, 100, 300]]
        let hazards = LiveHazardDisplayItem.rows(
            for: makeHole(
                hazards: CoursePrepHazards(
                    waterCarry: [[175, 195]],
                    bunkers: [[260, 12], [138, 12]]
                ),
                route: route
            ),
            liveReadouts: nil
        )

        XCTAssertEqual(
            hazards.map(\.label),
            ["球道沙坑", "前方水障碍", "果岭沙坑"]
        )
        XCTAssertFalse(hazards.contains { $0.label.rangeOfCharacter(from: .decimalDigits) != nil })
    }

    func testZhIssueLabelMapsMachineTokensAndPassesUnknownThrough() {
        XCTAssertEqual(zhIssueLabel("rough"), "长草脱困")
        XCTAssertEqual(zhIssueLabel("bunker"), "沙坑救球")
        XCTAssertEqual(zhIssueLabel("missing_putt_data"), "缺少推杆数据")
        XCTAssertEqual(zhIssueLabel("THREE_PUTT"), "三推")  // case-insensitive
        XCTAssertEqual(zhIssueLabel("某个中文标签"), "某个中文标签")  // already-localised passes through
        XCTAssertEqual(zhIssueLabel("totally_unknown"), "totally unknown")  // underscores → spaces
    }

    func testStrategyColorMatchesLiveRouteIdsBySemantics() {
        // Live decision route ids (conservative_layup / stock_line / aggressive_line) used to fall to
        // neutral; now coloured by meaning, matching the offline safe/stock/attack ids.
        XCTAssertEqual(AICaddieDesignTokens.strategyColor("conservative_layup"), AICaddieDesignTokens.par)
        XCTAssertEqual(AICaddieDesignTokens.strategyColor("stock_line"), AICaddieDesignTokens.birdie)
        XCTAssertEqual(AICaddieDesignTokens.strategyColor("aggressive_line"), AICaddieDesignTokens.eagle)
        XCTAssertEqual(AICaddieDesignTokens.strategyColor("safe"), AICaddieDesignTokens.par)
        XCTAssertEqual(AICaddieDesignTokens.strategyColor("attack"), AICaddieDesignTokens.eagle)
    }

    func testCaddieRouteIdsSelectTheMatchingProductStrategy() {
        XCTAssertEqual(caddieStrategyMode(forRouteId: "conservative_layup"), "protect_score")
        XCTAssertEqual(caddieStrategyMode(forRouteId: "safe"), "protect_score")
        XCTAssertEqual(caddieStrategyMode(forRouteId: "stock_line"), "stock")
        XCTAssertEqual(caddieStrategyMode(forRouteId: "standard"), "stock")
        XCTAssertEqual(caddieStrategyMode(forRouteId: "aggressive_line"), "attack")
        XCTAssertEqual(caddieStrategyMode(forRouteId: "go_for_it"), "attack")
        XCTAssertNil(caddieStrategyMode(forRouteId: "unknown_route"))
    }

    private func makeHole(
        hazards: CoursePrepHazards,
        route: [[Double]] = [[100, 500, 0], [100, 100, 300]],
        map: CoursePrepMap? = nil
    ) -> CoursePrepHole {
        CoursePrepHole(
            hole: 1,
            par: 4,
            parSource: "test",
            blueYards: 328,
            routeLenM: route.last?.dropFirst(2).first ?? 300,
            route: route,
            geometryCoverage: "ready",
            hazards: hazards,
            map: map
        )
    }
}
