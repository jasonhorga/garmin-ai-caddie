@testable import AICaddie
import XCTest

/// B4c: the fixture's two prep shapes (`Fixtures/b4c_prep_render_shapes.json`, kept in lock-step
/// with `server_v2/ci_fixture.py` by `tests/test_prep_render_shapes_fixture.py`) are production's:
/// `render=true` embeds the pixel overlay, `render=false` omits `map` and carries the local-metre
/// route plus the (0,0)/(120,0)/(0,120) projection refs. Both must resolve to one map overlay.
final class PrepRenderShapesTests: XCTestCase {
    private struct Oracle: Decodable {
        let rendered: CoursePrepResponse
        let lightweight: CoursePrepResponse
    }

    private func oracle() throws -> Oracle {
        #if SWIFT_PACKAGE
        let bundle = Bundle.module
        #else
        let bundle = Bundle(for: PrepRenderShapesTests.self)
        #endif
        let url = try XCTUnwrap(
            bundle.url(forResource: "b4c_prep_render_shapes", withExtension: "json", subdirectory: "Fixtures")
                ?? bundle.url(forResource: "b4c_prep_render_shapes", withExtension: "json")
        )
        return try JSONDecoder().decode(Oracle.self, from: Data(contentsOf: url))
    }

    func testRenderedAndLightweightPrepResolveToOneOverlay() throws {
        let oracle = try oracle()
        let rendered = try XCTUnwrap(oracle.rendered.holes.first)
        let lightweight = try XCTUnwrap(oracle.lightweight.holes.first)
        XCTAssertNotNil(rendered.map?.overlay, "render=true embeds the pixel overlay")
        XCTAssertNil(lightweight.map, "render=false omits map, as production does")

        let embedded = try XCTUnwrap(rendered.resolvedMapOverlay)
        let projected = try XCTUnwrap(lightweight.resolvedMapOverlay, "the refs project the local-metre route")
        XCTAssertEqual(projected.w, embedded.w)
        XCTAssertEqual(projected.h, embedded.h)
        XCTAssertEqual(projected.ppm, embedded.ppm, accuracy: 1e-4)
        XCTAssertEqual(projected.ln, embedded.ln, accuracy: 1e-6)
        XCTAssertEqual(projected.route.count, embedded.route.count)
        for (a, b) in zip(projected.route, embedded.route) {
            XCTAssertEqual(a[0], b[0], accuracy: 1e-3)
            XCTAssertEqual(a[1], b[1], accuracy: 1e-3)
            XCTAssertEqual(a[2], b[2], accuracy: 1e-6)
        }
        // One closure: the overlay's length is the route, the green middle and the Blue yardage.
        XCTAssertEqual(embedded.ln, rendered.routeLenM, accuracy: 1e-6)
        XCTAssertEqual(try XCTUnwrap(rendered.greenDistances?.middleM), rendered.routeLenM, accuracy: 1e-6)
        XCTAssertEqual(rendered.blueYards, CoursePrepRoute.yards(fromMetres: rendered.routeLenM))
    }
}
