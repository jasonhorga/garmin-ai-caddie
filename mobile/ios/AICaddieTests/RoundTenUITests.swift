import SwiftUI
import XCTest
@testable import AICaddie

/// round-10 反馈的纯逻辑回归:避开区沙坑编号/排序、issue 中文映射、策略语义着色。
final class RoundTenUITests: XCTestCase {
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
            )
        )
        let bunkers = hazards.filter { $0.icon == "🏖" }
        XCTAssertEqual(bunkers.count, 2)
        // Number/sort by measured front edge and show the same front/back semantics as S70.
        XCTAssertEqual(bunkers[0].label, "沙坑 1")
        XCTAssertEqual(bunkers[1].label, "沙坑 2")
        let nearYards = CoursePrepRoute.yards(fromMetres: 134)
        let nearClearYards = CoursePrepRoute.yards(fromMetres: 149)
        let farYards = CoursePrepRoute.yards(fromMetres: 207)
        let farClearYards = CoursePrepRoute.yards(fromMetres: 224)
        XCTAssertEqual(bunkers[0].detail, "到 \(nearYards) · 过 \(nearClearYards) 码")
        XCTAssertEqual(bunkers[1].detail, "到 \(farYards) · 过 \(farClearYards) 码")
        XCTAssertLessThan(nearYards, farYards)  // sort order: nearer bunker first

        let water = try XCTUnwrap(hazards.first { $0.icon == "💧" })
        XCTAssertEqual(water.detail, "到 191 · 过 213 码")

        // Every iPhone surface consumes one proximity order, regardless of hazard kind. A water
        // edge between two bunkers must not be appended after every bunker simply because of type.
        XCTAssertEqual(hazards.map(\.label), ["沙坑 1", "水域", "沙坑 2"])
        XCTAssertEqual(
            "\(hazards[0].label) · \(try XCTUnwrap(hazards[0].detail))",
            "沙坑 1 · 到 147 · 过 163 码"
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
        XCTAssertEqual(hazards.filter { $0.icon == "🏖" }.first?.label, "沙坑")
        XCTAssertEqual(hazards.filter { $0.icon == "💧" }.first?.label, "水域")
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
}
