import XCTest
@testable import AICaddieWatch

/// watch P0.4: the on-device per-hole topo image cache (phone → watch WatchConnectivity file transfer).
final class WatchHoleImageStoreTests: XCTestCase {
    private func tempStore() -> (WatchHoleImageStore, URL) {
        let dir = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString)
        return (WatchHoleImageStore(directoryURL: dir), dir)
    }

    func testStoreThenReadByGidAndHole() throws {
        let (store, _) = tempStore()
        XCTAssertFalse(store.hasImage(globalId: 31833, hole: 1))
        let data = try XCTUnwrap(Data(base64Encoded: WatchHoleMapSample.jpegBase64))
        try store.store(data: data, globalId: 31833, hole: 1)
        XCTAssertTrue(store.hasImage(globalId: 31833, hole: 1))
        XCTAssertEqual(store.data(globalId: 31833, hole: 1), data)
    }

    func testMissingHoleReadsNil() {
        let (store, _) = tempStore()
        XCTAssertNil(store.data(globalId: 31833, hole: 7))
        XCTAssertFalse(store.hasImage(globalId: 31833, hole: 7))
    }

    func testRepushOverwrites() throws {
        let (store, _) = tempStore()
        let jpeg = try XCTUnwrap(Data(base64Encoded: WatchHoleMapSample.jpegBase64))
        let png = try XCTUnwrap(Data(base64Encoded: Self.onePixelPNGBase64))
        try store.store(data: jpeg, globalId: 42, hole: 3)
        try store.store(data: png, globalId: 42, hole: 3)
        XCTAssertEqual(store.data(globalId: 42, hole: 3), png)
    }

    func testGeometryRevisionsAreSeparateAndOldOfflinePixelsRemainAvailable() throws {
        let (store, _) = tempStore()
        let jpeg = try XCTUnwrap(Data(base64Encoded: WatchHoleMapSample.jpegBase64))
        let png = try XCTUnwrap(Data(base64Encoded: Self.onePixelPNGBase64))
        let revisionA = "aaaaaaaaaaaaaaaa"
        let revisionB = "bbbbbbbbbbbbbbbb"

        try store.store(
            data: jpeg,
            globalId: 42,
            hole: 3,
            geometryRevision: revisionA
        )
        XCTAssertEqual(store.data(
            globalId: 42,
            hole: 3,
            geometryRevision: revisionA
        ), jpeg)
        XCTAssertNil(store.data(
            globalId: 42,
            hole: 3,
            geometryRevision: revisionB
        ))
        XCTAssertNil(store.data(globalId: 42, hole: 3))

        try store.store(
            data: png,
            globalId: 42,
            hole: 3,
            geometryRevision: revisionB
        )
        XCTAssertEqual(store.data(
            globalId: 42,
            hole: 3,
            geometryRevision: revisionA
        ), jpeg)
        XCTAssertEqual(store.data(
            globalId: 42,
            hole: 3,
            geometryRevision: revisionB
        ), png)
    }

    func testRejectsPlaceholderHTMLAndTruncatedImages() throws {
        let (store, _) = tempStore()
        let truncatedJPEG = Data([0xFF, 0xD8, 0xFF] + Array(repeating: 0, count: 100))

        for invalid in [Data([1, 2, 3, 4]), Data("<html>bad gateway</html>".utf8), truncatedJPEG] {
            XCTAssertThrowsError(try store.store(data: invalid, globalId: 42, hole: 3)) {
                XCTAssertEqual($0 as? WatchHoleImageStoreError, .invalidImageData)
            }
        }
        XCTAssertFalse(store.hasImage(globalId: 42, hole: 3))
    }

    func testFailedReplacementKeepsThePreviousValidImage() throws {
        let (store, directory) = tempStore()
        let original = try XCTUnwrap(Data(base64Encoded: WatchHoleMapSample.jpegBase64))
        try store.store(data: original, globalId: 42, hole: 3)
        let received = directory.appendingPathComponent("received.img")
        try Data("not an image".utf8).write(to: received)

        XCTAssertThrowsError(try store.store(fileURL: received, globalId: 42, hole: 3))
        XCTAssertEqual(store.data(globalId: 42, hole: 3), original)
    }

    func testLegacyCorruptCacheFileIsNotAdvertisedAsAnImage() throws {
        let (store, directory) = tempStore()
        let imageDirectory = directory
            .appendingPathComponent("hole-images", isDirectory: true)
            .appendingPathComponent(WatchBackendClient.topoStyleVersion, isDirectory: true)
        let target = imageDirectory.appendingPathComponent("42_3.img")
        try Data([1, 2, 3, 4]).write(to: target)

        XCTAssertNil(store.data(globalId: 42, hole: 3))
        XCTAssertFalse(store.hasImage(globalId: 42, hole: 3))
    }

    func testLegacyUnversionedImageIsNotReusedAfterRendererUpgrade() throws {
        let (_, directory) = tempStore()
        let legacyDirectory = directory.appendingPathComponent("hole-images", isDirectory: true)
        try FileManager.default.createDirectory(at: legacyDirectory, withIntermediateDirectories: true)
        let image = try XCTUnwrap(Data(base64Encoded: WatchHoleMapSample.jpegBase64))
        try image.write(to: legacyDirectory.appendingPathComponent("42_3.img"), options: .atomic)

        let upgradedStore = WatchHoleImageStore(directoryURL: directory)

        XCTAssertFalse(upgradedStore.hasImage(globalId: 42, hole: 3))
        XCTAssertNil(upgradedStore.data(globalId: 42, hole: 3))
    }

    func testStoredImageLivesUnderCurrentRendererVersion() throws {
        let (store, directory) = tempStore()
        let image = try XCTUnwrap(Data(base64Encoded: WatchHoleMapSample.jpegBase64))

        try store.store(data: image, globalId: 42, hole: 3)

        XCTAssertTrue(
            FileManager.default.fileExists(
                atPath: directory
                    .appendingPathComponent("hole-images", isDirectory: true)
                    .appendingPathComponent(WatchBackendClient.topoStyleVersion, isDirectory: true)
                    .appendingPathComponent("42_3.img")
                    .path
            )
        )
    }

    #if canImport(UIKit)
    func testRepeatedImageReadsReuseTheDecodedObject() throws {
        let (writer, directory) = tempStore()
        let data = try XCTUnwrap(Data(base64Encoded: WatchHoleMapSample.jpegBase64))
        try writer.store(data: data, globalId: 42, hole: 3)
        let reader = WatchHoleImageStore(directoryURL: directory)

        let first = try XCTUnwrap(reader.image(globalId: 42, hole: 3))
        let second = try XCTUnwrap(reader.image(globalId: 42, hole: 3))

        XCTAssertTrue(first === second)
    }

    func testWriterFacadeInvalidatesTheRendererFacadeCache() throws {
        let (writer, directory) = tempStore()
        let jpeg = try XCTUnwrap(Data(base64Encoded: WatchHoleMapSample.jpegBase64))
        let png = try XCTUnwrap(Data(base64Encoded: Self.onePixelPNGBase64))
        try writer.store(data: jpeg, globalId: 42, hole: 3)
        let renderer = WatchHoleImageStore(directoryURL: directory)
        let before = try XCTUnwrap(renderer.image(globalId: 42, hole: 3))

        try writer.store(data: png, globalId: 42, hole: 3)
        let after = try XCTUnwrap(renderer.image(globalId: 42, hole: 3))

        XCTAssertFalse(before === after)
        XCTAssertEqual(after.size.width, 1)
        XCTAssertEqual(after.size.height, 1)
    }
    #endif

    func testKeyIsGidUnderscoreHole() {
        XCTAssertEqual(WatchHoleImageStore.key(globalId: 31833, hole: 5), "31833_5")
    }

    private static let onePixelPNGBase64 =
        "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII="
}
