import SwiftUI
import XCTest
@testable import AICaddie

/// round-10 反馈的纯逻辑回归:避开区沙坑编号/排序、issue 中文映射、策略语义着色。
final class RoundTenUITests: XCTestCase {
    func testHazardsNumberAndSortMultipleBunkersNearToFar() throws {
        let hazards = CaddiePlanHazard.from(
            CoursePrepHazards(waterCarry: [[175, 195]], bunkers: [[210, 18], [138, 12]])
        )
        let bunkers = hazards.filter { $0.icon == "🏖" }
        XCTAssertEqual(bunkers.count, 2)
        // Bunker rows are [distance along route, shortest lateral gap to its boundary].
        // Number and sort by the first value without presenting the lateral value as a fake back edge.
        XCTAssertEqual(bunkers[0].label, "沙坑 1")
        XCTAssertEqual(bunkers[1].label, "沙坑 2")
        let nearYards = CoursePrepRoute.yards(fromMetres: 138)
        let farYards = CoursePrepRoute.yards(fromMetres: 210)
        let nearSideYards = CoursePrepRoute.yards(fromMetres: 12)
        let farSideYards = CoursePrepRoute.yards(fromMetres: 18)
        XCTAssertEqual(bunkers[0].detail, "距 \(nearYards) 码 · 离球路 \(nearSideYards) 码")
        XCTAssertEqual(bunkers[1].detail, "距 \(farYards) 码 · 离球路 \(farSideYards) 码")
        XCTAssertLessThan(nearYards, farYards)  // sort order: nearer bunker first

        let water = try XCTUnwrap(hazards.first { $0.icon == "💧" })
        XCTAssertEqual(water.detail, "191–213 码")
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
