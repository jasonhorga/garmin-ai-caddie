#if !SWIFT_PACKAGE && canImport(UIKit)
import Foundation
import UIKit
import XCTest
@testable import AICaddie

@MainActor
final class LiveMapFirstFrameTests: XCTestCase {
    func testKnownPreciseTopoNeverFallsBackToGarminBeforeDecode() {
        let descriptor = GarminRasterResponse(available: true, imageUrl: "/garmin.png")
        let state = LiveMapDisplayState.resolveLive(.init(
            coverage: "ready",
            preciseTopoImageReady: false,
            garminRaster: descriptor,
            garminImageReady: true,
            garminImageFailed: false,
            hasCachedPreciseTopo: false,
            preciseTopoAvailable: true
        ))
        XCTAssertNotEqual(state, .garminRaster)
        XCTAssertEqual(state, .factualPending)
    }

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
