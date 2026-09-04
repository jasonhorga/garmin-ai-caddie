import CoreLocation
import XCTest
@testable import AICaddie

final class LiveHoleGPSResolverTests: XCTestCase {
    func testConfidentNearestTeeProducesCandidate() throws {
        let holes = [
            hole(1, latitude: 40.0000, longitude: 116.0000),
            hole(2, latitude: 40.0010, longitude: 116.0000),
        ]

        let candidate = LiveHoleGPSResolver.candidate(
            holes: holes,
            coordinate: CLLocationCoordinate2D(latitude: 40.00102, longitude: 116.0000),
            horizontalAccuracyM: 6
        )

        XCTAssertEqual(candidate?.hole, 2)
        XCTAssertLessThan(try XCTUnwrap(candidate?.distanceM), 5)
    }

    func testAdjacentAmbiguousTeesDoNotAutoProposeEitherHole() {
        let holes = [
            hole(1, latitude: 40.00000, longitude: 116.0000),
            hole(2, latitude: 40.00010, longitude: 116.0000),
        ]

        XCTAssertNil(LiveHoleGPSResolver.candidate(
            holes: holes,
            coordinate: CLLocationCoordinate2D(latitude: 40.00005, longitude: 116.0000),
            horizontalAccuracyM: 5
        ))
    }

    func testFarOrLowAccuracyFixDoesNotProposeHole() {
        let holes = [hole(1, latitude: 40.0000, longitude: 116.0000)]
        XCTAssertNil(LiveHoleGPSResolver.candidate(
            holes: holes,
            coordinate: CLLocationCoordinate2D(latitude: 40.0100, longitude: 116.0000),
            horizontalAccuracyM: 5
        ))
        XCTAssertNil(LiveHoleGPSResolver.candidate(
            holes: holes,
            coordinate: CLLocationCoordinate2D(latitude: 40.0000, longitude: 116.0000),
            horizontalAccuracyM: 80
        ))
    }

    private func hole(_ number: Int, latitude: Double, longitude: Double) -> Hole {
        Hole(
            number: number,
            par: 4,
            yards: 400,
            geometryCoverage: .ready,
            teeLatitude: latitude,
            teeLongitude: longitude
        )
    }
}
