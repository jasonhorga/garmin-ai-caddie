import SwiftUI
import XCTest
@testable import AICaddie

/// round-10 反馈的纯逻辑回归:避开区沙坑编号/排序、issue 中文映射、策略语义着色。
final class RoundTenUITests: XCTestCase {
    func testStrategyLabelsDistinguishRecommendationConservativeAndAttack() {
        XCTAssertEqual(zhCaddieRouteLabel("stock"), "推荐")
        XCTAssertEqual(zhCaddieRouteLabel("safe"), "保守")
        XCTAssertEqual(zhCaddieRouteLabel("attack"), "进攻")
    }

    func testHazardIconsUseProductGlyphKeysInsteadOfEmoji() throws {
        let hazards = CaddiePlanHazard.from(
            CoursePrepHazards(waterCarry: [[175, 195]], bunkers: [[138, 12]])
        )

        XCTAssertEqual(try XCTUnwrap(hazards.first { $0.label == "沙坑" }).icon, "bunker")
        XCTAssertEqual(try XCTUnwrap(hazards.first { $0.label == "水域" }).icon, "water")
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

    func testHazardsNumberAndSortMultipleBunkersNearToFar() throws {
        let hazards = CaddiePlanHazard.from(
            CoursePrepHazards(
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
            route: [[100, 500, 0], [100, 100, 260]]
        )
        let bunkers = hazards.filter { $0.icon == "bunker" }
        XCTAssertEqual(bunkers.count, 2)
        // Name by actionable side/area, sort by measured front edge, and keep S70 front/back facts.
        XCTAssertEqual(bunkers[0].label, "右侧球道沙坑")
        XCTAssertEqual(bunkers[1].label, "右侧果岭沙坑")
        let nearYards = CoursePrepRoute.yards(fromMetres: 134)
        let nearClearYards = CoursePrepRoute.yards(fromMetres: 149)
        let farYards = CoursePrepRoute.yards(fromMetres: 207)
        let farClearYards = CoursePrepRoute.yards(fromMetres: 224)
        XCTAssertEqual(bunkers[0].detail, "到 \(nearYards) · 过 \(nearClearYards) 码")
        XCTAssertEqual(bunkers[1].detail, "到 \(farYards) · 过 \(farClearYards) 码")
        XCTAssertLessThan(nearYards, farYards)  // sort order: nearer bunker first

        let water = try XCTUnwrap(hazards.first { $0.icon == "water" })
        XCTAssertEqual(water.detail, "到 191 · 过 213 码")

        // Every iPhone surface consumes one proximity order, regardless of hazard kind. A water
        // edge between two bunkers must not be appended after every bunker simply because of type.
        XCTAssertEqual(hazards.map(\.label), ["右侧球道沙坑", "前方水障碍", "右侧果岭沙坑"])
        XCTAssertEqual(
            "\(hazards[0].label) · \(try XCTUnwrap(hazards[0].detail))",
            "右侧球道沙坑 · 到 147 · 过 163 码"
        )
    }

    func testLegacyBunkerNeverTreatsItsLateralGapAsTheBackEdge() throws {
        let bunker = try XCTUnwrap(CaddiePlanHazard.from(
            CoursePrepHazards(bunkers: [[138, 12]])
        ).first)

        XCTAssertEqual(bunker.detail, "距 151 码")
        XCTAssertFalse(bunker.detail?.contains("离球路") == true)
        XCTAssertFalse(bunker.detail?.contains("过") == true)
    }

    func testSingleHazardOfAKindIsNotNumbered() {
        let hazards = CaddiePlanHazard.from(
            CoursePrepHazards(waterCarry: [[175, 195]], bunkers: [[138, 12]])
        )
        XCTAssertEqual(hazards.filter { $0.icon == "bunker" }.first?.label, "沙坑")
        XCTAssertEqual(hazards.filter { $0.icon == "water" }.first?.label, "前方水障碍")
    }

    func testLegacyHazardsUseAreaAndDistanceInsteadOfDecoderOrderNumbers() {
        let hazards = CaddiePlanHazard.from(
            CoursePrepHazards(
                waterCarry: [[175, 195]],
                bunkers: [[260, 12], [138, 12]]
            ),
            route: [[100, 500, 0], [100, 100, 300]]
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
}
