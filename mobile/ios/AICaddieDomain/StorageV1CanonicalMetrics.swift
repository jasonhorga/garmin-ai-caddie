import Foundation

internal enum StorageV1CanonicalMetrics {
    internal struct Value {
        internal let canonicalBytes: Int
        internal let relativeDepth: Int
    }

    internal struct Container {
        private var canonicalBytes = 2
        private var relativeDepth = 1
        private var entryCount = 0

        internal mutating func appendArrayValue(_ value: Value) {
            appendSeparatorIfNeeded()
            canonicalBytes = StorageV1CanonicalMetrics.saturatingAdd(
                canonicalBytes,
                value.canonicalBytes
            )
            relativeDepth = max(
                relativeDepth,
                StorageV1CanonicalMetrics.saturatingAdd(
                    value.relativeDepth,
                    1
                )
            )
            entryCount = StorageV1CanonicalMetrics.saturatingAdd(
                entryCount,
                1
            )
        }

        internal mutating func appendObjectMember(
            key: Value,
            value: Value
        ) {
            appendSeparatorIfNeeded()
            canonicalBytes = StorageV1CanonicalMetrics.saturatingAdd(
                canonicalBytes,
                key.canonicalBytes
            )
            canonicalBytes = StorageV1CanonicalMetrics.saturatingAdd(
                canonicalBytes,
                1
            )
            canonicalBytes = StorageV1CanonicalMetrics.saturatingAdd(
                canonicalBytes,
                value.canonicalBytes
            )
            relativeDepth = max(
                relativeDepth,
                StorageV1CanonicalMetrics.saturatingAdd(
                    value.relativeDepth,
                    1
                )
            )
            entryCount = StorageV1CanonicalMetrics.saturatingAdd(
                entryCount,
                1
            )
        }

        internal var value: Value {
            Value(
                canonicalBytes: canonicalBytes,
                relativeDepth: relativeDepth
            )
        }

        private mutating func appendSeparatorIfNeeded() {
            if entryCount > 0 {
                canonicalBytes = StorageV1CanonicalMetrics.saturatingAdd(
                    canonicalBytes,
                    1
                )
            }
        }
    }

    internal static func scalar(canonicalBytes: Int) -> Value {
        Value(canonicalBytes: canonicalBytes, relativeDepth: 0)
    }

    internal static func quotedString(decodedUTF8: Data) -> Value {
        var byteCount = 2
        for byte in decodedUTF8 {
            let contribution: Int
            switch byte {
            case 0x22, 0x5C:
                contribution = 2
            case 0x08, 0x09, 0x0A, 0x0C, 0x0D:
                contribution = 2
            case 0x00...0x1F:
                contribution = 6
            default:
                contribution = 1
            }
            byteCount = saturatingAdd(byteCount, contribution)
        }
        return scalar(canonicalBytes: byteCount)
    }

    internal static func isWithin(
        _ value: Value,
        maximumBytes: Int,
        maximumDepth: Int
    ) -> Bool {
        value.canonicalBytes <= maximumBytes
            && value.relativeDepth <= maximumDepth
    }

    private static func saturatingAdd(_ lhs: Int, _ rhs: Int) -> Int {
        let (sum, overflow) = lhs.addingReportingOverflow(rhs)
        return overflow ? Int.max : sum
    }
}
