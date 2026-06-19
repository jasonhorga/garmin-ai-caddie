import SwiftUI
import XCTest
@testable import AICaddie

/// round-10 反馈的纯逻辑回归:避开区沙坑编号/排序、issue 中文映射、策略语义着色。
final class RoundTenUITests: XCTestCase {
    func testHazardsNumberAndSortMultipleBunkersNearToFar() {
        let hazards = CaddiePlanHazard.from(
            CoursePrepHazards(waterCarry: [[175, 195]], bunkers: [[210, 225], [138, 150]])
        )
        let bunkers = hazards.filter { $0.icon == "🏖" }
        XCTAssertEqual(bunkers.count, 2)
        // numbered + nearest carry first (138 before 210), so three zones aren't all just "沙坑".
        XCTAssertEqual(bunkers[0].label, "沙坑 1")
        XCTAssertEqual(bunkers[1].label, "沙坑 2")
        XCTAssertTrue(bunkers[0].detail?.contains("138") == true)
        XCTAssertTrue(bunkers[1].detail?.contains("210") == true)
    }

    func testSingleHazardOfAKindIsNotNumbered() {
        let hazards = CaddiePlanHazard.from(
            CoursePrepHazards(waterCarry: [[175, 195]], bunkers: [[138, 150]])
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
