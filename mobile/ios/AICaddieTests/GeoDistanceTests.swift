import XCTest
@testable import AICaddie

/// round-13 B1: the LIVE GPS rangefinder's distance math + the model wiring that carries the green
/// Front/Middle/Back coords to the phone. Live CoreLocation behaviour itself is device-only, but the
/// pure haversine math and the Codable decode are deterministic and unit-tested here.
final class GeoDistanceTests: XCTestCase {
    func testHaversineEquatorDegreeLongitude() {
        // 1° of longitude at the equator = radians(1) × 6 371 000 ≈ 111 194.9 m.
        let m = GeoDistance.haversineMetres(0, 0, 0, 1)
        XCTAssertEqual(m, 111_194.9, accuracy: 1.0)
    }

    func testHaversineSymmetricAndZero() {
        XCTAssertEqual(GeoDistance.haversineMetres(40, 116, 40, 116), 0, accuracy: 1e-6)
        let a = GeoDistance.haversineMetres(40.0, 116.0, 40.001, 116.001)
        let b = GeoDistance.haversineMetres(40.001, 116.001, 40.0, 116.0)
        XCTAssertEqual(a, b, accuracy: 1e-6)
    }

    func testLiveYardsToGreenMiddleFromTee() {
        // Player on the tee; the green-middle the backend ships for a RefLat/RefLon=(40,116) hole sits
        // ~201 m (local) due north → ~40.0018059. The live rangefinder should read ~220 yards.
        let here = (lat: 40.0, lon: 116.0)
        let greenMiddle = (lat: 40.0018059, lon: 116.0)
        let metres = GeoDistance.haversineMetres(here.lat, here.lon, greenMiddle.lat, greenMiddle.lon)
        XCTAssertEqual(metres, 200.8, accuracy: 1.5)
        let yards = GeoDistance.yards(from: here.lat, here.lon, to: greenMiddle.lat, greenMiddle.lon)
        XCTAssertEqual(yards, 220)
    }

    func testYardsIsNilWhenTargetCoordinateMissing() {
        XCTAssertNil(GeoDistance.yards(from: 40, 116, to: nil, 116))
        XCTAssertNil(GeoDistance.yards(from: 40, 116, to: 40, nil))
    }

    func testGreenDistancesDecodesLiveLatLon() throws {
        // The backend (course_prep._green_distances) ships these keys when the hole anchor is known.
        let json = """
        {"available":true,"frontM":196.0,"frontYd":214,"middleM":201.0,"middleYd":220,
         "backM":206.0,"backYd":225,
         "frontLat":40.0017609,"frontLon":115.99996,
         "middleLat":40.0018059,"middleLon":116.0,
         "backLat":40.0018509,"backLon":116.00004}
        """
        let gd = try JSONDecoder().decode(CoursePrepGreenDistances.self, from: Data(json.utf8))
        XCTAssertEqual(gd.frontLat, 40.0017609)
        XCTAssertEqual(gd.middleLon, 116.0)
        XCTAssertEqual(gd.backLat, 40.0018509)
        // The phone can now range-find to the green-middle from a fix without any backend round-trip.
        let yards = GeoDistance.yards(from: 40.0, 116.0, to: gd.middleLat, gd.middleLon)
        XCTAssertEqual(yards, 220)
    }

    func testGreenDistancesWithoutLatLonDecodesNilGracefully() throws {
        // Geometry-only hole (no RefLat/RefLon) → coords absent → decode nil, distances intact.
        let json = #"{"available":true,"frontM":196.0,"middleM":201.0,"backM":206.0}"#
        let gd = try JSONDecoder().decode(CoursePrepGreenDistances.self, from: Data(json.utf8))
        XCTAssertNil(gd.frontLat)
        XCTAssertNil(gd.middleLon)
        XCTAssertNil(gd.backLat)
        XCTAssertEqual(gd.middleM, 201.0)
        XCTAssertNil(GeoDistance.yards(from: 40.0, 116.0, to: gd.middleLat, gd.middleLon))
    }
}
