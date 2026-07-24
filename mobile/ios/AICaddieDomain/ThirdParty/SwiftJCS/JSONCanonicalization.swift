import Foundation

/// Errors that can occur during JSON canonicalization.
public enum JSONCanonicalizationError: Error, Sendable {

    /// The input data is not valid JSON.
    case invalidJSON

    /// A number value is NaN or Infinity, which are not permitted in JSON.
    case invalidNumber

    /// A string contains invalid Unicode (e.g., lone surrogates).
    case invalidUnicode
}

/// A namespace for canonicalizing JSON according to RFC 8785
/// (JSON Canonicalization Scheme).
public enum JSONCanonicalization {

    /// Returns canonical JSON data for a Foundation JSON object.
    ///
    /// - Parameter obj: A Foundation JSON object (e.g., `NSDictionary`,
    ///   `NSArray`, `NSString`, `NSNumber`, or `NSNull`).
    /// - Returns: The canonicalized JSON data encoded as UTF-8.
    /// - Throws: ``JSONCanonicalizationError`` if the object contains
    ///   invalid values.
    public static func data(withJSONObject obj: Any) throws -> Data {
        var buffer = Data()
        try _serialize(obj, into: &buffer)
        return buffer
    }

    /// Writes canonical JSON data for a Foundation JSON object to a stream.
    ///
    /// The stream must already be opened before calling this method.
    ///
    /// - Parameters:
    ///   - obj: A Foundation JSON object (e.g., `NSDictionary`, `NSArray`,
    ///     `NSString`, `NSNumber`, or `NSNull`).
    ///   - stream: An output stream to write the canonical JSON to.
    /// - Returns: The number of bytes written to the stream.
    /// - Throws: ``JSONCanonicalizationError`` if the object contains
    ///   invalid values, or an error from the stream if writing fails.
    @discardableResult
    public static func writeJSONObject(_ obj: Any, to stream: OutputStream) throws -> Int {
        let buffer = try data(withJSONObject: obj)
        return try buffer.withUnsafeBytes { (rawBuffer: UnsafeRawBufferPointer) -> Int in
            guard let pointer = rawBuffer.baseAddress?.assumingMemoryBound(to: UInt8.self) else {
                return 0
            }
            let written = stream.write(pointer, maxLength: rawBuffer.count)
            if written < 0 {
                throw stream.streamError ?? JSONCanonicalizationError.invalidJSON
            }
            return written
        }
    }
}

// MARK: - Internal serialization engine

internal func _serialize(_ value: Any, into buffer: inout Data) throws {
    switch value {
    case is NSNull:
        buffer.append(contentsOf: [0x6e, 0x75, 0x6c, 0x6c]) // null
    case let number as NSNumber:
        if CFGetTypeID(number) == CFBooleanGetTypeID() {
            if number.boolValue {
                buffer.append(contentsOf: [0x74, 0x72, 0x75, 0x65]) // true
            }
            else {
                buffer.append(contentsOf: [0x66, 0x61, 0x6c, 0x73, 0x65]) // false
            }
        }
        else {
            let serialized = try _serializeNumber(number.doubleValue)
            buffer.append(contentsOf: serialized.utf8)
        }
    case let string as String:
        try _serializeString(string, into: &buffer)
    case let array as [Any]:
        buffer.append(0x5b) // [
        for (index, element) in array.enumerated() {
            if index > 0 {
                buffer.append(0x2c) // ,
            }
            try _serialize(element, into: &buffer)
        }
        buffer.append(0x5d) // ]
    case let dict as [String: Any]:
        buffer.append(0x7b) // {
        let sortedKeys = dict.keys.sorted(by: _compareUTF16)
        for (index, key) in sortedKeys.enumerated() {
            if index > 0 {
                buffer.append(0x2c) // ,
            }
            try _serializeString(key, into: &buffer)
            buffer.append(0x3a) // :
            try _serialize(dict[key]!, into: &buffer)
        }
        buffer.append(0x7d) // }
    default:
        throw JSONCanonicalizationError.invalidJSON
    }
}

// MARK: - UTF-16 code unit comparison for property sorting

internal func _compareUTF16(_ a: String, _ b: String) -> Bool {
    let aUTF16 = Array(a.utf16)
    let bUTF16 = Array(b.utf16)
    let minLength = min(aUTF16.count, bUTF16.count)
    for i in 0..<minLength {
        if aUTF16[i] != bUTF16[i] {
            return aUTF16[i] < bUTF16[i]
        }
    }
    return aUTF16.count < bUTF16.count
}
