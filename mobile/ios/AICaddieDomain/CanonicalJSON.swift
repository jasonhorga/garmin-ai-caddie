import CryptoKit
import Foundation
@_implementationOnly import SwiftJCS

public enum CanonicalJSONError: Error, Equatable {
    case nonNFC
    case negativeZero
    case unsafeInteger
    case unsupported
    case invalidDomain
}

public enum CanonicalJSON {
    private static let maximumSafeInteger: Int64 = 9_007_199_254_740_991

    public static func data(_ value: JSONValue) throws -> Data {
        try JSONCanonicalization.data(withJSONObject: foundationObject(value))
    }

    public static func data<T: Encodable>(_ value: T) throws -> Data {
        let encoded = try JSONEncoder().encode(value)
        guard !containsNegativeZeroNumber(in: encoded) else {
            throw CanonicalJSONError.negativeZero
        }
        return try data(JSONDecoder().decode(JSONValue.self, from: encoded))
    }

    private static func foundationObject(_ value: JSONValue) throws -> Any {
        switch value {
        case .integer(let integer):
            guard integer >= -maximumSafeInteger,
                  integer <= maximumSafeInteger else {
                throw CanonicalJSONError.unsafeInteger
            }
            return NSNumber(value: integer)
        case .number(let number):
            guard number.isFinite else {
                throw CanonicalJSONError.unsupported
            }
            guard !(number.isZero && number.sign == .minus) else {
                throw CanonicalJSONError.negativeZero
            }
            if number.rounded(.towardZero) == number,
               abs(number) > Double(maximumSafeInteger) {
                throw CanonicalJSONError.unsafeInteger
            }
            return NSNumber(value: number)
        case .null:
            return NSNull()
        case .bool(let bool):
            return NSNumber(value: bool)
        case .string(let string):
            try validateNFC(string)
            return string
        case .array(let array):
            return try array.map(foundationObject)
        case .object(let object):
            var result: [String: Any] = [:]
            result.reserveCapacity(object.count)
            for (key, child) in object {
                try validateNFC(key)
                result[key] = try foundationObject(child)
            }
            return result
        }
    }

    private static func validateNFC(_ string: String) throws {
        guard string.utf8.elementsEqual(
            string.precomposedStringWithCanonicalMapping.utf8
        ) else {
            throw CanonicalJSONError.nonNFC
        }
    }

    private static func containsNegativeZeroNumber(in data: Data) -> Bool {
        let bytes = Array(data)
        var index = 0
        var insideString = false
        var escaped = false

        while index < bytes.count {
            let byte = bytes[index]
            if insideString {
                if escaped {
                    escaped = false
                } else if byte == 0x5c {
                    escaped = true
                } else if byte == 0x22 {
                    insideString = false
                }
                index += 1
                continue
            }

            if byte == 0x22 {
                insideString = true
                index += 1
                continue
            }

            guard byte == 0x2d,
                  index + 1 < bytes.count,
                  bytes[index + 1] == 0x30 else {
                index += 1
                continue
            }

            var cursor = index + 2
            var allMantissaDigitsAreZero = true

            if cursor < bytes.count, bytes[cursor] == 0x2e {
                cursor += 1
                while cursor < bytes.count, isDigit(bytes[cursor]) {
                    if bytes[cursor] != 0x30 {
                        allMantissaDigitsAreZero = false
                    }
                    cursor += 1
                }
            }

            if cursor < bytes.count,
               bytes[cursor] == 0x65 || bytes[cursor] == 0x45 {
                cursor += 1
                if cursor < bytes.count,
                   bytes[cursor] == 0x2b || bytes[cursor] == 0x2d {
                    cursor += 1
                }
                while cursor < bytes.count, isDigit(bytes[cursor]) {
                    cursor += 1
                }
            }

            if allMantissaDigitsAreZero,
               cursor == bytes.count || isValueDelimiter(bytes[cursor]) {
                return true
            }
            index = max(cursor, index + 1)
        }

        return false
    }

    private static func isDigit(_ byte: UInt8) -> Bool {
        byte >= 0x30 && byte <= 0x39
    }

    private static func isValueDelimiter(_ byte: UInt8) -> Bool {
        byte == 0x09 || byte == 0x0a || byte == 0x0d || byte == 0x20
            || byte == 0x2c || byte == 0x5d || byte == 0x7d
    }
}

public enum TypedID {
    public static func make(domain: String, value: JSONValue) throws -> String {
        try make(domain: domain, canonicalBytes: CanonicalJSON.data(value))
    }

    public static func make<T: Encodable>(domain: String, value: T) throws -> String {
        try make(domain: domain, canonicalBytes: CanonicalJSON.data(value))
    }

    private static func make(domain: String, canonicalBytes: Data) throws -> String {
        guard !domain.isEmpty,
              domain.unicodeScalars.allSatisfy({
                  $0.value > 0 && $0.value <= 0x7f
              }) else {
            throw CanonicalJSONError.invalidDomain
        }

        var input = Data(domain.utf8)
        input.append(0)
        input.append(canonicalBytes)
        return SHA256.hash(data: input)
            .map { String(format: "%02x", $0) }
            .joined()
    }
}
