import CoreGraphics
import CoreLocation
import Foundation
import XCTest
@testable import AICaddie

private final class GarminRasterStubURLProtocol: URLProtocol {
    enum Mode { case serverError, timeout }
    static var mode: Mode = .serverError

    override class func canInit(with request: URLRequest) -> Bool { true }
    override class func canonicalRequest(for request: URLRequest) -> URLRequest { request }
    override func startLoading() {
        switch Self.mode {
        case .timeout:
            client?.urlProtocol(self, didFailWithError: URLError(.timedOut))
        case .serverError:
            let response = HTTPURLResponse(
                url: request.url!, statusCode: 500, httpVersion: nil,
                headerFields: ["Content-Type": "application/json"]
            )!
            client?.urlProtocol(self, didReceive: response, cacheStoragePolicy: .notAllowed)
            client?.urlProtocol(self, didLoad: Data(#"{"detail":"fixture"}"#.utf8))
            client?.urlProtocolDidFinishLoading(self)
        }
    }
    override func stopLoading() {}
}

/// Card 454: the phone can use Garmin's raster while CourseView geometry is pending and can
/// transfer the player's viewport/points when the precise image arrives.
final class GarminRasterTests: XCTestCase {
    private func projection(
        originPixel: CGPoint,
        xPixel: CGPoint,
        yPixel: CGPoint
    ) -> CoursePrepHoleImageProjection {
        CoursePrepHoleImageProjection(
            available: true,
            widthPx: 1242,
            heightPx: 1920,
            refs: [
                CoursePrepProjectionRef(lat: 40.0000, lon: 116.0000, px: originPixel.x, py: originPixel.y),
                CoursePrepProjectionRef(lat: 40.0000, lon: 116.0010, px: xPixel.x, py: xPixel.y),
                CoursePrepProjectionRef(lat: 40.0010, lon: 116.0000, px: yPixel.x, py: yPixel.y),
            ]
        )
    }

    private func prep(coverage: String = "partial") throws -> CoursePrepHole {
        let json = #"{"hole":1,"par":4,"par_source":"courseview","blue_yards":410,"route_len_m":300,"route":[[120,330],[120,30]],"geometryCoverage":"#(coverage)","geometryRevision":"r1","steps":[],"cautions":[],"hazards":{"water_carry":[],"bunkers":[]},"map":{"overlay":{"w":240,"h":360,"ppm":1,"ln":300,"route":[[120,330,0],[120,30,300]]}},"holeImageProjection":{"available":true,"widthPx":240,"heightPx":360,"refs":[{"lat":40.0,"lon":116.0,"px":120,"py":330},{"lat":40.0,"lon":116.001,"px":120,"py":30},{"lat":40.001,"lon":116.0,"px":240,"py":330}]}}"#
        return try JSONDecoder().decode(CoursePrepHole.self, from: Data(json.utf8))
    }

    func testTopoPendingRasterAvailableUsesRasterProjection() throws {
        let hole = try prep(coverage: "ready")
        let state = LiveMapDisplayState.resolveLive(
            .init(
                coverage: hole.geometryCoverage,
                preciseTopoImageReady: false,
                garminRaster: GarminRasterResponse(
                    available: true,
                    imageUrl: "/api/v2/courses/1/holes/1/garmin-raster.jpg?v=asset-1",
                    projection: GarminRasterProjection(widthPx: 1242, heightPx: 1920, refs: [])
                ),
                garminImageFailed: false,
                hasCachedPreciseTopo: false
            )
        )
        XCTAssertEqual(state, .garminRaster)
        let raster = projection(
            originPixel: CGPoint(x: 80, y: 140),
            xPixel: CGPoint(x: 80, y: 1740),
            yPixel: CGPoint(x: 700, y: 140)
        )
        let point = GarminRasterProjectionMath.projectToPixel(
            latitude: 40.0005,
            longitude: 116.0005,
            projection: raster
        )
        XCTAssertEqual(point?.x ?? -1, 390, accuracy: 0.5)
        XCTAssertEqual(point?.y ?? -1, 940, accuracy: 0.5)
    }

    func testTopoReadyWinsOverRasterAndUsesTopoProjection() throws {
        let hole = try prep()
        XCTAssertEqual(
            LiveMapDisplayState.resolveLive(
                .init(
                    coverage: hole.geometryCoverage,
                    preciseTopoImageReady: true,
                    garminRaster: GarminRasterResponse(available: true, imageUrl: "/raster.jpg"),
                    garminImageFailed: false,
                    hasCachedPreciseTopo: false
                )
            ),
            .precise
        )
    }

    func testUnavailableRasterFallsBackToNumericPlaceholderState() throws {
        let hole = try prep()
        XCTAssertEqual(
            LiveMapDisplayState.resolveLive(
                .init(
                    coverage: hole.geometryCoverage,
                    preciseTopoImageReady: false,
                    garminRaster: GarminRasterResponse(available: false),
                    garminImageFailed: false,
                    hasCachedPreciseTopo: false
                )
            ),
            .numericPlaceholder
        )
        XCTAssertEqual(
            LiveMapDisplayState.resolveLive(
                .init(
                    coverage: nil,
                    preciseTopoImageReady: false,
                    garminRaster: GarminRasterResponse(
                        available: false,
                        imageUrl: "/raster.jpg?v=asset-4"
                    ),
                    garminImageFailed: false,
                    hasCachedPreciseTopo: false
                )
            ),
            .garminRaster
        )
        XCTAssertEqual(
            LiveMapDisplayState.resolveLive(
                .init(
                    coverage: nil,
                    preciseTopoImageReady: false,
                    garminRaster: GarminRasterResponse(
                        available: true,
                        imageUrl: "/raster.jpg?v=asset-5"
                    ),
                    garminImageFailed: true,
                    hasCachedPreciseTopo: false
                )
            ),
            .numericPlaceholder
        )
    }

    func testRasterToTopoTransferKeepsGeographicViewportCenter() {
        let source = projection(
            originPixel: CGPoint(x: 80, y: 140),
            xPixel: CGPoint(x: 80, y: 1740),
            yPixel: CGPoint(x: 700, y: 140)
        )
        let destination = projection(
            originPixel: CGPoint(x: 120, y: 40),
            xPixel: CGPoint(x: 120, y: 1000),
            yPixel: CGPoint(x: 700, y: 40)
        )
        let rasterCenter = CGPoint(x: 390, y: 940)
        let topoCenter = GarminRasterProjectionMath.remap(
            pixel: rasterCenter,
            from: source,
            to: destination
        )
        XCTAssertEqual(topoCenter?.x ?? -1, 410, accuracy: 0.5)
        XCTAssertEqual(topoCenter?.y ?? -1, 520, accuracy: 0.5)
        let coordinate = GarminRasterProjectionMath.projectFromPixel(rasterCenter, projection: source)
        XCTAssertEqual(coordinate?.latitude ?? 0, 40.0005, accuracy: 1e-9)
        XCTAssertEqual(coordinate?.longitude ?? 0, 116.0005, accuracy: 1e-9)
    }

    func testSameCoordinateIsPixelAccurateInBothProjectionFrames() {
        let first = projection(
            originPixel: CGPoint(x: 100, y: 200),
            xPixel: CGPoint(x: 300, y: 200),
            yPixel: CGPoint(x: 100, y: 500)
        )
        let second = projection(
            originPixel: CGPoint(x: 20, y: 40),
            xPixel: CGPoint(x: 420, y: 40),
            yPixel: CGPoint(x: 20, y: 640)
        )
        let coordinate = CLLocationCoordinate2D(latitude: 40.00025, longitude: 116.00075)
        let firstPoint = GarminRasterProjectionMath.projectToPixel(
            latitude: coordinate.latitude,
            longitude: coordinate.longitude,
            projection: first
        )
        let secondPoint = GarminRasterProjectionMath.projectToPixel(
            latitude: coordinate.latitude,
            longitude: coordinate.longitude,
            projection: second
        )
        XCTAssertEqual(firstPoint?.x ?? -1, 250, accuracy: 0.5)
        XCTAssertEqual(firstPoint?.y ?? -1, 275, accuracy: 0.5)
        XCTAssertEqual(secondPoint?.x ?? -1, 320, accuracy: 0.5)
        XCTAssertEqual(secondPoint?.y ?? -1, 190, accuracy: 0.5)
    }

    func testRemapOverlayUsesGroundMetresWhenReferenceSpansDiffer() throws {
        let source = CoursePrepHoleImageProjection(
            available: true, widthPx: 240, heightPx: 360,
            refs: [
                CoursePrepProjectionRef(lat: 40, lon: 116, px: 0, py: 0),
                CoursePrepProjectionRef(lat: 40, lon: 116.001, px: 100, py: 0),
                CoursePrepProjectionRef(lat: 40.001, lon: 116, px: 0, py: 100),
            ]
        )
        let destination = CoursePrepHoleImageProjection(
            available: true, widthPx: 1242, heightPx: 1920,
            refs: [
                CoursePrepProjectionRef(lat: 39.999, lon: 115.999, px: 10, py: 20),
                CoursePrepProjectionRef(lat: 39.999, lon: 116.001, px: 210, py: 20),
                CoursePrepProjectionRef(lat: 40.001, lon: 115.999, px: 10, py: 220),
            ]
        )
        let overlay = CoursePrepOverlay(w: 240, h: 360, ppm: 1, ln: 100, route: [[0, 0, 0], [100, 0, 100]])
        let remapped = try XCTUnwrap(
            GarminRasterProjectionMath.remapOverlay(overlay, from: source, to: destination)
        )
        XCTAssertEqual(remapped.ppm, 1, accuracy: 0.03)
    }

    func testViewportTransferConvertsScaleOffsetAndTarget() throws {
        let source = projection(
            originPixel: CGPoint(x: 80, y: 140),
            xPixel: CGPoint(x: 80, y: 1740),
            yPixel: CGPoint(x: 700, y: 140)
        )
        let destination = CoursePrepHoleImageProjection(
            available: true, widthPx: 240, heightPx: 360,
            refs: [
                CoursePrepProjectionRef(lat: 40, lon: 116, px: 120, py: 330),
                CoursePrepProjectionRef(lat: 40, lon: 116.001, px: 120, py: 30),
                CoursePrepProjectionRef(lat: 40.001, lon: 116, px: 240, py: 330),
            ]
        )
        let sourceOverlay = CoursePrepOverlay(w: 1242, h: 1920, ppm: 2, ln: 300, route: [[390, 1740, 0], [390, 140, 300]])
        let destinationOverlay = CoursePrepOverlay(w: 240, h: 360, ppm: 1, ln: 300, route: [[120, 330, 0], [120, 30, 300]])
        let result = try XCTUnwrap(LiveMapViewportCarryOver.transfer(
            viewportSize: CGSize(width: 390, height: 844),
            sourceFrame: CGRect(x: 0, y: 80, width: 390, height: 604),
            destinationFrame: CGRect(x: 60, y: 80, width: 270, height: 405),
            sourceOverlay: sourceOverlay,
            destinationOverlay: destinationOverlay,
            sourceProjection: source,
            destinationProjection: destination,
            scale: 2,
            offset: CGSize(width: -24, height: 18)
        ))
        XCTAssertGreaterThanOrEqual(result.scale, 1)
        XCTAssertLessThanOrEqual(result.scale, 4)
        let oldCenter = CGPoint(x: 390 / 2 - (-24) / 2, y: 844 / 2 - 18 / 2)
        let oldPixel = CGPoint(
            x: (oldCenter.x - 0) / 390 * 1242,
            y: (oldCenter.y - 80) / 604 * 1920
        )
        let oldCoordinate = try XCTUnwrap(GarminRasterProjectionMath.projectFromPixel(oldPixel, projection: source))
        let newCenter = CGPoint(x: 195 - result.offset.width / result.scale, y: 422 - result.offset.height / result.scale)
        let newPixel = CGPoint(
            x: (newCenter.x - 60) / 270 * 240,
            y: (newCenter.y - 80) / 405 * 360
        )
        let newCoordinate = try XCTUnwrap(GarminRasterProjectionMath.projectFromPixel(newPixel, projection: destination))
        XCTAssertEqual(oldCoordinate.latitude, newCoordinate.latitude, accuracy: 1e-7)
        XCTAssertEqual(oldCoordinate.longitude, newCoordinate.longitude, accuracy: 1e-7)
    }

    func testRasterFailureReasonDoesNotCrashAndIsNotUsable() {
        let failed = GarminRasterResponse(
            available: false,
            mode: "none",
            reason: "timeout"
        )
        XCTAssertFalse(failed.isUsable)
        XCTAssertEqual(failed.reason, "timeout")
    }

    func testUnavailableProjectionShowsImageWithoutOverlays() throws {
        let response = try JSONDecoder().decode(
            GarminRasterResponse.self,
            from: Data(#"{"available":false,"imageUrl":"/api/v2/courses/1/holes/1/garmin-raster.jpg?v=asset-2","projection":null,"mode":"none","reason":"geometry"}"#.utf8)
        )
        XCTAssertTrue(response.hasDisplayableImage)
        XCTAssertFalse(response.isUsable)
        XCTAssertNil(response.projection)
    }

    func testLegacyUnavailableProjectionFlagIsExplicitlyUnavailable() throws {
        let response = try JSONDecoder().decode(
            GarminRasterResponse.self,
            from: Data(#"{"available":true,"imageUrl":"/api/v2/courses/1/holes/1/garmin-raster.jpg?v=asset-3","projection":{"available":false,"widthPx":1242,"heightPx":1920,"refs":[{"lat":40,"lon":116,"px":0,"py":0},{"lat":40,"lon":116.001,"px":100,"py":0},{"lat":40.001,"lon":116,"px":0,"py":100}]},"mode":"H","reason":null}"#.utf8)
        )
        XCTAssertFalse(response.projection?.isUsable == true)
        XCTAssertFalse(response.isUsable)
        XCTAssertTrue(response.hasDisplayableImage)
    }

    func testRelativeImageURLPreservesConfiguredBasePath() throws {
        let response = GarminRasterResponse(
            available: true,
            imageUrl: "/api/v2/courses/1/holes/1/garmin-raster.jpg?v=asset-6"
        )
        let url = try XCTUnwrap(
            response.resolvedImageURL(relativeTo: URL(string: "https://example.test/caddie")!)
        )
        XCTAssertEqual(url.path, "/caddie/api/v2/courses/1/holes/1/garmin-raster.jpg")
        XCTAssertEqual(url.query, "v=asset-6")
    }

    func testRaster500AndTimeoutAreOrdinaryErrors() async {
        let configuration = URLSessionConfiguration.ephemeral
        configuration.protocolClasses = [GarminRasterStubURLProtocol.self]
        let session = URLSession(configuration: configuration)
        let client = SyncClient(baseURL: URL(string: "https://example.test")!, session: session)
        for mode in [GarminRasterStubURLProtocol.Mode.serverError, .timeout] {
            GarminRasterStubURLProtocol.mode = mode
            do {
                _ = try await client.fetchGarminRaster(globalId: 1, localHole: 1)
                XCTFail("expected raster request failure")
            } catch {
                XCTAssertFalse(error is DecodingError)
            }
        }
    }
}
