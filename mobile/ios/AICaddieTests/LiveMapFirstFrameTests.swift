#if !SWIFT_PACKAGE && canImport(UIKit)
import Foundation
import UIKit
import XCTest
@testable import AICaddie

@MainActor
final class LiveMapFirstFrameTests: XCTestCase {
    /// J4.5-1: an installed precise map owns the first frame even before decode completes.
    func testKnownPreciseTopoNeverFallsBackToGarminBeforeDecode() throws {
        // Either availability signal reserves the precise map, with or without a ready Garmin.
        for (available, cached) in [(true, false), (false, true)] {
            for garminReady in [true, false] {
                let state = LiveMapDisplayState.resolveLive(.init(
                    coverage: "ready",
                    preciseTopoImageReady: false,
                    garminRaster: GarminRasterResponse(available: true, imageUrl: "/garmin.png"),
                    garminImageReady: garminReady,
                    garminImageFailed: false,
                    hasCachedPreciseTopo: cached,
                    preciseTopoAvailable: available
                ))
                try assertNeutralDecodeFrame(state)
            }
        }
    }

    /// J4.5-1: first hole, strip jumps, resume, and trimmed pages discover installed pixels
    /// before any SwiftUI task runs, even when Garmin is already decoded.
    func testInstalledTopoOwnsInitialFrameWithoutSessionPath() throws {
        let package = try ProductInputs.package()
        let directory = FileManager.default.temporaryDirectory
            .appendingPathComponent("first-frame-\(UUID().uuidString)", isDirectory: true)
        defer { try? FileManager.default.removeItem(at: directory) }
        let store = OfflineStore(directoryURL: directory)
        let png = Data(base64Encoded:
            "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII="
        )!
        let rasterURL = URL(string: "https://first-frame.example.test/\(UUID().uuidString).png")!
        GarminRasterImageStore.preload(try XCTUnwrap(UIImage(data: png)), for: rasterURL)
        defer { GarminRasterImageStore.evict(rasterURL) }
        for (number, resumed, trimmed) in [(1, false, false), (7, false, false),
                                           (12, true, false), (7, false, true)] {
            let hole = try XCTUnwrap(package.holes.first { $0.number == number })
            let cache = LiveHoleSessionCache()
            let revision = LiveTopoAvailability.revision(hole: hole, prep: nil)
            XCTAssertTrue(try store.saveCourseTopoImage(
                png, globalId: hole.sourceGlobalId, localHole: hole.sourceLocalHole,
                geometryRevision: revision
            ))
            cache.update(
                roundId: package.roundId, hole: number, sourceGlobalId: hole.sourceGlobalId,
                sourceLocalHole: hole.sourceLocalHole, teeBox: package.course.teeBox,
                geometryRevision: revision
            ) { entry in
                entry.garminRaster = GarminRasterResponse(available: true, imageUrl: rasterURL.absoluteString)
                if trimmed {
                    entry.localTopoURL = LiveTopoAvailability.localTopoURL(
                        store: store, globalId: hole.sourceGlobalId,
                        localHole: hole.sourceLocalHole, geometryRevision: revision
                    )
                }
            }
            if trimmed { cache.trim(roundId: package.roundId, keepingHoles: [1]) }
            let view = CurrentHoleView(
                package: package, hole: hole,
                caddieBaseURL: URL(string: "https://first-frame.example.test"), offlineStore: store,
                liveRoundState: resumed ? .init(roundId: package.roundId, activeHole: number, holes: []) : nil,
                sessionCache: cache
            )
            try assertNeutralDecodeFrame(view.liveMapDisplayStateForTesting())
        }
    }

    /// J4.5: neutral ground has no map plane to zoom or pan.
    func testNeutralDecodeFrameIgnoresMapScaleAndOffset() {
        XCTAssertEqual(LiveMapDisplaySelection.gestureScale(for: .factualPending, proposed: 4), 1)
        XCTAssertEqual(LiveMapDisplaySelection.gestureOffset(
            for: .factualPending, proposed: CGSize(width: 120, height: -80)
        ), .zero)
    }

