import Foundation
import XCTest

enum ProductSharedVectors {
    /// Read the authoritative files directly; do not copy goldens into a second fixture set.
    /// Xcode copies the authoritative files to this test bundle; host SwiftPM uses its checkout.
    static func read<T: Decodable>(_ name: String, as type: T.Type = T.self) throws -> T {
        #if SWIFT_PACKAGE
        var root = URL(fileURLWithPath: #filePath)
        for _ in 0..<5 { root.deleteLastPathComponent() }
        let url = root.appendingPathComponent("tests/product/fixtures/shared/\(name).json")
        #else
        let url = try XCTUnwrap(Bundle(for: ProductLoopMapTests.self).url(forResource: name, withExtension: "json"))
        #endif
        return try JSONDecoder().decode(type, from: Data(contentsOf: url))
    }

    static func decode<T: Decodable>(_ object: Any, as type: T.Type = T.self) throws -> T {
        try JSONDecoder().decode(type, from: JSONSerialization.data(withJSONObject: object))
    }
}
