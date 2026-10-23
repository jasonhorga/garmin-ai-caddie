import Foundation

enum ProductSharedVectors {
    /// Read the authoritative files directly; do not copy goldens into a second fixture set.
    /// Xcode/macOS CI and SwiftPM both compile these sources from the repository checkout.
    static func read<T: Decodable>(_ name: String, as type: T.Type = T.self) throws -> T {
        var root = URL(fileURLWithPath: #filePath)
        for _ in 0..<5 { root.deleteLastPathComponent() }
        let url = root.appendingPathComponent("tests/product/fixtures/shared/\(name).json")
        return try JSONDecoder().decode(type, from: Data(contentsOf: url))
    }

    static func decode<T: Decodable>(_ object: Any, as type: T.Type = T.self) throws -> T {
        try JSONDecoder().decode(type, from: JSONSerialization.data(withJSONObject: object))
    }
}
