@testable import AICaddie
import XCTest

/// C118① / J2.2: a range picker and its displayed stats always describe the same answer.
final class C118ResultsRangeFailureTests: XCTestCase {
    private func stats(_ rounds: Int) throws -> MobileStats {
        try JSONDecoder().decode(
            MobileStats.self,
            from: Data(#"{"summary":{"totalRounds":\#(rounds)}}"#.utf8)
        )
    }

    func test_c118_1_failed_range_switch_reverts_picker_and_keeps_previous_data() throws {
        let all = try stats(31)
        var state = ResultsTimeLoadState(window: "all", stats: all)
        let request = state.select("last10")

        XCTAssertTrue(state.complete(request, stats: nil))
        XCTAssertEqual(state.window, "all", "failed 10 场 request must return the picker to the data's all range")
        XCTAssertEqual(state.stats?.summary?.totalRounds, 31, "the previous all-range answer remains visible")
        XCTAssertEqual(state.notice, "未更新，可重试")
    }

    func test_c118_1_successful_range_switch_commits_matching_picker_and_data() throws {
        let all = try stats(31)
        let ten = try stats(10)
        var state = ResultsTimeLoadState(window: "all", stats: all)
        let request = state.select("last10")

        XCTAssertTrue(state.complete(request, stats: ten))
        XCTAssertEqual(state.window, "last10")
        XCTAssertEqual(state.stats?.summary?.totalRounds, 10)
        XCTAssertNil(state.notice)
    }
}
