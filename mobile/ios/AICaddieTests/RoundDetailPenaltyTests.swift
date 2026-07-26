import Foundation
import XCTest
@testable import AICaddie

final class RoundDetailPenaltyTests: XCTestCase {
    func testRoundDetailDecodesPerHolePenalties() throws {
        let json = """
        {
          "roundRef": "watch-round-1",
          "found": true,
          "scorecard": [
            {"hole": 1, "par": 4, "score": 5, "putts": 2, "penalties": 1}
          ]
        }
        """

        let detail = try JSONDecoder().decode(RoundDetail.self, from: Data(json.utf8))

        XCTAssertEqual(detail.scorecard.first?.penalties, 1)
    }
}
