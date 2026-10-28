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

    /// Product spec 4.5: a measured tee-to-green route is the middle tier, while a hole
    /// without even that route stays on the single waiting surface.
    func testLiveMapThreeTiersUseRouteBeforeNumericWaiting() {
        let routeOnly = LiveMapDisplayState.resolveLive(.init(
            coverage: "partial", preciseTopoImageReady: false, garminRaster: nil,
            garminImageFailed: true, hasCachedPreciseTopo: false, hasRoute: true
        ))
        XCTAssertEqual(routeOnly, .factual)
        let waiting = LiveMapDisplayState.resolveLive(.init(
            coverage: "partial", preciseTopoImageReady: false, garminRaster: nil,
            garminImageFailed: true, hasCachedPreciseTopo: false, hasRoute: false
        ))
        XCTAssertEqual(waiting, .waiting)
    }

    func testPreciseMapReplacesRouteTierWithoutChangingInteractionPolicy() {
        let route = LiveMapDisplayState.resolveLive(.init(
            coverage: "partial", preciseTopoImageReady: false, garminRaster: nil,
            garminImageFailed: true, hasCachedPreciseTopo: false, hasRoute: true
        ))
        let precise = LiveMapDisplayState.resolveLive(.init(
            coverage: "ready", preciseTopoImageReady: true, garminRaster: nil,
            garminImageFailed: true, hasCachedPreciseTopo: false, hasRoute: true
        ))
        XCTAssertEqual(route, .factual)
        XCTAssertEqual(precise, .precise)
        XCTAssertEqual(LiveMapDisplaySelection.gestureScale(for: route, proposed: 2.4), 2.4)
        XCTAssertEqual(LiveMapDisplaySelection.gestureScale(for: precise, proposed: 2.4), 2.4)
        XCTAssertEqual(
            LiveMapDisplaySelection.gestureOffset(for: route, proposed: CGSize(width: 31, height: -12)),
            LiveMapDisplaySelection.gestureOffset(for: precise, proposed: CGSize(width: 31, height: -12))
        )
    }

    /// Product spec 4.5: bitmap replacement keeps the complete viewport interaction state.
    func testRouteTierViewportTransitionPreservesStateForPrecise() {
        let interaction = LiveMapViewportInteraction(
            scale: 2.4,
            offset: CGSize(width: 31, height: -12),
            selectedHazardID: "bunker-0",
            targetPixel: CGPoint(x: 88, y: 141),
            greenPinPixel: CGPoint(x: 91, y: 52)
        )
        let overlay = CoursePrepOverlay(
            w: 240, h: 360, ppm: 1, ln: 300, route: [[120, 330, 0], [120, 30, 300]]
        )
        let precise = projection(
            originPixel: CGPoint(x: 120, y: 330),
            xPixel: CGPoint(x: 120, y: 30),
            yPixel: CGPoint(x: 240, y: 330)
        )
        let preciseResult = LiveMapViewportTransition.preserve(
            previous: .factual,
            next: .precise,
            viewportSize: CGSize(width: 390, height: 844),
            sourceFrame: CGRect(x: 75, y: 100, width: 240, height: 360),
            destinationFrame: CGRect(x: 0, y: 80, width: 390, height: 603),
            sourceOverlay: overlay,
            destinationOverlay: overlay,
            sourceProjection: precise,
            destinationProjection: precise,
            targetCoordinate: nil,
            greenPinCoordinate: nil,
            interaction: interaction
        )
        XCTAssertEqual(preciseResult, interaction, "route → precise")
    }

    func testViewportTransitionPixelSpaceMatrixRemapsCrossSpaceAndKeepsSameSpaceIdentity() throws {
        let preciseProjection = CoursePrepHoleImageProjection(
            available: true,
            widthPx: 240,
            heightPx: 360,
            refs: [
                CoursePrepProjectionRef(lat: 40.0000, lon: 116.0000, px: 120, py: 330),
                CoursePrepProjectionRef(lat: 40.0000, lon: 116.0010, px: 120, py: 30),
                CoursePrepProjectionRef(lat: 40.0010, lon: 116.0000, px: 240, py: 330),
            ]
        )
        let garminProjection = CoursePrepHoleImageProjection(
            available: true,
            widthPx: 1242,
            heightPx: 1920,
            refs: [
                CoursePrepProjectionRef(lat: 40.0000, lon: 116.0000, px: 621, py: 1740),
                CoursePrepProjectionRef(lat: 40.0000, lon: 116.0010, px: 621, py: 140),
                CoursePrepProjectionRef(lat: 40.0010, lon: 116.0000, px: 1242, py: 1740),
            ]
        )
        let preciseOverlay = CoursePrepOverlay(
            w: 240, h: 360, ppm: 1, ln: 300, route: [[120, 330, 0], [120, 30, 300]]
        )
        let garminOverlay = CoursePrepOverlay(
            w: 1242, h: 1920, ppm: 2, ln: 300, route: [[621, 1740, 0], [621, 140, 300]]
        )
        let targetCoordinate = CLLocationCoordinate2D(latitude: 40.0005, longitude: 116.0005)
        let greenCoordinate = CLLocationCoordinate2D(latitude: 40.0002, longitude: 116.0008)
        let preciseFrame = CGRect(x: 75, y: 100, width: 240, height: 360)
        let garminFrame = CGRect(x: 0, y: 80, width: 390, height: 603)
        let transitions: [(LiveMapDisplayState, LiveMapDisplayState)] = [
            (.factualPending, .garminRaster),
            (.factual, .garminRaster),
            (.precise, .garminRaster),
            (.garminRaster, .factual),
            (.garminRaster, .factualPending),
            (.garminRaster, .precise),
        ]
        for (previous, next) in transitions {
            let sourceProjection = previous == .garminRaster ? garminProjection : preciseProjection
            let destinationProjection = next == .garminRaster ? garminProjection : preciseProjection
            let sourceOverlay = previous == .garminRaster ? garminOverlay : preciseOverlay
            let destinationOverlay = next == .garminRaster ? garminOverlay : preciseOverlay
            let interaction = LiveMapViewportInteraction(
                scale: 2,
                offset: CGSize(width: 12, height: -8),
                selectedHazardID: "water-0",
                targetPixel: try XCTUnwrap(GarminRasterProjectionMath.projectToPixel(
                    latitude: targetCoordinate.latitude,
                    longitude: targetCoordinate.longitude,
                    projection: sourceProjection
                )),
                greenPinPixel: try XCTUnwrap(GarminRasterProjectionMath.projectToPixel(
                    latitude: greenCoordinate.latitude,
                    longitude: greenCoordinate.longitude,
                    projection: sourceProjection
                ))
            )
            let result = LiveMapViewportTransition.preserve(
                previous: previous,
                next: next,
                viewportSize: CGSize(width: 390, height: 844),
                sourceFrame: previous == .garminRaster ? garminFrame : preciseFrame,
                destinationFrame: next == .garminRaster ? garminFrame : preciseFrame,
                sourceOverlay: sourceOverlay,
                destinationOverlay: destinationOverlay,
                sourceProjection: sourceProjection,
                destinationProjection: destinationProjection,
                targetCoordinate: targetCoordinate,
                greenPinCoordinate: greenCoordinate,
                interaction: interaction
            )
            let expectedTarget = try XCTUnwrap(GarminRasterProjectionMath.projectToPixel(
                latitude: targetCoordinate.latitude,
                longitude: targetCoordinate.longitude,
                projection: destinationProjection
            ))
            let expectedGreen = try XCTUnwrap(GarminRasterProjectionMath.projectToPixel(
                latitude: greenCoordinate.latitude,
                longitude: greenCoordinate.longitude,
                projection: destinationProjection
            ))
            XCTAssertEqual(result.targetPixel?.x ?? -1, expectedTarget.x, accuracy: 0.001, "\(previous) → \(next) target x")
            XCTAssertEqual(result.targetPixel?.y ?? -1, expectedTarget.y, accuracy: 0.001, "\(previous) → \(next) target y")
            XCTAssertEqual(result.greenPinPixel?.x ?? -1, expectedGreen.x, accuracy: 0.001, "\(previous) → \(next) green x")
            XCTAssertEqual(result.greenPinPixel?.y ?? -1, expectedGreen.y, accuracy: 0.001, "\(previous) → \(next) green y")
            let targetAfter = try XCTUnwrap(GarminRasterProjectionMath.projectFromPixel(
                try XCTUnwrap(result.targetPixel), projection: destinationProjection
            ))
            let greenAfter = try XCTUnwrap(GarminRasterProjectionMath.projectFromPixel(
                try XCTUnwrap(result.greenPinPixel), projection: destinationProjection
            ))
            XCTAssertEqual(targetAfter.latitude, targetCoordinate.latitude, accuracy: 1e-9, "\(previous) → \(next) target latitude")
            XCTAssertEqual(targetAfter.longitude, targetCoordinate.longitude, accuracy: 1e-9, "\(previous) → \(next) target longitude")
            XCTAssertEqual(greenAfter.latitude, greenCoordinate.latitude, accuracy: 1e-9, "\(previous) → \(next) green latitude")
            XCTAssertEqual(greenAfter.longitude, greenCoordinate.longitude, accuracy: 1e-9, "\(previous) → \(next) green longitude")
        }

        let sameSpaceInteraction = LiveMapViewportInteraction(
            scale: 2.4,
            offset: CGSize(width: 31, height: -12),
            selectedHazardID: "bunker-0",
            targetPixel: CGPoint(x: 88, y: 141),
            greenPinPixel: CGPoint(x: 91, y: 52)
        )
        for (previous, next) in [
            (LiveMapDisplayState.factual, LiveMapDisplayState.factualPending),
            (.factualPending, .precise),
            (.precise, .factual),
            (.waiting, .factualPending),
        ] {
            let result = LiveMapViewportTransition.preserve(
                previous: previous,
                next: next,
                viewportSize: .zero,
                sourceFrame: nil,
                destinationFrame: nil,
                sourceOverlay: nil,
                destinationOverlay: nil,
                sourceProjection: nil,
                destinationProjection: nil,
                targetCoordinate: nil,
                greenPinCoordinate: nil,
                interaction: sameSpaceInteraction
            )
            XCTAssertEqual(result, sameSpaceInteraction, "same pixel space \(previous) → \(next)")
        }
    }

    func testCrossSpaceTransitionKeepsMappedPointsBeforeFramesAreMeasured() throws {
        let preciseProjection = projection(
            originPixel: CGPoint(x: 120, y: 330),
            xPixel: CGPoint(x: 120, y: 30),
            yPixel: CGPoint(x: 240, y: 330)
        )
        let garminProjection = projection(
            originPixel: CGPoint(x: 621, y: 1740),
            xPixel: CGPoint(x: 621, y: 140),
            yPixel: CGPoint(x: 1242, y: 1740)
        )
        let targetCoordinate = CLLocationCoordinate2D(latitude: 40.0005, longitude: 116.0005)
        let greenCoordinate = CLLocationCoordinate2D(latitude: 40.0002, longitude: 116.0008)
        let interaction = LiveMapViewportInteraction(
            scale: 2,
            offset: CGSize(width: 12, height: -8),
            selectedHazardID: "water-0",
            targetPixel: try XCTUnwrap(GarminRasterProjectionMath.projectToPixel(
                latitude: targetCoordinate.latitude,
                longitude: targetCoordinate.longitude,
                projection: preciseProjection
            )),
            greenPinPixel: try XCTUnwrap(GarminRasterProjectionMath.projectToPixel(
                latitude: greenCoordinate.latitude,
                longitude: greenCoordinate.longitude,
                projection: preciseProjection
            ))
        )
        let result = LiveMapViewportTransition.preserve(
            previous: .factualPending,
            next: .garminRaster,
            viewportSize: .zero,
            sourceFrame: nil,
            destinationFrame: nil,
            sourceOverlay: nil,
            destinationOverlay: nil,
            sourceProjection: preciseProjection,
            destinationProjection: garminProjection,
            targetCoordinate: targetCoordinate,
            greenPinCoordinate: greenCoordinate,
            interaction: interaction
        )
        let expectedTarget = try XCTUnwrap(GarminRasterProjectionMath.projectToPixel(
            latitude: targetCoordinate.latitude,
            longitude: targetCoordinate.longitude,
            projection: garminProjection
        ))
        let expectedGreen = try XCTUnwrap(GarminRasterProjectionMath.projectToPixel(
            latitude: greenCoordinate.latitude,
            longitude: greenCoordinate.longitude,
            projection: garminProjection
        ))
        XCTAssertEqual(result.scale, interaction.scale)
        XCTAssertEqual(result.offset, interaction.offset)
        XCTAssertEqual(result.targetPixel?.x ?? -1, expectedTarget.x, accuracy: 0.001)
        XCTAssertEqual(result.targetPixel?.y ?? -1, expectedTarget.y, accuracy: 0.001)
        XCTAssertEqual(result.greenPinPixel?.x ?? -1, expectedGreen.x, accuracy: 0.001)
        XCTAssertEqual(result.greenPinPixel?.y ?? -1, expectedGreen.y, accuracy: 0.001)
    }

    func testRouteTierToGarminRemapsPointsAndKeepsViewportGeography() throws {
        let sourceProjection = projection(
            originPixel: CGPoint(x: 120, y: 330),
            xPixel: CGPoint(x: 120, y: 30),
            yPixel: CGPoint(x: 240, y: 330)
        )
        let destinationProjection = projection(
            originPixel: CGPoint(x: 621, y: 960),
            xPixel: CGPoint(x: 621, y: 0),
            yPixel: CGPoint(x: 1242, y: 960)
        )
        let sourceOverlay = CoursePrepOverlay(
            w: 240, h: 360, ppm: 1, ln: 300, route: [[120, 330, 0], [120, 30, 300]]
        )
        let destinationOverlay = CoursePrepOverlay(
            w: 1242, h: 1920, ppm: 2, ln: 300, route: [[390, 1740, 0], [390, 140, 300]]
        )
        let targetCoordinate = CLLocationCoordinate2D(latitude: 40.0005, longitude: 116.0005)
        let greenCoordinate = CLLocationCoordinate2D(latitude: 40.0002, longitude: 116.0008)
        let interaction = LiveMapViewportInteraction(
            scale: 2,
            offset: CGSize(width: 12, height: -8),
            selectedHazardID: "water-0",
            targetPixel: try XCTUnwrap(GarminRasterProjectionMath.projectToPixel(
                latitude: targetCoordinate.latitude,
                longitude: targetCoordinate.longitude,
                projection: sourceProjection
            )),
            greenPinPixel: try XCTUnwrap(GarminRasterProjectionMath.projectToPixel(
                latitude: greenCoordinate.latitude,
                longitude: greenCoordinate.longitude,
                projection: sourceProjection
            ))
        )
        let viewport = CGSize(width: 390, height: 844)
        let sourceFrame = CGRect(x: 75, y: 100, width: 240, height: 360)
        let destinationFrame = CGRect(x: 0, y: 80, width: 390, height: 603)
        let result = LiveMapViewportTransition.preserve(
            previous: .factual,
            next: .garminRaster,
            viewportSize: viewport,
            sourceFrame: sourceFrame,
            destinationFrame: destinationFrame,
            sourceOverlay: sourceOverlay,
            destinationOverlay: destinationOverlay,
            sourceProjection: sourceProjection,
            destinationProjection: destinationProjection,
            targetCoordinate: targetCoordinate,
            greenPinCoordinate: greenCoordinate,
            interaction: interaction
        )
        let expectedTarget = try XCTUnwrap(GarminRasterProjectionMath.projectToPixel(
            latitude: targetCoordinate.latitude,
            longitude: targetCoordinate.longitude,
            projection: destinationProjection
        ))
        let expectedGreen = try XCTUnwrap(GarminRasterProjectionMath.projectToPixel(
            latitude: greenCoordinate.latitude,
            longitude: greenCoordinate.longitude,
            projection: destinationProjection
        ))
        XCTAssertEqual(result.targetPixel?.x ?? -1, expectedTarget.x, accuracy: 0.001)
        XCTAssertEqual(result.targetPixel?.y ?? -1, expectedTarget.y, accuracy: 0.001)
        XCTAssertEqual(result.greenPinPixel?.x ?? -1, expectedGreen.x, accuracy: 0.001)
        XCTAssertEqual(result.greenPinPixel?.y ?? -1, expectedGreen.y, accuracy: 0.001)

        func centerCoordinate(
            frame: CGRect,
            overlay: CoursePrepOverlay,
            projection: CoursePrepHoleImageProjection,
            scale: CGFloat,
            offset: CGSize
        ) -> CLLocationCoordinate2D? {
            let center = CGPoint(x: viewport.width / 2, y: viewport.height / 2)
            let base = CGPoint(
                x: center.x - offset.width / scale,
                y: center.y - offset.height / scale
            )
            let pixel = CGPoint(
                x: (base.x - frame.minX) / frame.width * CGFloat(overlay.w),
                y: (base.y - frame.minY) / frame.height * CGFloat(overlay.h)
            )
            return GarminRasterProjectionMath.projectFromPixel(pixel, projection: projection)
        }
        let beforeCenter = try XCTUnwrap(centerCoordinate(
            frame: sourceFrame, overlay: sourceOverlay, projection: sourceProjection,
            scale: interaction.scale, offset: interaction.offset
        ))
        let afterCenter = try XCTUnwrap(centerCoordinate(
            frame: destinationFrame, overlay: destinationOverlay, projection: destinationProjection,
            scale: result.scale, offset: result.offset
        ))
        XCTAssertEqual(afterCenter.latitude, beforeCenter.latitude, accuracy: 1e-9)
        XCTAssertEqual(afterCenter.longitude, beforeCenter.longitude, accuracy: 1e-9)
    }

    func testGarminToPreciseViewportTransitionRemapsPixelOnlyPoints() throws {
        let garmin = projection(
            originPixel: CGPoint(x: 80, y: 1740),
            xPixel: CGPoint(x: 80, y: 140),
            yPixel: CGPoint(x: 700, y: 1740)
        )
        let precise = projection(
            originPixel: CGPoint(x: 120, y: 330),
            xPixel: CGPoint(x: 120, y: 30),
            yPixel: CGPoint(x: 240, y: 330)
        )
        let sourceOverlay = CoursePrepOverlay(
            w: 1242, h: 1920, ppm: 2, ln: 300, route: [[390, 1740, 0], [390, 140, 300]]
        )
        let destinationOverlay = CoursePrepOverlay(
            w: 240, h: 360, ppm: 1, ln: 300, route: [[120, 330, 0], [120, 30, 300]]
        )
        let sourcePoint = try XCTUnwrap(GarminRasterProjectionMath.projectToPixel(
            latitude: 40.0005, longitude: 116.0005, projection: garmin
        ))
        let interaction = LiveMapViewportInteraction(
            scale: 2, offset: .zero, selectedHazardID: "water-0",
            targetPixel: sourcePoint, greenPinPixel: sourcePoint
        )
        let result = LiveMapViewportTransition.preserve(
            previous: .garminRaster,
            next: .precise,
            viewportSize: CGSize(width: 390, height: 844),
            sourceFrame: CGRect(x: 0, y: 80, width: 390, height: 603),
            destinationFrame: CGRect(x: 75, y: 100, width: 240, height: 360),
            sourceOverlay: sourceOverlay,
            destinationOverlay: destinationOverlay,
            sourceProjection: garmin,
            destinationProjection: precise,
            targetCoordinate: nil,
            greenPinCoordinate: nil,
            interaction: interaction
        )
        let expected = try XCTUnwrap(GarminRasterProjectionMath.remap(
            pixel: sourcePoint, from: garmin, to: precise
        ))
        XCTAssertEqual(result.targetPixel?.x ?? -1, expected.x, accuracy: 0.001)
        XCTAssertEqual(result.targetPixel?.y ?? -1, expected.y, accuracy: 0.001)
        XCTAssertEqual(result.greenPinPixel?.x ?? -1, expected.x, accuracy: 0.001)
        XCTAssertEqual(result.greenPinPixel?.y ?? -1, expected.y, accuracy: 0.001)
    }

    func testRouteTierToUnregisteredGarminClearsPixelOnlyPoints() {
        let interaction = LiveMapViewportInteraction(
            scale: 2.2,
            offset: CGSize(width: 10, height: -6),
            selectedHazardID: "water-0",
            targetPixel: CGPoint(x: 120, y: 180),
            greenPinPixel: CGPoint(x: 120, y: 30)
        )
        let result = LiveMapViewportTransition.preserve(
            previous: .factual,
            next: .garminRaster,
            viewportSize: CGSize(width: 390, height: 844),
            sourceFrame: CGRect(x: 75, y: 100, width: 240, height: 360),
            destinationFrame: CGRect(x: 0, y: 80, width: 390, height: 603),
            sourceOverlay: CoursePrepOverlay(w: 240, h: 360, ppm: 1, ln: 300, route: []),
            destinationOverlay: CoursePrepOverlay(w: 1242, h: 1920, ppm: 1, ln: 0, route: []),
            sourceProjection: nil,
            destinationProjection: nil,
            targetCoordinate: nil,
            greenPinCoordinate: nil,
            interaction: interaction
        )
        XCTAssertEqual(result.scale, interaction.scale)
        XCTAssertEqual(result.offset, interaction.offset)
        XCTAssertNil(result.targetPixel)
        XCTAssertNil(result.greenPinPixel)
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
            LiveMapDisplaySelection.mapFrameOverlay(
                for: .garminRaster,
                overlay: nil,
                garminProjection: nil
            )
        )
        let gestureOverlay = try XCTUnwrap(
            LiveMapDisplaySelection.gestureFrameOverlay(
                for: .garminRaster,
                overlay: nil,
                garminProjection: nil
            )
        )
        XCTAssertEqual(overlay, gestureOverlay)
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

    func testGarminWithoutOverlayUsesSameFramedRasterForGestures() throws {
        let overlay = try XCTUnwrap(
            LiveMapDisplaySelection.mapFrameOverlay(
                for: .garminRaster,
                overlay: nil,
                garminProjection: nil
            )
        )
        let gestureOverlay = try XCTUnwrap(
            LiveMapDisplaySelection.gestureFrameOverlay(
                for: .garminRaster,
                overlay: nil,
                garminProjection: nil
            )
        )
        XCTAssertEqual(overlay, gestureOverlay)
        let viewport = CGSize(width: 390, height: 844)
        let rasterFrame = try XCTUnwrap(
            LivePlayMapOverlayLayout.lightweightFittedFrame(
                overlay: overlay,
                viewport: viewport,
                chrome: []
            )
        )
        let gestureFrame = try XCTUnwrap(
            LivePlayMapOverlayLayout.mapFrame(
                overlayWidth: overlay.w,
                overlayHeight: overlay.h,
                in: viewport,
                topInset: LivePlayMapOverlayLayout.liveMapTopInset,
                fittedFrame: rasterFrame
            )
        )

        XCTAssertGreaterThan(rasterFrame.width, 0)
        XCTAssertGreaterThan(rasterFrame.height, 0)
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
