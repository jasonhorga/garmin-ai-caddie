@testable import AICaddie
import XCTest

/// J2.2: a range picker and its displayed stats always describe the same answer.
final class J2_2ResultsRangeFailureTests: XCTestCase {
    private func stats(_ rounds: Int) throws -> MobileStats {
        try JSONDecoder().decode(
            MobileStats.self,
            from: Data(#"{"summary":{"totalRounds":\#(rounds)}}"#.utf8)
        )
    }

    func test_j2_2_failed_range_switch_reverts_picker_and_keeps_previous_data() throws {
        let all = try stats(31)
        var state = ResultsTimeLoadState(window: "all", stats: all)
        let request = state.select("last10")

        XCTAssertTrue(state.complete(request, stats: nil))
        XCTAssertEqual(state.window, "all", "failed 10 场 request must return the picker to the data's all range")
        XCTAssertEqual(state.stats?.summary?.totalRounds, 31, "the previous all-range answer remains visible")
        XCTAssertEqual(state.notice, "10 场未更新，可重试")
        XCTAssertEqual(state.retry().window, "last10", "retry must request the failed range")
    }

    func test_j2_2_successful_range_switch_commits_matching_picker_and_data() throws {
        let all = try stats(31)
        let ten = try stats(10)
        var state = ResultsTimeLoadState(window: "all", stats: all)
        let request = state.select("last10")

        XCTAssertTrue(state.complete(request, stats: ten))
        XCTAssertEqual(state.window, "last10")
        XCTAssertEqual(state.stats?.summary?.totalRounds, 10)
        XCTAssertNil(state.notice)
    }

    func test_j2_2_switching_back_invalidates_the_old_request() throws {
        let all = try stats(31)
        let ten = try stats(10)
        var state = ResultsTimeLoadState(window: "all", stats: all)
        let oldRequest = state.select("last10")

        XCTAssertNil(state.choose("all"))
        XCTAssertFalse(state.complete(oldRequest, stats: ten))
        XCTAssertEqual(state.window, "all")
        XCTAssertEqual(state.stats?.summary?.totalRounds, 31)
        XCTAssertEqual(state.notice, "10 场未更新，可重试")
        XCTAssertFalse(state.isLoading)
    }

    func test_j2_2_refresh_invalidates_a_pending_range_without_silent_revert() throws {
        let all = try stats(31)
        let ten = try stats(10)
        var state = ResultsTimeLoadState(window: "all", stats: all)
        let oldRequest = state.select("last10")
        let refreshRequest = state.refresh()

        XCTAssertFalse(state.complete(oldRequest, stats: ten))
        XCTAssertEqual(state.window, "all")
        XCTAssertEqual(state.notice, "10 场未更新，可重试")
        XCTAssertTrue(state.isLoading)
        XCTAssertTrue(state.complete(refreshRequest, stats: all))
        XCTAssertNil(state.notice)
    }
}
