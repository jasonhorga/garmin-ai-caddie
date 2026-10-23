"""Card 454: show the Garmin hole raster while the precise phone map is pending.

The native iOS target only runs on the macOS native-mobile runner. These offline checks pin the
Swift contract, endpoint/cache wiring, projection math and the two required snapshot test names so
the card's six acceptance cases remain reviewable on Linux as well.
"""

from __future__ import annotations

import math
import re
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
IOS = ROOT / "mobile" / "ios"
CURRENT = IOS / "AICaddie" / "Views" / "CurrentHoleView.swift"
COMPONENTS = IOS / "AICaddie" / "Views" / "LiveHoleComponents.swift"
MAP = IOS / "AICaddie" / "Views" / "HoleImageMapView.swift"
MODEL = IOS / "AICaddie" / "Models" / "GarminRaster.swift"
CACHE = IOS / "AICaddie" / "Views" / "GarminRasterImageStore.swift"
SYNC = IOS / "AICaddie" / "Services" / "SyncClient.swift"
SNAPSHOTS = IOS / "AICaddieTests" / "DesignSnapshotTests.swift"
NATIVE = IOS / "AICaddieTests" / "GarminRasterTests.swift"


def source(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def project(lat: float, lon: float, refs: list[tuple[float, float, float, float]]) -> tuple[float, float]:
    """The same relative 2×2 affine solve used by GarminRasterProjectionMath."""

    o, x, y = refs[:3]
    a, b = x[1] - o[1], y[1] - o[1]
    c, d = x[0] - o[0], y[0] - o[0]
    determinant = a * d - b * c
    assert abs(determinant) > 1e-12
    dl, da = lon - o[1], lat - o[0]
    s = (dl * d - b * da) / determinant
    t = (a * da - dl * c) / determinant
    return (o[2] + s * (x[2] - o[2]) + t * (y[2] - o[2]),
            o[3] + s * (x[3] - o[3]) + t * (y[3] - o[3]))


class Card454AcceptanceTests(unittest.TestCase):
    def test_state_priority_and_current_projection_contract(self) -> None:
        components = source(COMPONENTS)
        current = source(CURRENT)
        self.assertIn("case garminRaster", components)
        self.assertIn("case numericPlaceholder", components)
        self.assertIn("static func resolveLive(", components)
        self.assertIn("preciseTopoImageReady: hasPreciseTopoImage", current)
        self.assertIn("garminImageFailed: garminRasterImageFailed || garminRasterImageRetrying", current)
        self.assertIn("if liveMapDisplayState == .garminRaster", current)
        self.assertIn("garminRasterProjection: liveMapDisplayState == .garminRaster", current)
        self.assertIn("LiveMapDisplaySelection.projection(", current)
        self.assertIn("LiveMapDisplaySelection.overlay(", current)
        self.assertIn("garminRasterImageReloadID", current)
        self.assertIn("gestureFrameOverlay(", components)
        self.assertIn("gestureScale(", components)
        self.assertIn("if garminRasterURL != nil, garminRasterProjection?.isUsable != true { return }", source(IOS / "AICaddie" / "Views" / "HoleImageMapView.swift"))
        self.assertIn("static func resolveLive(", components)

    def test_raster_available_path_uses_image_and_projection(self) -> None:
        current = source(CURRENT)
        mapping = source(MAP)
        self.assertIn('"live-hole-map-garmin-raster"', current)
        self.assertIn("garminRasterURL: liveMapDisplayState == .garminRaster", current)
        self.assertIn("GarminRasterProjectionMath.remapOverlay(", mapping)
        self.assertIn("private var displayProjection", mapping)
        self.assertIn("TopoHoleBaseImage(", mapping)
        self.assertIn("garminRasterURL: garminRasterURL", mapping)
        self.assertIn("onGarminImageFailed", mapping)

    def test_precise_replaces_raster_and_numeric_placeholder_has_required_copy(self) -> None:
        current = source(CURRENT)
        components = source(COMPONENTS)
        self.assertIn("liveMapDisplayState == .precise", current)
        self.assertIn("LiveMapNumericPlaceholder(", current)
        self.assertIn('Text("正在下载")', components)
        self.assertIn('live-map-numeric-placeholder', components)
        self.assertIn("GarminRasterStandaloneView", current)
        self.assertIn("easeInOut(duration: 0.25)", current)
        backdrop = current[current.index("@ViewBuilder private var liveMapBackdrop"):]
        self.assertNotIn("LiveMapPreparingSurface(", backdrop)
        self.assertNotIn("HoleMapWaitingPage(", backdrop)

    def test_known_refs_preserve_pixel_and_geographic_center(self) -> None:
        source_refs = [
            (40.0, 116.0, 80.0, 140.0),
            (40.0, 116.001, 80.0, 1740.0),
            (40.001, 116.0, 700.0, 140.0),
        ]
        raster_px = project(40.0005, 116.0005, source_refs)
        self.assertAlmostEqual(raster_px[0], 390.0, delta=0.5)
        self.assertAlmostEqual(raster_px[1], 940.0, delta=0.5)
        destination_refs = [
            (40.0, 116.0, 120.0, 40.0),
            (40.0, 116.001, 120.0, 1000.0),
            (40.001, 116.0, 700.0, 40.0),
        ]
        topo_px = project(40.0005, 116.0005, destination_refs)
        self.assertAlmostEqual(topo_px[0], 410.0, delta=0.5)
        self.assertAlmostEqual(topo_px[1], 520.0, delta=0.5)
        model = source(MODEL)
        for function_name in ("projectToPixel", "projectFromPixel", "remap", "remapOverlay"):
            self.assertRegex(model, rf"static func {function_name}\b")
        self.assertIn("pixelsPerMetre", model)
        self.assertIn("GarminRasterViewportTransfer", model)

    def test_endpoint_errors_degrade_and_assets_are_versioned_cached(self) -> None:
        sync = source(SYNC)
        cache = source(CACHE)
        self.assertIn("/garmin-raster", sync)
        self.assertIn('public static let garminRasterStyleVersion = "garmin-raster-v1"', sync)
        self.assertIn("AICaddieGarminRasterImages-v1", cache)
        self.assertIn("AICaddieGarminRasterMetadata-v1", cache)
        self.assertIn("request_failed", source(CURRENT))
        self.assertIn('URLComponents(string: $0)?.queryItems?.first(where: { $0.name == "v" })?.value', cache)
        self.assertIn("statusCode == 409", cache)
        self.assertIn("retryAttemptByURL", cache)
        self.assertIn("retryDelaysNanoseconds: [UInt64] = [0, 5_000_000_000, 15_000_000_000]", source(IOS / "AICaddie" / "Views" / "TopoHoleBaseImage.swift"))

    def test_native_tests_and_design_snapshots_cover_all_six_cases(self) -> None:
        native = source(NATIVE)
        snapshots = source(SNAPSHOTS)
        expected_native = (
            "testTopoPendingRasterAvailableUsesRasterProjection",
            "testTopoReadyWinsOverRasterAndUsesTopoProjection",
            "testPartialWithoutCachedTopoDoesNotEnterPreciseOrReuseProjection",
            "testNumericPlaceholderGestureStateResetsScaleAndOffset",
            "testGarminWithoutProjectionGestureFrameClampsToFallbackRaster",
            "testUnavailableRasterFallsBackToNumericPlaceholderState",
            "testRasterToTopoTransferKeepsGeographicViewportCenter",
            "testSameCoordinateIsPixelAccurateInBothProjectionFrames",
            "testRasterFailureReasonDoesNotCrashAndIsNotUsable",
            "testRaster500AndTimeoutAreOrdinaryErrors",
            "testUnavailableProjectionShowsImageWithoutOverlays",
        )
        for name in expected_native:
            self.assertIn(f"func {name}", native)
        self.assertIn('named: "live-garmin-raster-position"', snapshots)
        self.assertIn('named: "live-numeric-placeholder"', snapshots)
        self.assertIn('named: "live-garmin-raster-loading"', snapshots)
        self.assertNotIn('named: "live-garmin-raster-precise-replacement"', snapshots)
        self.assertIn("func testCaptureGarminRasterWithPosition", snapshots)
        self.assertIn("func testCaptureLiveNumericMapPlaceholder", snapshots)


if __name__ == "__main__":
    unittest.main()
