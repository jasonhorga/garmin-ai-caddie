import Foundation

enum StorageV1RawJSONGate {
    static let maximumDocumentBytes = 67_108_864
    static let maximumDepth = RoundTransportLimits.maxRawJsonDepth
    static let maximumKeyScalars = RoundTransportLimits.maxJsonKeyCharacters
    static let maximumStringScalars = 1_398_104

    fileprivate final class SourceIdentity {
        fileprivate init() {}
    }

    enum ValidationError: Error, Equatable {
        case documentTooLarge(actual: Int, maximum: Int)
        case malformedJSON(byteOffset: Int)
        case invalidUTF8(byteOffset: Int)
        case nestingTooDeep(byteOffset: Int, maximum: Int)
        case keyTooLong(byteOffset: Int, maximumScalars: Int)
        case stringTooLong(byteOffset: Int, maximumScalars: Int)
        case duplicateObjectKey(byteOffset: Int)
    }

    struct Event: Equatable {
        enum Kind: Equatable {
            case objectStart, objectEnd, arrayStart, arrayEnd, objectKey
            case string, number, trueLiteral, falseLiteral, nullLiteral
        }

        let kind: Kind
        fileprivate let byteRange: Range<Data.Index>
        let stringScalarCount: Int?
        let decodedStringUTF8: Data?
        fileprivate let sourceIdentity: SourceIdentity

        fileprivate init(
            kind: Kind,
            byteRange: Range<Data.Index>,
            stringScalarCount: Int?,
            decodedStringUTF8: Data?,
            sourceIdentity: SourceIdentity
        ) {
            self.kind = kind
            self.byteRange = byteRange
            self.stringScalarCount = stringScalarCount
            self.decodedStringUTF8 = decodedStringUTF8
            self.sourceIdentity = sourceIdentity
        }

        static func == (lhs: Event, rhs: Event) -> Bool {
            lhs.sourceIdentity === rhs.sourceIdentity
                && lhs.kind == rhs.kind
                && lhs.byteRange == rhs.byteRange
                && lhs.stringScalarCount == rhs.stringScalarCount
                && lhs.decodedStringUTF8 == rhs.decodedStringUTF8
        }
    }

    struct ValidatedRawJSON {
        private let data: Data
        fileprivate let sourceIdentity: SourceIdentity

        fileprivate init(
            data: Data,
            sourceIdentity: SourceIdentity
        ) {
            self.data = data
            self.sourceIdentity = sourceIdentity
        }

        func makeCursor() -> Cursor {
            Cursor(data: data, sourceIdentity: sourceIdentity)
        }

        func exactBytes() -> Data {
            data
        }

        func rawBytes(for event: Event) -> Data.SubSequence? {
            guard event.sourceIdentity === sourceIdentity else {
                return nil
            }
            return data[event.byteRange]
        }
    }

    final class Cursor {
        private let data: Data
        private let sourceIdentity: SourceIdentity

        fileprivate init(
            data: Data,
            sourceIdentity: SourceIdentity
        ) {
            self.data = data
            self.sourceIdentity = sourceIdentity
        }

        func next() throws -> Event? {
            _ = data
            _ = sourceIdentity
            return nil
        }
    }

    static func validate(_ data: Data) throws -> ValidatedRawJSON {
        guard data.count <= maximumDocumentBytes else {
            throw ValidationError.documentTooLarge(
                actual: data.count,
                maximum: maximumDocumentBytes
            )
        }
        return ValidatedRawJSON(
            data: data,
            sourceIdentity: SourceIdentity()
        )
    }
}
