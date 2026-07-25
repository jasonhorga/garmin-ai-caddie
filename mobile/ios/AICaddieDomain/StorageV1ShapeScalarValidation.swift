import Foundation

internal enum StorageV1ShapeScalarValidation {
    internal struct IntegerResult {
        internal let value: Int
        internal let metrics: StorageV1CanonicalMetrics.Value
    }

    internal static func validateString(
        decodedUTF8: Data,
        scalarCount: Int,
        maximumScalars: Int
    ) throws -> StorageV1CanonicalMetrics.Value {
        guard scalarCount <= maximumScalars else {
            throw StorageV1ShapeCodec.ValidationError.stringLimitExceeded
        }
        try validateNFC(decodedUTF8)
        return StorageV1CanonicalMetrics.quotedString(
            decodedUTF8: decodedUTF8
        )
    }

    internal static func validateNFC(_ decodedUTF8: Data) throws {
        guard let value = String(data: decodedUTF8, encoding: .utf8) else {
            throw StorageV1ShapeCodec.ValidationError.nonNFCString
        }
        let normalizedUTF8 = Data(
            value.precomposedStringWithCanonicalMapping.utf8
        )
        guard normalizedUTF8 == decodedUTF8 else {
            throw StorageV1ShapeCodec.ValidationError.nonNFCString
        }
    }

    internal static func validateBase64(
        decodedUTF8: Data,
        scalarCount: Int,
        maximumTextScalars: Int,
        maximumDecodedBytes: Int
    ) throws -> StorageV1CanonicalMetrics.Value {
        guard scalarCount <= maximumTextScalars else {
            throw StorageV1ShapeCodec.ValidationError.stringLimitExceeded
        }
        try validateNFC(decodedUTF8)

        guard decodedUTF8.count.isMultiple(of: 4) else {
            throw StorageV1ShapeCodec.ValidationError.invalidBase64
        }
        if decodedUTF8.isEmpty {
            return StorageV1CanonicalMetrics.quotedString(
                decodedUTF8: decodedUTF8
            )
        }

        var paddingCount = 0
        if decodedUTF8.last == 0x3D {
            paddingCount = 1
            if decodedUTF8.dropLast().last == 0x3D {
                paddingCount = 2
            }
        }
        let contentCount = decodedUTF8.count - paddingCount
        for (index, byte) in decodedUTF8.enumerated() {
            if index >= contentCount {
                guard byte == 0x3D else {
                    throw StorageV1ShapeCodec.ValidationError.invalidBase64
                }
            } else {
                guard isBase64AlphabetByte(byte) else {
                    throw StorageV1ShapeCodec.ValidationError.invalidBase64
                }
            }
        }

        let groups = decodedUTF8.count / 4
        let (groupBytes, overflow) = groups.multipliedReportingOverflow(by: 3)
        guard !overflow else {
            throw StorageV1ShapeCodec.ValidationError.invalidBase64
        }
        let decodedByteCount = groupBytes - paddingCount
        guard decodedByteCount <= maximumDecodedBytes,
              let text = String(data: decodedUTF8, encoding: .utf8),
              let decoded = Data(base64Encoded: text),
              decoded.count == decodedByteCount,
              decoded.base64EncodedData() == decodedUTF8 else {
            throw StorageV1ShapeCodec.ValidationError.invalidBase64
        }

        return StorageV1CanonicalMetrics.quotedString(
            decodedUTF8: decodedUTF8
        )
    }

    internal static func validateInteger(
        rawBytes: Data
    ) throws -> IntegerResult {
        guard !containsFractionOrExponent(rawBytes),
              let text = String(data: rawBytes, encoding: .utf8),
              let exactInt64 = Int64(text),
              let platformInt = Int(exactly: exactInt64) else {
            throw StorageV1ShapeCodec.ValidationError.invalidNumber
        }

        let canonical: Data
        do {
            canonical = try CanonicalJSON.data(.integer(exactInt64))
        } catch {
            throw StorageV1ShapeCodec.ValidationError.invalidNumber
        }
        guard canonical == rawBytes else {
            throw StorageV1ShapeCodec.ValidationError.invalidNumber
        }
        return IntegerResult(
            value: platformInt,
            metrics: StorageV1CanonicalMetrics.scalar(
                canonicalBytes: canonical.count
            )
        )
    }

    internal static func validateRecursiveNumber(
        rawBytes: Data
    ) throws -> StorageV1CanonicalMetrics.Value {
        if !containsFractionOrExponent(rawBytes) {
            return try validateInteger(rawBytes: rawBytes).metrics
        }
        guard let text = String(data: rawBytes, encoding: .utf8),
              let value = Double(text),
              value.isFinite else {
            throw StorageV1ShapeCodec.ValidationError.invalidNumber
        }

        let canonical: Data
        do {
            canonical = try CanonicalJSON.data(.number(value))
        } catch {
            throw StorageV1ShapeCodec.ValidationError.invalidNumber
        }
        guard canonical == rawBytes else {
            throw StorageV1ShapeCodec.ValidationError.invalidNumber
        }
        return StorageV1CanonicalMetrics.scalar(
            canonicalBytes: canonical.count
        )
    }

    private static func containsFractionOrExponent(_ bytes: Data) -> Bool {
        bytes.contains(0x2E) || bytes.contains(0x65) || bytes.contains(0x45)
    }

    private static func isBase64AlphabetByte(_ byte: UInt8) -> Bool {
        switch byte {
        case 0x41...0x5A, 0x61...0x7A, 0x30...0x39, 0x2B, 0x2F:
            return true
        default:
            return false
        }
    }
}