    /// J4.5: a visible map can shrink continuously from 2x to 1x; a neutral frame ignores the
    /// same pinch. Relative magnification must not be clamped like the final displayed scale.
    func testPinchCanShrinkVisibleMapsButCannotZoomNeutralGround() {
        for state: LiveMapDisplayState in [.precise, .garminRaster] {
            let multiplier = LiveMapDisplaySelection.gestureMagnification(for: state, proposed: 0.5)
            XCTAssertEqual(LiveMapDisplaySelection.gestureScale(for: state, proposed: 2 * multiplier), 1)
        }
        for state: LiveMapDisplayState in [.factualPending, .waiting] {
            XCTAssertEqual(LiveMapDisplaySelection.gestureMagnification(for: state, proposed: 3), 1)
            XCTAssertEqual(LiveMapDisplaySelection.gestureScale(for: state, proposed: 3), 1)
        }
    }

    /// J4.5-2: a local file repaired during automatic retry recovers without leaving the hole.
    func testLocalDecodeRetriesReadRepairedFileWithoutChangingURL() async throws {
        let url = FileManager.default.temporaryDirectory
            .appendingPathComponent("decode-retry-\(UUID().uuidString).png")
        defer {
            TopoHoleImageStore.retrySleepForTesting = nil
            TopoHoleImageStore.evict(url)
            try? FileManager.default.removeItem(at: url)
        }
        try Data("broken png".utf8).write(to: url)
        var delays: [UInt64] = []
        TopoHoleImageStore.retrySleepForTesting = { delay in
            delays.append(delay)
            let png = Data(base64Encoded:
                "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII="
            )!
            try png.write(to: url, options: .atomic)
        }
        let ready = await TopoHoleImageStore.ensureLoaded(url)
        XCTAssertTrue(ready, "a repaired local PNG must recover on the same page")
        XCTAssertEqual(delays, [5_000_000_000])
        XCTAssertTrue(TopoHoleImageStore.isMemoryCached(url))
    }

    /// J4.5-2: corrupt files stop after two retries; a later explicit load can recover.
    func testLocalDecodeRetriesAreBoundedAndCanBeRestarted() async throws {
        let url = FileManager.default.temporaryDirectory
            .appendingPathComponent("decode-exhausted-\(UUID().uuidString).png")
        defer {
            TopoHoleImageStore.retrySleepForTesting = nil
            TopoHoleImageStore.evict(url)
            try? FileManager.default.removeItem(at: url)
        }
        try Data("broken png".utf8).write(to: url)
        var delays: [UInt64] = []
        TopoHoleImageStore.retrySleepForTesting = { delays.append($0) }
        let failed = await TopoHoleImageStore.ensureLoaded(url)
        XCTAssertFalse(failed)
        XCTAssertEqual(delays, [5_000_000_000, 15_000_000_000])
        let png = Data(base64Encoded:
            "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII="
        )!
        try png.write(to: url, options: .atomic)
        let recovered = await TopoHoleImageStore.ensureLoaded(url)
        XCTAssertTrue(recovered)
        XCTAssertEqual(delays.count, 2, "explicit retry starts immediately")
    }

    private func assertNeutralDecodeFrame(
        _ state: LiveMapDisplayState,
        file: StaticString = #filePath,
        line: UInt = #line
    ) throws {
        let prep = try ProductInputs.prep()
        let overlay = try XCTUnwrap(prep.resolvedMapOverlay)
        let projection = CoursePrepHoleImageProjection(
            available: true, widthPx: 300, heightPx: 400,
            refs: [
                CoursePrepProjectionRef(lat: 0, lon: 0, px: 100, py: 350),
                CoursePrepProjectionRef(lat: 0, lon: 0.001, px: 200, py: 350),
                CoursePrepProjectionRef(lat: 0.001, lon: 0, px: 100, py: 250),
            ]
        )
        XCTAssertNotEqual(state, .garminRaster, file: file, line: line)
        XCTAssertNotEqual(state, .waiting, "No preparation/spinner page during local decode", file: file, line: line)
        XCTAssertEqual(state, .factualPending, file: file, line: line)
        XCTAssertNil(LiveMapDisplaySelection.overlay(
            for: state, precise: overlay, preciseProjection: projection, garminProjection: projection
        ), "J4.5 no route/label/target/flag over the neutral frame", file: file, line: line)
        XCTAssertNil(LiveMapDisplaySelection.projection(
            for: state, precise: projection, garmin: projection
        ), file: file, line: line)
        XCTAssertNil(LiveMapDisplaySelection.mapFrameOverlay(
            for: state, overlay: overlay, garminProjection: projection
        ), file: file, line: line)
        XCTAssertNil(LiveMapDisplaySelection.gestureFrameOverlay(
            for: state, overlay: overlay, garminProjection: projection
        ), file: file, line: line)
    }

