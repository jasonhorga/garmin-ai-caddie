import XCTest
@testable import AICaddieDomain

/// Runs the Swift classifier against the same vectors as `tests/test_tee_result.py`.
/// `Fixtures/tee_result_vectors.json` is a byte-for-byte copy of `tests/fixtures/tee_result_vectors.json`
/// (`tests/test_tee_result.py` fails if the copies drift).
final class TeeResultTests: XCTestCase {
    private struct Vector: Decodable {
        let name: String
        let point: [Double]?
        let fairwayOutline: FairwayOutline?
        let route: [[Double]]
        let par: Int
        let expected: String?
    }

    private struct Vectors: Decodable {
        let cases: [Vector]
    }

    private func vectors() throws -> [Vector] {
        #if SWIFT_PACKAGE
        let bundle = Bundle.module
        #else
        let bundle = Bundle(for: TeeResultTests.self)
        #endif
        let url = try XCTUnwrap(
            bundle.url(forResource: "tee_result_vectors", withExtension: "json", subdirectory: "Fixtures")
                ?? bundle.url(forResource: "tee_result_vectors", withExtension: "json"),
            "missing copied fixture Fixtures/tee_result_vectors.json"
        )
        return try JSONDecoder().decode(Vectors.self, from: Data(contentsOf: url)).cases
    }

    func testEverySharedVector() throws {
        let cases = try vectors()
        XCTAssertGreaterThanOrEqual(cases.count, 16)
        for vector in cases {
            let result = TeeResultClassifier.classify(
                point: vector.point,
                outline: vector.fairwayOutline,
                route: vector.route,
                par: vector.par
            )
            XCTAssertEqual(result?.rawValue, vector.expected, vector.name)
        }
    }

    func testOutlineWithoutPixelRingsStillDecodes() throws {
        let outline = try JSONDecoder().decode(
            FairwayOutline.self,
            from: Data(#"{"version":1,"polygons":[{"outerLatLon":[[40.0,116.0],[40.0,116.001],[40.001,116.0]]}]}"#.utf8)
        )
        XCTAssertEqual(outline.polygons.first?.outerPx, [])
        XCTAssertEqual(outline.polygons.first?.holesLatLon.count, 0)
    }
}
