import Foundation
import XCTest
@testable import AICaddieDomain

/// 5.8: independent product vectors shared with the backend, including polygon cutouts,
/// disconnected fairways, reverse direction and cases where no result is justified.
final class ProductTeeResultTests: XCTestCase {
    private struct Document: Decodable {
        let schemaVersion: Int
        let cases: [Vector]
    }

    private struct Vector: Decodable {
        let id: String
        let par: Int
        let point: [Double]?
        let fairwayOutline: FairwayOutline?
        let route: [[Double]]
        let expected: String?
    }

    func test_j5_8_tee_results_match_shared_vectors() throws {
        // Xcode copies the authoritative vector into this bundle, without a duplicate fixture.
        #if SWIFT_PACKAGE
        var root = URL(fileURLWithPath: #filePath)
        for _ in 0..<5 { root.deleteLastPathComponent() }
        let url = root.appendingPathComponent("tests/product/fixtures/shared/tee_result.json")
        #else
        let url = try XCTUnwrap(Bundle(for: Self.self).url(forResource: "tee_result", withExtension: "json"))
        #endif
        let document = try JSONDecoder().decode(Document.self, from: Data(contentsOf: url))
        XCTAssertEqual(document.schemaVersion, 1)
        XCTAssertFalse(document.cases.isEmpty, "the shared vector table must be exercised")
        for vector in document.cases {
            XCTAssertEqual(
                TeeResultClassifier.classify(
                    point: vector.point,
                    outline: vector.fairwayOutline,
                    route: vector.route,
                    par: vector.par
                )?.rawValue,
                vector.expected,
                vector.id
            )
        }
    }
}
