import CoreGraphics
import CoreLocation
import Foundation
import UIKit
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
        let json = #"{"hole":1,"par":4,"par_source":"courseview","blue_yards":410,"route_len_m":300,"route":[[120,330],[120,30]],"geometryCoverage":"\#(coverage)","geometryRevision":"r1","steps":[],"cautions":[],"hazards":{"water_carry":[],"bunkers":[]},"map":{"overlay":{"w":240,"h":360,"ppm":1,"ln":300,"route":[[120,330,0],[120,30,300]]}},"holeImageProjection":{"available":true,"widthPx":240,"heightPx":360,"refs":[{"lat":40.0,"lon":116.0,"px":120,"py":330},{"lat":40.0,"lon":116.001,"px":120,"py":30},{"lat":40.001,"lon":116.0,"px":240,"py":330}]}}"#
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
        let preciseProjection = try XCTUnwrap(hole.holeImageProjection)
        let garminProjection = CoursePrepHoleImageProjection(
            available: true,
            widthPx: 1242,
            heightPx: 1920,
            refs: preciseProjection.refs ?? []
        )
        XCTAssertEqual(
            LiveMapDisplaySelection.projection(
                for: state,
                precise: preciseProjection,
                garmin: garminProjection
            ),
            garminProjection
        )
        XCTAssertNotNil(
            LiveMapDisplaySelection.overlay(
                for: state,
                precise: hole.resolvedMapOverlay,
                preciseProjection: preciseProjection,
                garminProjection: garminProjection
            )
        )
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
        let hole = try prep(coverage: "ready")
        let preciseProjection = try XCTUnwrap(hole.holeImageProjection)
        let garminProjection = CoursePrepHoleImageProjection(
            available: true,
            widthPx: 1242,
            heightPx: 1920,
            refs: preciseProjection.refs ?? []
        )
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
        XCTAssertEqual(
            LiveMapDisplaySelection.projection(
                for: .precise,
                precise: preciseProjection,
                garmin: garminProjection
            ),
            preciseProjection
        )
        XCTAssertEqual(
            LiveMapDisplaySelection.overlay(
                for: .precise,
                precise: hole.resolvedMapOverlay,
                preciseProjection: preciseProjection,
                garminProjection: garminProjection
            ),
            hole.resolvedMapOverlay
        )
    }

    func testEmbeddedTopoWinsWhenGarminImageFails() {
        let validPNG = "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII="
        XCTAssertTrue(CoursePrepHole.hasDecodableEmbeddedTopo(validPNG))
        XCTAssertFalse(CoursePrepHole.hasDecodableEmbeddedTopo("data:image/png;base64,not-base64"))
        XCTAssertFalse(CoursePrepHole.hasDecodableEmbeddedTopo("data:image/png;base64"))
        XCTAssertEqual(
            LiveMapDisplayState.resolveLive(
                .init(
                    coverage: "ready",
                    preciseTopoImageReady: CoursePrepHole.hasDecodableEmbeddedTopo(validPNG),
                    garminRaster: GarminRasterResponse(
                        available: true,
                        imageUrl: "/raster.jpg"
                    ),
                    garminImageFailed: true,
                    hasCachedPreciseTopo: false
                )
            ),
            .precise
        )
    }

    func testPartialWithoutCachedTopoDoesNotEnterPreciseOrReuseProjection() throws {
        let hole = try prep(coverage: "partial")
        let preciseProjection = try XCTUnwrap(hole.holeImageProjection)
        let garminProjection = CoursePrepHoleImageProjection(
            available: true,
            widthPx: 1242,
            heightPx: 1920,
            refs: preciseProjection.refs ?? []
        )
        let state = LiveMapDisplayState.resolveLive(
            .init(
                coverage: hole.geometryCoverage,
                preciseTopoImageReady: true,
                garminRaster: GarminRasterResponse(available: true, imageUrl: "/raster.jpg"),
                garminImageFailed: false,
                hasCachedPreciseTopo: false
            )
        )
        XCTAssertEqual(state, .garminRaster)
        let numericState = LiveMapDisplayState.resolveLive(
            .init(
                coverage: hole.geometryCoverage,
                preciseTopoImageReady: false,
                garminRaster: GarminRasterResponse(available: true, imageUrl: "/raster.jpg"),
                garminImageFailed: true,
                hasCachedPreciseTopo: false
            )
        )
        XCTAssertEqual(numericState, .numericPlaceholder)
        XCTAssertNil(
            LiveMapDisplaySelection.projection(
                for: numericState,
                precise: preciseProjection,
                garmin: garminProjection
            )
        )
        XCTAssertNil(
            LiveMapDisplaySelection.overlay(
                for: numericState,
                precise: hole.resolvedMapOverlay,
                preciseProjection: preciseProjection,
                garminProjection: garminProjection
            )
        )
    }

    func testNumericPlaceholderGestureStateResetsScaleAndOffset() {
        XCTAssertEqual(
            LiveMapDisplaySelection.gestureScale(for: .numericPlaceholder, proposed: 4),
            1
        )
        XCTAssertEqual(
            LiveMapDisplaySelection.gestureOffset(
                for: .numericPlaceholder,
                proposed: CGSize(width: 120, height: -80)
            ),
            .zero
        )
        XCTAssertNil(
            LiveMapDisplaySelection.gestureFrameOverlay(
                for: .numericPlaceholder,
                overlay: CoursePrepOverlay(w: 240, h: 360, ppm: 1, ln: 0, route: []),
                garminProjection: nil
            )
        )
    }

    func testGarminRetryCursorResumesRemainingDelayAndResets() {
        var cursor = GarminRasterRetryCursor()
        XCTAssertEqual(cursor.nextPlan(nowNanoseconds: 100)?.attempt, 0)
        XCTAssertEqual(cursor.nextPlan(nowNanoseconds: 100)?.delayNanoseconds, 0)

        cursor.recordFailure(at: 100)
        XCTAssertEqual(cursor.nextPlan(nowNanoseconds: 100)?.attempt, 1)
        XCTAssertEqual(cursor.nextPlan(nowNanoseconds: 100)?.delayNanoseconds, 5_000_000_000)
        XCTAssertEqual(cursor.nextPlan(nowNanoseconds: 2_000_000_100)?.delayNanoseconds, 3_000_000_000)
        XCTAssertEqual(cursor.nextPlan(nowNanoseconds: 5_000_000_100)?.delayNanoseconds, 0)

        cursor.recordFailure(at: 5_000_000_100)
        XCTAssertEqual(cursor.nextPlan(nowNanoseconds: 5_000_000_100)?.attempt, 2)
        XCTAssertEqual(cursor.nextPlan(nowNanoseconds: 20_000_000_100)?.delayNanoseconds, 0)
        cursor.recordFailure(at: 20_000_000_100)
        XCTAssertEqual(cursor.nextPlan(nowNanoseconds: 20_000_000_100)?.delayNanoseconds, 30_000_000_000)

        cursor.reset()
        XCTAssertEqual(cursor.nextPlan(nowNanoseconds: 20_000_000_100)?.attempt, 0)
        XCTAssertEqual(cursor.nextPlan(nowNanoseconds: 20_000_000_100)?.delayNanoseconds, 0)
    }

    func testGarminWithoutProjectionGestureFrameClampsToFallbackRaster() throws {
        let overlay = try XCTUnwrap(
            LiveMapDisplaySelection.gestureFrameOverlay(
                for: .garminRaster,
                overlay: nil,
                garminProjection: nil
            )
        )
        XCTAssertEqual(overlay.w, 1242)
        XCTAssertEqual(overlay.h, 1920)
        let viewport = CGSize(width: 390, height: 844)
        let frame = try XCTUnwrap(
            LivePlayMapOverlayLayout.mapFrame(
                overlayWidth: overlay.w,
                overlayHeight: overlay.h,
                in: viewport,
                topInset: LivePlayMapOverlayLayout.liveMapTopInset
            )
        )
        let proposed = CGSize(width: 900, height: -900)
        let clamped = LivePlayMapOverlayLayout.clampedOffset(
            proposed,
            mapFrame: frame,
            viewportSize: viewport,
            scale: 4
        )
        let center = CGPoint(x: viewport.width / 2, y: viewport.height / 2)
        let transformedMinX = center.x + (frame.minX - center.x) * 4
        let transformedMaxX = center.x + (frame.maxX - center.x) * 4
        let transformedMinY = center.y + (frame.minY - center.y) * 4
        let transformedMaxY = center.y + (frame.maxY - center.y) * 4
        XCTAssertGreaterThanOrEqual(clamped.width, viewport.width - transformedMaxX)
        XCTAssertLessThanOrEqual(clamped.width, -transformedMinX)
        XCTAssertGreaterThanOrEqual(clamped.height, viewport.height - transformedMaxY)
        XCTAssertLessThanOrEqual(clamped.height, -transformedMinY)
        XCTAssertNotEqual(clamped, proposed)
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
        let sourceFrame = CGRect(x: 0, y: 80, width: 390, height: 604)
        let destinationFrame = CGRect(x: 60, y: 80, width: 270, height: 405)
        let sourceOffset = CGSize(width: 450, height: 150)
        let unclamped = try XCTUnwrap(GarminRasterViewportTransfer.transfer(
            viewportSize: CGSize(width: 390, height: 844),
            sourceFrame: sourceFrame,
            destinationFrame: destinationFrame,
            sourceOverlay: sourceOverlay,
            destinationOverlay: destinationOverlay,
            sourceProjection: source,
            destinationProjection: destination,
            scale: 4,
            offset: sourceOffset
        ))
        let result = try XCTUnwrap(LiveMapViewportCarryOver.transfer(
            viewportSize: CGSize(width: 390, height: 844),
            sourceFrame: sourceFrame,
            destinationFrame: destinationFrame,
            sourceOverlay: sourceOverlay,
            destinationOverlay: destinationOverlay,
            sourceProjection: source,
            destinationProjection: destination,
            // Use a zoom where both destination axes cover the viewport; the helper's actual
            // clamped offset is still used below when reconstructing the displayed centre.
            scale: 4,
            offset: sourceOffset
        ))
        XCTAssertGreaterThanOrEqual(result.scale, 1)
        XCTAssertLessThanOrEqual(result.scale, 4)
        XCTAssertEqual(result.offset.width, unclamped.offset.width, accuracy: 1e-6)
        XCTAssertEqual(result.offset.height, unclamped.offset.height, accuracy: 1e-6)
        let displayedOffset = LivePlayMapOverlayLayout.clampedOffset(
            result.offset,
            mapFrame: destinationFrame,
            viewportSize: CGSize(width: 390, height: 844),
            scale: result.scale
        )
        let displayedSourceOffset = LivePlayMapOverlayLayout.clampedOffset(
            sourceOffset,
            mapFrame: sourceFrame,
            viewportSize: CGSize(width: 390, height: 844),
            scale: 4
        )
        let oldCenter = CGPoint(
            x: 390 / 2 - displayedSourceOffset.width / 4,
            y: 844 / 2 - displayedSourceOffset.height / 4
        )
        let oldPixel = CGPoint(
            x: (oldCenter.x - 0) / 390 * 1242,
            y: (oldCenter.y - 80) / 604 * 1920
        )
        let oldCoordinate = try XCTUnwrap(GarminRasterProjectionMath.projectFromPixel(oldPixel, projection: source))
        let newCenter = CGPoint(
            x: 195 - displayedOffset.width / result.scale,
            y: 422 - displayedOffset.height / result.scale
        )
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

    /// C88: the server's Garmin raster is a WebP whose sky is transparent. The store asks for WebP
    /// first and keeps the alpha both from the network and from its own disk copy.
    @MainActor
    func testStoreLoadsTheTransparentWebpRasterAndKeepsItsAlpha() async throws {
        let url = URL(string: "https://garmin-webp.example.test/api/v2/courses/1/holes/1/garmin-raster.webp?v=c88-\(UUID().uuidString)-sky1")!
        // Synthetic 40-byte RGBA WebP generated with Pillow: transparent 8x8 canvas,
        // rectangle (2, 2)..(5, 5) filled (104, 158, 92, 255), saved as lossless WebP.
        let webp = try XCTUnwrap(
            Data(base64Encoded: "UklGRiAAAABXRUJQVlA4TBQAAAAvB8ABEA8wnoM2XPMf8BieiP4HDw==")
        )
        let accept = AcceptHeader()
        CapturingURLProtocol.requestHandler = { request in
            accept.value = request.value(forHTTPHeaderField: "Accept")
            let response = HTTPURLResponse(
                url: request.url!, statusCode: 200, httpVersion: nil,
                headerFields: ["Content-Type": "image/webp"]
            )!
            return (response, webp)
        }
        URLProtocol.registerClass(CapturingURLProtocol.self)
        defer {
            URLProtocol.unregisterClass(CapturingURLProtocol.self)
            CapturingURLProtocol.requestHandler = nil
        }

        // A decoder regression must fail the assertion, rather than retrying forever.
        let store = GarminRasterImageStore(sleep: { _ in throw CancellationError() })
        await store.load(url)
        let loaded = try XCTUnwrap(store.image)
        XCTAssertEqual(loaded.size, CGSize(width: 8, height: 8))
        XCTAssertEqual(accept.value?.hasPrefix("image/webp"), true, "requested \(accept.value ?? "nil")")
        XCTAssertEqual(try alpha(of: loaded, x: 0, y: 0), 0)
        XCTAssertEqual(try alpha(of: loaded, x: 4, y: 4), 255)

        GarminRasterImageStore.evict(url)
        XCTAssertNil(GarminRasterImageStore.cachedImage(for: url), "a memory miss must not decode disk on the main thread")
        let disk = try XCTUnwrap(GarminRasterImageStore.diskCachedImage(for: url))
        XCTAssertEqual(try alpha(of: disk, x: 0, y: 0), 0)
        XCTAssertEqual(try alpha(of: disk, x: 4, y: 4), 255)
        GarminRasterImageStore.evict(url)
    }

    @MainActor
    func testDiskCacheStartupRemovesOnlyLegacyJPEGs() throws {
        let manager = FileManager.default
        let root = manager.temporaryDirectory.appendingPathComponent(UUID().uuidString, isDirectory: true)
        defer { try? manager.removeItem(at: root) }
        let images = root.appendingPathComponent("AICaddieGarminRasterImages-v1", isDirectory: true)
        let metadata = root.appendingPathComponent("AICaddieGarminRasterMetadata-v1", isDirectory: true)
        try manager.createDirectory(at: images, withIntermediateDirectories: true)
        try manager.createDirectory(at: metadata, withIntermediateDirectories: true)
        let bytes = Data([1, 2, 3])
        for name in ["old.jpg", "old-uppercase.JPG", "current.webp", "retained.png"] {
            try bytes.write(to: images.appendingPathComponent(name))
        }
        let unrelated = metadata.appendingPathComponent("unrelated.jpg")
        try bytes.write(to: unrelated)

        let prepared = GarminRasterImageStore.prepareDiskCacheDirectory(in: root)
        XCTAssertEqual(prepared, images)
        XCTAssertFalse(manager.fileExists(atPath: images.appendingPathComponent("old.jpg").path))
        XCTAssertFalse(manager.fileExists(atPath: images.appendingPathComponent("old-uppercase.JPG").path))
        for name in ["current.webp", "retained.png"] {
            XCTAssertEqual(try Data(contentsOf: images.appendingPathComponent(name)), bytes)
        }
        XCTAssertEqual(try Data(contentsOf: unrelated), bytes)
        // A JPEG cached after the one-time cleanup is still referenced by an older offline pack.
        let laterJPEG = images.appendingPathComponent("later.jpg")
        try bytes.write(to: laterJPEG)
        let again = GarminRasterImageStore.prepareDiskCacheDirectory(in: root)
        XCTAssertEqual(again, prepared)
        XCTAssertEqual(try Data(contentsOf: images.appendingPathComponent("current.webp")), bytes)
        XCTAssertEqual(try Data(contentsOf: laterJPEG), bytes)
    }

    private final class AcceptHeader {
        var value: String?
    }

    private func alpha(of image: UIImage, x: Int, y: Int) throws -> Int {
        let cgImage = try XCTUnwrap(image.cgImage)
        var bytes = [UInt8](repeating: 0, count: 4)
        let drawn = bytes.withUnsafeMutableBytes { buffer -> Bool in
            guard let context = CGContext(
                data: buffer.baseAddress, width: 1, height: 1, bitsPerComponent: 8, bytesPerRow: 4,
                space: CGColorSpaceCreateDeviceRGB(),
                bitmapInfo: CGImageAlphaInfo.premultipliedLast.rawValue
            ) else { return false }
            context.draw(cgImage, in: CGRect(
                x: -CGFloat(x), y: -CGFloat(cgImage.height - 1 - y),
                width: CGFloat(cgImage.width), height: CGFloat(cgImage.height)
            ))
            return true
        }
        XCTAssertTrue(drawn)
        return Int(bytes[3])
    }
}