    /// J4.5-1: a local precise map without a prep route also gets a neutral decode frame.
    func testKnownPreciseTopoWithNoPrepRouteKeepsNeutralPendingFrame() throws {
        let inputs = LiveMapDisplayState.liveInputs(
            coverage: "ready",
            decodeFailed: false,
            resolvedLocalTopoURL: URL(fileURLWithPath: "/tmp/known-topo.png"),
            hasLiveTopoURL: true,
            hasEmbeddedTopoImage: false,
            preciseTopoImageReady: false,
            memoryCached: false,
            garminRaster: GarminRasterResponse(available: true, imageUrl: "/garmin.png"),
            garminImageReady: true,
            garminImageFailed: false,
            hasRoute: false
        )
        try assertNeutralDecodeFrame(LiveMapDisplayState.resolveLive(inputs))
    }

    /// J4.5-1/2: a failed local decode releases the neutral frame for the ready Garmin bitmap.
    func testFailedPreciseDecodeAllowsReadyGarminFallback() {
        let inputs = LiveMapDisplayState.liveInputs(
            coverage: "ready",
            decodeFailed: true,
            resolvedLocalTopoURL: URL(fileURLWithPath: "/tmp/broken-topo.png"),
            hasLiveTopoURL: true,
            hasEmbeddedTopoImage: false,
            preciseTopoImageReady: false,
            memoryCached: false,
            garminRaster: GarminRasterResponse(available: true, imageUrl: "/garmin.png"),
            garminImageReady: true,
            garminImageFailed: false
        )
        let state = LiveMapDisplayState.resolveLive(inputs)
        XCTAssertEqual(state, .garminRaster)
    }

    /// J4.5-1/2: decode failure overrides stale cache/readiness signals and releases Garmin.
    func testFailedCachedPreciseDecodeAllowsGarminDespiteStaleReadySignals() {
        let inputs = LiveMapDisplayState.liveInputs(
            coverage: "ready", decodeFailed: true,
            resolvedLocalTopoURL: URL(fileURLWithPath: "/tmp/failed-cached-topo.png"),
            hasLiveTopoURL: true, hasEmbeddedTopoImage: false,
            preciseTopoImageReady: true, memoryCached: true,
            garminRaster: GarminRasterResponse(available: true, imageUrl: "/garmin.png"),
            garminImageReady: true, garminImageFailed: false
        )
        XCTAssertEqual(LiveMapDisplayState.resolveLive(inputs), .garminRaster)
    }

    /// J4.5-1/4: local decode completion promotes to precise; failure without Garmin waits neutrally.
    func testLocalPreciseDecodeCompletionAndFailureWithoutGarmin() {
        for failed in [false, true] {
            let inputs = LiveMapDisplayState.liveInputs(
                coverage: "ready", decodeFailed: failed,
                resolvedLocalTopoURL: URL(fileURLWithPath: "/tmp/installed-topo.png"),
                hasLiveTopoURL: true, hasEmbeddedTopoImage: false,
                preciseTopoImageReady: !failed, memoryCached: false,
                garminRaster: nil, garminImageReady: false, garminImageFailed: false
            )
            XCTAssertEqual(LiveMapDisplayState.resolveLive(inputs), failed ? .waiting : .precise)
        }
    }

    func testNeighbourLookupUsesTheSameLocalURLThatPrefetchDecodes() async throws {
        let directory = FileManager.default.temporaryDirectory
            .appendingPathComponent("live-map-first-frame-\(UUID().uuidString)", isDirectory: true)
        defer { try? FileManager.default.removeItem(at: directory) }
        let store = OfflineStore(directoryURL: directory)
        let png = Data(base64Encoded:
            "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII="
        )!
        XCTAssertTrue(try store.saveCourseTopoImage(png, globalId: 42, localHole: 3, geometryRevision: "r1"))
        let url = LiveTopoAvailability.localTopoURL(
            store: store, globalId: 42, localHole: 3, geometryRevision: "r1"
        )
        XCTAssertTrue(url?.isFileURL == true)
        let loaded = await TopoHoleImageStore.ensureLoaded(url)
        XCTAssertTrue(loaded)
        XCTAssertTrue(TopoHoleImageStore.isMemoryCached(url))
    }
}
#endif
